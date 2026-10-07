"""Wallpapers: a library folder, cached thumbnails, and the desktop / lock-screen images made from the original.

The library is ~/Pictures/Wallpapers (the XDG pictures dir when one is set). Setting a wallpaper never touches the
original: the desktop image (~/.config/fw13/theme/desktop.jpg, read by hyprpaper) and the lock image
(~/.config/fw13/theme/lock.jpg, read by hyprlock) are rendered from it with an effect each (none, blur, dim, grey,
blur+dim), and ~/.config/hypr/wallpaper.jpg keeps a copy of the desktop image for anything that still reads it.
When the theme follows the wallpaper, its colours are read from a small copy of the original (not the effect).

State lives in fw13.store under "wallpaper": {"current": original path, "desktop_effect", "lock_effect"}.
No GTK here (Pillow; GdkPixbuf only to decode formats Pillow lacks, e.g. JPEG XL). Public functions return None
or an error string unless they say otherwise; nothing runs at import.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from . import store
from . import theme as _theme

THEME_DIR = _theme.DIR
DESKTOP = os.path.join(THEME_DIR, "desktop.jpg")   # hyprpaper.conf
LOCK = os.path.join(THEME_DIR, "lock.jpg")          # hyprlock.conf
COMPAT = os.path.expanduser("~/.config/hypr/wallpaper.jpg")  # the old single wallpaper path, kept in sync
THUMBS = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "fw13", "thumbs")
EFFECTS = (("none", "None"), ("blur", "Blur"), ("dim", "Dim"), ("grey", "Grey"), ("blur+dim", "Blur + dim"))
DEFAULT_EFFECTS = {"desktop_effect": "none", "lock_effect": "none"}  # hyprlock.conf blurs on its own
MAX_W = 3840      # rendered desktop / lock images
PALETTE_W = 1024  # the copy matugen reads (it fails on big JPEG XL files)
EXTS = (".jpg", ".jpeg", ".png", ".webp", ".jxl")

_lock = threading.RLock()  # set / set_effects / remove: one at a time (they share the store and the files)
_library_dir = None
_pixbuf_exts = None


# ---- library ------------------------------------------------------------------------------------------------

def library_dir():
    """~/Pictures/Wallpapers, or Wallpapers in the XDG pictures dir (`xdg-user-dir PICTURES`) when one is set."""
    global _library_dir
    if _library_dir is None:
        home = os.path.expanduser("~")
        pics = ""
        try:
            pics = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True, text=True, timeout=5,
                                  stdin=subprocess.DEVNULL).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        # xdg-user-dir prints $HOME when the dir isn't configured
        if not pics or os.path.normpath(pics) == os.path.normpath(home):
            pics = os.path.join(home, "Pictures")
        _library_dir = os.path.join(pics, "Wallpapers")
    return _library_dir


def _pixbuf_formats():
    """Extensions GdkPixbuf can decode (used for those Pillow can't, e.g. .jxl). No Gtk import."""
    global _pixbuf_exts
    if _pixbuf_exts is None:
        exts = []
        try:
            import gi
            gi.require_version("GdkPixbuf", "2.0")
            from gi.repository import GdkPixbuf
            for f in GdkPixbuf.Pixbuf.get_formats():
                exts += ["." + e.lower() for e in f.get_extensions()]
        except (ImportError, ValueError):
            pass
        _pixbuf_exts = frozenset(exts)
    return _pixbuf_exts


NO_PILLOW = "python3-pillow is not installed"


def have_pillow():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _pillow_formats():
    try:
        from PIL import Image
        Image.init()
        return frozenset(e for e, fmt in Image.registered_extensions().items() if fmt in Image.OPEN)
    except ImportError:
        return frozenset()


def readable_exts():
    """The extensions in EXTS that Pillow or GdkPixbuf can decode here."""
    can = _pillow_formats() | _pixbuf_formats()
    return tuple(e for e in EXTS if e in can)


def _ext(path):
    return os.path.splitext(path)[1].lower()


def library():
    """Sorted image paths in the library (missing folder: [])."""
    d = library_dir()
    exts = readable_exts()
    try:
        names = os.listdir(d)
    except OSError:
        return []
    out = [os.path.join(d, n) for n in names
           if not n.startswith(".") and _ext(n) in exts and os.path.isfile(os.path.join(d, n))]
    return sorted(out, key=lambda p: os.path.basename(p).lower())


def in_library(path):
    try:
        lib = os.path.realpath(library_dir())
        return os.path.commonpath([lib, os.path.realpath(path)]) == lib and os.path.realpath(path) != lib
    except ValueError:
        return False


def _unique(dirname, name):
    base, ext = os.path.splitext(name)
    cand, i = name, 2
    while os.path.exists(os.path.join(dirname, cand)):
        cand = f"{base}-{i}{ext}"
        i += 1
    return os.path.join(dirname, cand)


def readable(path):
    """True if `path` decodes as an image (a cheap, downscaled decode). Without Pillow nothing can be checked
    (or rendered): True, so add() still copies and set() reports the missing package."""
    if not have_pillow():
        return True
    try:
        _open(path, max_side=64)
        return True
    except Exception:  # noqa: BLE001 — OSError, ValueError, Pillow's DecompressionBombError, …
        return False


def add(paths):
    """Copy `paths` into the library (originals are never moved or deleted). Files already in the library are
    kept as they are. Returns the library paths, in order; unreadable or unsupported files are skipped."""
    d = library_dir()
    os.makedirs(d, exist_ok=True)
    exts = readable_exts()
    out = []
    for src in paths:
        if not os.path.isfile(src) or _ext(src) not in exts or not readable(src):
            continue
        if in_library(src):
            out.append(os.path.join(d, os.path.relpath(os.path.realpath(src), os.path.realpath(d))))
            continue
        dst = _unique(d, os.path.basename(src))
        fd, tmp = tempfile.mkstemp(prefix=".add-", dir=d)
        os.close(fd)
        try:
            shutil.copyfile(src, tmp)
            os.chmod(tmp, 0o644)
            if os.path.exists(dst):  # appeared meanwhile
                dst = _unique(d, os.path.basename(src))
            os.replace(tmp, dst)
            out.append(dst)
        except OSError:
            pass
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return out


def remove(path):
    """Delete `path` from the library (and its thumbnails). Only files inside the library; the current wallpaper is
    first switched to the next one in the library (if it is the only one, it is kept)."""
    if not in_library(path) or not os.path.isfile(path):
        return "Only pictures in the wallpaper library can be removed"
    real_path = os.path.realpath(path)
    warn = None
    with _lock:
        cur = current()
        if cur and os.path.realpath(cur) == real_path:
            lib = library()
            real = [os.path.realpath(p) for p in lib]
            if len(lib) < 2 or real_path not in real:
                return "This is the current wallpaper and the only one in the library"
            i = real.index(real_path)
            err = None
            for nxt in lib[i + 1:] + lib[:i]:  # the following pictures in turn, skipping unreadable ones
                err = set(nxt)
                cur = current()
                if not cur or os.path.realpath(cur) != real_path:
                    warn = err  # switched; a theme warning ("Wallpaper set, but: …") is passed on
                    break
            else:
                return f"Could not switch away from it first: {err}"
        _drop_thumbs(path)
        try:
            os.remove(path)
        except OSError as e:
            return f"Could not remove it: {e}"
    return warn


# ---- decoding -----------------------------------------------------------------------------------------------

def _open(path, max_side=None):
    """`path` as an upright PIL image (EXIF orientation applied). Pillow first, GdkPixbuf for what it can't
    read. max_side lets GdkPixbuf decode at a smaller size (cheap for thumbnails). Raises OSError/ValueError."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise OSError(NO_PILLOW) from None
    if _ext(path) in _pillow_formats():
        try:
            im = Image.open(path)
            if max_side:
                im.draft("RGB", (max_side, max_side))  # JPEG: decode at a fraction of the size
            im = ImageOps.exif_transpose(im)
            im.load()
            return im
        except (OSError, ValueError, Image.DecompressionBombError):
            pass  # wrong extension or a format Pillow lacks: try GdkPixbuf
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf, GLib
    except (ImportError, ValueError):
        raise OSError("cannot read this image") from None
    try:
        if max_side:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, max_side, max_side, True)
        else:
            pb = GdkPixbuf.Pixbuf.new_from_file(path)
        pb = pb.apply_embedded_orientation() or pb
    except GLib.Error as e:  # glycin's message is a multi-line dump: keep it out of the UI
        print(f"fw13.wallpaper: {path}: {e.message}", file=sys.stderr)
        raise OSError(f"cannot read this image ({os.path.basename(path)})") from None
    mode = "RGBA" if pb.get_has_alpha() else "RGB"
    return Image.frombytes(mode, (pb.get_width(), pb.get_height()), pb.read_pixel_bytes().get_data(),
                           "raw", mode, pb.get_rowstride())


def _flatten(im, bg):
    """RGB copy of `im`, alpha flattened onto colour `bg` ("#rrggbb")."""
    from PIL import Image
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        base = Image.new("RGB", im.size, bg[:7])
        base.paste(im, mask=im.getchannel("A"))
        return base
    return im.convert("RGB")


def _fit_width(im, w):
    from PIL import Image
    if im.width <= w:
        return im
    return im.resize((w, max(1, round(im.height * w / im.width))), Image.Resampling.LANCZOS)


def _atomic_save(im, path, fmt, **kw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + "-", dir=os.path.dirname(path))
    os.close(fd)
    try:
        im.save(tmp, fmt, **kw)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ---- thumbnails ---------------------------------------------------------------------------------------------

def _thumb_prefix(path):
    return hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:20]


def _drop_thumbs(path, keep=None):
    pre = _thumb_prefix(path) + "-"
    try:
        for n in os.listdir(THUMBS):
            if n.startswith(pre) and n != keep:
                try:
                    os.remove(os.path.join(THUMBS, n))
                except OSError:
                    pass
    except OSError:
        pass


def thumbnail(path, w=240):
    """A cached PNG thumbnail (w × w·9/16, centre-cropped) for `path`; None if it can't be read.

    Keyed by path + mtime + size, so an edited file gets a new one (the old one is dropped)."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    h = max(1, w * 9 // 16)
    key = hashlib.sha1(f"{st.st_mtime_ns}:{st.st_size}:{w}".encode()).hexdigest()[:12]
    name = f"{_thumb_prefix(path)}-{w}-{key}.png"
    out = os.path.join(THUMBS, name)
    if os.path.isfile(out):
        return out
    try:
        im = _open(path, max_side=max(w, h) * 2)
        im = _flatten(im, _theme.palette()["bg"])
        im = ImageOps.fit(im, (w, h), Image.Resampling.LANCZOS)
        _atomic_save(im, out, "PNG", optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    for n in os.listdir(THUMBS):  # older thumbnails of this file at this width
        if n.startswith(f"{_thumb_prefix(path)}-{w}-") and n != name:
            try:
                os.remove(os.path.join(THUMBS, n))
            except OSError:
                pass
    return out


# ---- state --------------------------------------------------------------------------------------------------

def _effect_names():
    return tuple(k for k, _ in EFFECTS)


def state():
    w = store.get("wallpaper")
    w = w if isinstance(w, dict) else {}
    out = {"current": w.get("current") if isinstance(w.get("current"), str) else None}
    for k, v in DEFAULT_EFFECTS.items():
        out[k] = w.get(k) if w.get(k) in _effect_names() else v
    return out


def _save_state(**changes):
    data = store.load()
    w = data.get("wallpaper")
    w = dict(w) if isinstance(w, dict) else {}
    w.update(changes)
    data["wallpaper"] = w
    store.save(data)


def current():
    """The original image of the current wallpaper, or None (none set, or the file is gone)."""
    p = state()["current"]
    return p if p and os.path.isfile(p) else None


# ---- rendering ----------------------------------------------------------------------------------------------

def effect(im, name):
    """`im` (RGB) with effect `name` applied."""
    from PIL import ImageEnhance, ImageFilter, ImageOps
    if name in ("blur", "blur+dim"):
        # Blur a quarter-size copy and scale it back: same look as a big radius, a fraction of the time.
        small = im.resize((max(1, im.width // 4), max(1, im.height // 4)))
        small = small.filter(ImageFilter.GaussianBlur(max(2, im.width // 400)))
        im = small.resize(im.size)
    if name in ("dim", "blur+dim"):
        im = ImageEnhance.Brightness(im).enhance(0.6)
    if name == "grey":
        im = ImageOps.grayscale(im).convert("RGB")
    return im


def _render(src, desktop_effect, lock_effect, which=("desktop", "lock")):
    """Write DESKTOP / LOCK (and COMPAT = the desktop image) from original `src`. Returns the base RGB image
    (scaled, effect-free) for reuse."""
    base = _fit_width(_flatten(_open(src), _theme.palette()["bg"]), MAX_W)
    if "desktop" in which:
        desk = effect(base, desktop_effect)
        _atomic_save(desk, DESKTOP, "JPEG", quality=90)
        _atomic_save(desk, COMPAT, "JPEG", quality=90)
    if "lock" in which:
        _atomic_save(effect(base, lock_effect), LOCK, "JPEG", quality=90)
    return base


def restart_hyprpaper():
    """hyprpaper 0.8 has no reload IPC we can rely on (`hyprctl hyprpaper` answers "Invalid request"), so
    restart it. Only inside a Hyprland session."""
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return
    try:
        subprocess.run(["pkill", "-x", "hyprpaper"], timeout=5)
        for _ in range(20):  # let the old one release the layer surface first
            if subprocess.run(["pgrep", "-x", "hyprpaper"], capture_output=True, timeout=5).returncode:
                break
            time.sleep(0.1)
        subprocess.Popen(["uwsm", "app", "--", "hyprpaper"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _palette_copy(src=None, base=None):
    """Path of a temp PNG (<= PALETTE_W wide) of the original, for matugen. Caller deletes it."""
    im = base if base is not None else _flatten(_open(src, max_side=PALETTE_W * 2), _theme.palette()["bg"])
    im = _fit_width(im, PALETTE_W)
    fd, tmp = tempfile.mkstemp(prefix="fw13-wallpaper-", suffix=".png")
    os.close(fd)
    try:
        im.save(tmp, "PNG")
    except (OSError, ValueError):
        os.unlink(tmp)
        raise
    return tmp


def _theme_from(src, base=None, apply=True):
    """Palette from original `src` into the theme (only when it follows the wallpaper). None or an error."""
    s = _theme.state()
    if s["source"] != "wallpaper":
        return None
    try:
        tmp = _palette_copy(src, base)
    except (OSError, ValueError) as e:
        return f"Could not read colours from the wallpaper: {e}"
    try:
        p = _theme.from_wallpaper(tmp, s["mode"], s["type"])
    except RuntimeError as e:
        return f"Could not read colours from the wallpaper: {e}"
    finally:
        os.unlink(tmp)
    data = store.load()
    had, old = "theme" in data, data.get("theme")
    t = old if isinstance(old, dict) else {}
    data["theme"] = {**t, **s, "palette": p, "wallpaper": src}
    try:
        store.save(data)
    except OSError as e:
        return f"Could not save the theme: {e}"
    try:
        _theme.write(p, apply=apply)
    except OSError as e:  # put the old entry back so palette() matches the files on disk (like set_source)
        data = store.load()
        if had:
            data["theme"] = old
        else:
            data.pop("theme", None)
        try:
            store.save(data)
            _theme.write(_theme.palette(), apply=False)
        except OSError:
            pass
        return f"Could not write the theme files: {e}"
    return None


def set(path, theme=True, restart=True):  # noqa: A001 — fw13.wallpaper.set(...)
    """Make `path` (the original, anywhere) the wallpaper: store it, render the desktop and lock images, restart
    hyprpaper (restart=False: not, and apps are not reloaded — for install scripts), then, if theme and the
    theme follows the wallpaper, read new colours from it."""
    if not path or not os.path.isfile(path):
        return "No such picture"
    path = os.path.abspath(path)
    with _lock:
        st = state()
        try:
            base = _render(path, st["desktop_effect"], st["lock_effect"])
        except Exception as e:  # noqa: BLE001 — OSError, ValueError, Pillow's DecompressionBombError
            return f"Could not set the wallpaper: {e}"
        try:
            _save_state(current=path)
        except OSError as e:
            return f"Could not save the wallpaper choice: {e}"
        if restart:
            restart_hyprpaper()
        if theme:
            err = _theme_from(path, base=base, apply=restart)
            if err:
                return f"Wallpaper set, but: {err}"
    return None


def set_effects(desktop=None, lock=None, restart=True):
    """Change the desktop and/or lock effect, store it and re-render from the current original."""
    names = _effect_names()
    if desktop is not None and desktop not in names or lock is not None and lock not in names:
        return "Unknown effect"
    with _lock:
        st = state()
        changes = {}
        if desktop is not None:
            changes["desktop_effect"] = desktop
        if lock is not None:
            changes["lock_effect"] = lock
        try:
            _save_state(**changes)
        except OSError as e:
            return f"Could not save the effect: {e}"
        src = current()
        if not src:
            return None  # used the next time a wallpaper is set
        which = [k for k, v in (("desktop", desktop), ("lock", lock))
                 if v is not None and (v != st[f"{k}_effect"] or not os.path.isfile(DESKTOP if k == "desktop"
                                                                                     else LOCK))]
        if not which:
            return None
        new = {**st, **changes}
        try:
            _render(src, new["desktop_effect"], new["lock_effect"], which)
        except Exception as e:  # noqa: BLE001
            return f"Could not render the wallpaper: {e}"
        if restart and "desktop" in which:
            restart_hyprpaper()
    return None


def set_theme(source, mode=None, scheme_type=None):
    """theme.set_source(), but colours come from (a small copy of) the original wallpaper, not the desktop image
    with its effect. Falls back to ~/.config/hypr/wallpaper.jpg when no original is known."""
    with _lock:  # a wallpaper set() running meanwhile would overwrite the theme entry with its own palette
        src = current()
        if source != "wallpaper" or not src:
            return _theme.set_source(source, mode=mode, scheme_type=scheme_type)
        try:
            tmp = _palette_copy(src)
        except (OSError, ValueError) as e:
            return f"Could not read colours from the wallpaper: {e}"
        try:
            err = _theme.set_source(source, mode=mode, scheme_type=scheme_type, wallpaper=tmp)
        finally:
            os.unlink(tmp)
        if not err:  # remember the original, not the temp copy
            data = store.load()
            if isinstance(data.get("theme"), dict):
                data["theme"]["wallpaper"] = src
                try:
                    store.save(data)
                except OSError:
                    pass
        return err


def init():
    """First run (chezmoi run_once): create the library; with no current wallpaper, adopt an old
    ~/.config/hypr/wallpaper.jpg (copied into the library) or else the first readable library picture, and render the
    desktop/lock images from it. No restarts, no reloads — safe without a desktop."""
    os.makedirs(library_dir(), exist_ok=True)
    if not have_pillow():
        return NO_PILLOW
    if current():
        if not (os.path.isfile(DESKTOP) and os.path.isfile(LOCK)):
            return set(current(), theme=False, restart=False)
        return None
    # No current wallpaper yet: adopt the old one (whatever the library holds), else the first usable library
    # picture, so hyprpaper / hyprlock have desktop.jpg / lock.jpg to show.
    cands = add([COMPAT]) if os.path.isfile(COMPAT) else []
    err = None
    for p in cands + [p for p in library() if p not in cands]:
        err = set(p, theme=False, restart=False)
        if current():
            return None
    return err
