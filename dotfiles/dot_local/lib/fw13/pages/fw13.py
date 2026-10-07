"""fw13: what the installer asked once — Chromium sign-in keys, Ollama Cloud key, restic backups, login shell —
plus the dotfiles checkout and what the installer set up.

Backend: fw13.setup (chezmoi.toml + chezmoi apply of just the affected files). Key fields are always empty and
hidden; the page only ever learns "set" and a length.
"""
import os
import secrets
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import setup, store  # noqa: E402
from ..ui_theme import button  # noqa: E402
from .appearance import background  # noqa: E402
from .common import Page, label, launch, wrap  # noqa: E402
from .system import bg  # noqa: E402

OK_DOT = "●"
RELOGIN = "Saved — log out and back in to use the new keys"


def _buttons(*widgets):
    box = Gtk.Box(spacing=6)
    for w in widgets:
        if w is not None:
            box.pack_start(w, False, False, 0)
    return box


def _set_text(info):
    return f"{OK_DOT} Set" if info["set"] else "Not set"


def _when(ts):
    if not ts:
        return ""
    t = time.localtime(ts)
    if time.strftime("%Y%m%d", t) == time.strftime("%Y%m%d"):
        return time.strftime("today %H:%M", t)
    if time.strftime("%Y%m%d", t) == time.strftime("%Y%m%d", time.localtime(time.time() - 86400)):
        return time.strftime("yesterday %H:%M", t)
    return time.strftime("%-d %b %H:%M", t)


def _load():
    """Everything the page shows; runs in a worker thread."""
    st = setup.status()
    return {"status": st,
            "backup": setup.backup_state() if st["restic"]["repository"]["set"] else None,
            "shells": setup.shells(), "shell": setup.current_shell(),
            "dots": setup.dotfiles_state(), "installed": setup.installed_state(),
            "fingers": setup.fingerprints(), "timeshift": setup.timeshift_state()}


class Fw13Page(Page):
    def __init__(self):
        super().__init__("fw13")
        self.status = self.add_widget(label("", "dim", wrap=True))
        self.status.set_no_show_all(True)
        self.st = None         # _load() result; None until the first load
        self.busy = False      # an action is running: buttons are insensitive
        self.confirming = False
        self.restic = None     # (state, message) from the last connection test
        self.poll = None       # GLib source id while a backup runs
        self.render()
        self.reload()

    # --- state -------------------------------------------------------------
    def refresh(self):
        if not (self.busy or self.confirming):
            self.reload()

    def reload(self):
        bg(_load, self.got_state, fail=lambda e: {"error": str(e)})

    def got_state(self, res):
        if "error" in res and "status" not in res:
            self.set_status(res["error"], "bad")
            return False
        self.st = res
        if res["status"]["error"]:
            self.set_status(res["status"]["error"], "bad")
        if res["backup"] and res["backup"]["running"] and not self.poll:
            self.start_poll()
        if not (self.busy or self.confirming):
            self.render()
        return False

    def set_status(self, text, cls="dim"):
        ctx = self.status.get_style_context()
        for c in ("dim", "bad", "ok"):
            ctx.remove_class(c)
        ctx.add_class(cls)
        self.status.set_text(text)
        self.status.set_visible(bool(text))

    def run(self, msg, work, done_note=""):
        """Run work() -> (ok, message) off the main loop (kept alive if the window closes), then reload."""
        if self.busy:
            return
        self.busy = True
        self.confirming = False
        self.set_status(msg)
        for child in self.box.get_children()[2:]:
            child.set_sensitive(False)

        def done(res):
            self.busy = False
            if isinstance(res, str):  # background(): an exception, as "Error: …"
                ok, note = False, res
            else:
                ok, note = res
            self.set_status((note or done_note) if ok else note, "dim" if ok else "bad")
            self.render()
            self.reload()
        background(work, done)

    # --- layout ------------------------------------------------------------
    def render(self):
        self.clear(keep=2)
        if self.st is None:
            self.add_widget(label("Loading…", "dim"))
            self.show_all()
            return
        st = self.st["status"]
        self.heading("Keys")
        self.render_chromium(st["chromium"])
        self.render_ollama(st["ollama"]["api_key"])
        self.heading("Backups (restic)")
        self.render_restic(st["restic"])
        self.heading("Login shell")
        self.render_shell()
        self.heading("Dotfiles")
        self.render_dotfiles()
        self.heading("Installed with")
        self.render_installed()
        self.show_all()

    def item(self, title, hint, buttons, lead=None, lead_cls="ok"):
        """Title, a hint line ('lead' coloured, then the dim rest), buttons on the right (stacks when narrow)."""
        r = Gtk.Box(spacing=12)
        r.get_style_context().add_class("item")
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.pack_start(wrap(label(title)), False, False, 0)
        sub = Gtk.Box()
        if lead:
            sub.pack_start(label(lead, lead_cls), False, False, 0)
        if hint:
            sub.pack_start(wrap(label((" · " if lead else "") + hint, "dim")), True, True, 0)
        left.pack_start(sub, False, False, 0)
        r.pack_start(left, True, True, 0)
        if buttons:
            box = _buttons(*buttons)
            box.set_valign(Gtk.Align.CENTER)
            r.pack_end(box, False, False, 0)
            self.adapt(r, box)
        return self.add_widget(r)

    def render_chromium(self, ch):
        n = sum(v["set"] for v in ch.values())
        if n:
            self.item("Chromium sign-in", f"Google API keys ({n} of 3 values)",
                      [button("Change", self.edit_chromium), self.remove_button("chromium", "Remove these keys?")],
                      lead=f"{OK_DOT} Set" if n == 3 else "Incomplete", lead_cls="ok" if n == 3 else "warn")
        else:
            self.item("Chromium sign-in", "Google API keys for Chromium Sync",
                      [button("Add keys", self.edit_chromium, "primary")], lead="Not set", lead_cls="dim")

    def render_ollama(self, key):
        if key["set"]:
            self.item("Ollama Cloud", "API key for OpenCode",
                      [button("Change", self.edit_ollama), self.remove_button("ollama", "Remove this key?")],
                      lead=_set_text(key))
        else:
            self.item("Ollama Cloud", "API key for OpenCode",
                      [button("Add key", self.edit_ollama, "primary")], lead="Not set", lead_cls="dim")

    def render_restic(self, rs):
        repo, pw = rs["repository"], rs["password"]
        if not repo["set"]:
            self.item("Repository", "Daily backup of your home folder (sftp:, s3:, b2:, rest: or a local path)",
                      [button("Set up", self.edit_restic, "primary")], lead="Not set", lead_cls="dim")
            return
        self.item("Repository", repo["display"],
                  [button("Change", self.edit_restic),
                   self.remove_button("restic", "Remove the repository settings and stop daily backups?")],
                  lead=f"{OK_DOT} Set")
        self.item("Password", f"{pw['len']} characters" if pw["set"] else "Needed to open the repository",
                  [], lead=_set_text(pw), lead_cls="ok" if pw["set"] else "warn")
        b = self.st["backup"] or {}
        sw = Gtk.Switch()
        sw.set_active(bool(b.get("timer")))
        sw.connect("state-set", self.on_timer)
        self.row("Daily backup", sw, hint="restic-backup.timer · keeps 7 daily, 4 weekly, 6 monthly")
        if b.get("running") or self.poll:
            last, cls = "Backing up now…", "dim"
        elif b.get("last"):
            good = b.get("result") == "success"
            last = f"Last run: {_when(b['last'])}, {'succeeded' if good else 'failed'}"
            cls = "ok" if good else "bad"
        else:
            last, cls = "Last run: never", "dim"
        self.add_widget(label(last, cls))
        if self.restic:
            state, msg = self.restic
            self.add_widget(label(msg, "ok" if state == "ok" else "bad", wrap=True))
        init = button("Initialise", self.restic_init, "primary") \
            if self.restic and self.restic[0] == "missing" else None
        now = button("Back up now", self.backup_now)
        now.set_sensitive(not (b.get("running") or self.poll))
        tools = _buttons(button("Test connection", self.restic_test), init, now,
                         button("View log", lambda: launch("kitty", "--hold", "-e", "journalctl", "--user",
                                                           "-u", setup.UNIT, "-n", "200", "--no-pager")))
        tools.set_halign(Gtk.Align.START)
        self.add_widget(tools)

    def render_shell(self):
        shells, cur = self.st["shells"], self.st["shell"]
        combo = Gtk.ComboBoxText()
        for s in shells:
            combo.append(s, os.path.basename(s))
        if cur in shells:
            combo.set_active_id(cur)
        apply = button("Apply", lambda: self.set_shell(combo.get_active_id()))
        apply.set_sensitive(False)
        combo.connect("changed", lambda c: apply.set_sensitive(c.get_active_id() not in (None, cur)))
        self.row(f"Shell: {os.path.basename(cur)}", _buttons(combo, apply),
                 hint="Applies to new logins and terminals, GNOME too")

    def render_dotfiles(self):
        d = self.st["dots"]
        where = " @ ".join(x for x in (d["remote"], d["rev"]) if x) or d["source"] or "No chezmoi source found"
        upd = button("Update dotfiles", lambda: launch("kitty", "--hold", "-e", "chezmoi", "update"))
        rerun = button("Re-run user setup", lambda: launch("kitty", "--hold", "-e", setup.INSTALLER,
                                                           "--user-only")) if d["installer"] else None
        self.item(where, "Both apply the pushed repo, not local edits" + (" · local changes in the source"
                                                                          if d["dirty"] else ""),
                  [upd, rerun])

    def render_installed(self):
        for k, v in self.st["installed"]:
            self.row(k, label(v, "dim", wrap=True, max_width_chars=40, xalign=1))
        n = self.st["fingers"]
        if n is None:
            self.row("Fingerprint", label("No reader found", "dim"))
        else:
            enrol = button("Enrol", lambda: launch("kitty", "--hold", "-e", "fprintd-enroll"))
            self.row("Fingerprint", _buttons(label(f"{n} finger{'s' if n != 1 else ''}", "dim"), enrol))
        self.row("Timeshift", label(self.st["timeshift"] or "Not set up (sudo fw-timeshift-setup)", "dim",
                                    wrap=True, max_width_chars=40, xalign=1))

    def remove_button(self, table, question):
        """Remove, with a confirm step in place of the row's buttons."""
        b = button("Remove", None, "danger")

        def ask(_b):
            self.confirming = True
            box = b.get_parent()
            for w in box.get_children():
                box.remove(w)
            box.pack_start(wrap(label(question, "warn")), False, False, 0)
            box.pack_start(button("Cancel", self.cancel_confirm), False, False, 0)
            box.pack_start(button("Remove", lambda: self.remove(table), "danger"), False, False, 0)
            box.show_all()
        b.connect("clicked", ask)
        return b

    def cancel_confirm(self):
        self.confirming = False
        self.render()

    # --- key dialogs ---------------------------------------------------------
    def ask(self, title, fields, note="", generate=None):
        """Modal dialog -> {key: value} or None. fields: [(key, placeholder, secret, required)]. Entries start
        empty; a blank optional field means "keep the current value". generate: key filled by Generate. The
        repository is shown as typed, but hidden like a secret while it holds user:pass@."""
        dlg = Gtk.Dialog(transient_for=self.get_toplevel(), modal=True, title=title)
        dlg.get_style_context().add_class("panel")
        dlg.set_default_size(420, -1)
        area = dlg.get_content_area()
        area.set_spacing(8)
        for side in ("top", "bottom", "start", "end"):
            getattr(area, f"set_margin_{side}")(16)
        area.pack_start(label(title, "title"), False, False, 0)
        if note:
            area.pack_start(label(note, "dim", wrap=True, max_width_chars=50), False, False, 0)
        entries = {}
        for key, placeholder, secret, _req in fields:
            e = Gtk.Entry(visibility=not secret, placeholder_text=placeholder, max_length=512)
            if secret:
                e.set_input_purpose(Gtk.InputPurpose.PASSWORD)
            entries[key] = e
            area.pack_start(e, False, False, 0)
        show = Gtk.CheckButton(label="Show")

        def update_visibility(*_):
            for key, _p, secret, _r in fields:
                e = entries[key]
                hide = secret or (key == "repository" and setup.USERINFO_RE.search(e.get_text()))
                e.set_visibility(show.get_active() or not hide)
        show.connect("toggled", update_visibility)
        tools = Gtk.Box(spacing=8)
        if any(s or k == "repository" for k, _p, s, _r in fields):
            tools.pack_start(show, False, False, 0)
        if generate:
            gen = Gtk.Button(label="Generate")
            gen.connect("clicked", lambda _b: entries[generate].set_text(secrets.token_urlsafe(32)))
            tools.pack_start(gen, False, False, 0)
        area.pack_start(tools, False, False, 0)
        err = label("", "bad", wrap=True, max_width_chars=50)
        area.pack_start(err, False, False, 0)
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        ok = dlg.add_button("Save", Gtk.ResponseType.OK)
        ok.get_style_context().add_class("primary")
        dlg.set_default_response(Gtk.ResponseType.OK)

        def check():
            for key, _p, secret, req in fields:
                v = entries[key].get_text()
                if req and not v:
                    return False, ""
                good, msg = setup.validate(v, secret)
                if not good:
                    return False, msg
            return any(e.get_text() for e in entries.values()), ""

        def changed(*_):
            update_visibility()
            good, msg = check()
            ok.set_sensitive(good)
            err.set_text(msg)
        for e in entries.values():
            e.connect("changed", changed)
            e.connect("activate", lambda _e: check()[0] and dlg.response(Gtk.ResponseType.OK))
        changed()
        dlg.show_all()
        self.confirming = True
        try:
            resp = dlg.run()
        finally:
            self.confirming = False
        result = {k: e.get_text() for k, e in entries.items() if e.get_text()}
        dlg.destroy()
        return result if resp == Gtk.ResponseType.OK and check()[0] else None

    def edit_chromium(self):
        ch = self.st["status"]["chromium"]  # a field is required while its own value is unset
        have = any(v["set"] for v in ch.values())
        got = self.ask("Chromium sign-in", [(k, ph, True, not ch[k]["set"]) for k, ph in
                                            (("api_key", "GOOGLE_API_KEY"),
                                             ("client_id", "GOOGLE_DEFAULT_CLIENT_ID"),
                                             ("client_secret", "GOOGLE_DEFAULT_CLIENT_SECRET"))],
                       note="Your own Google OAuth client for Chromium Sync." +
                            (" Leave a field blank to keep its current value." if have else ""))
        if got:
            self.run("Saving…", lambda: setup.set_values("chromium", got), RELOGIN)

    def edit_ollama(self):
        got = self.ask("Ollama Cloud", [("api_key", "API key", True, True)],
                       note="Used by OpenCode for Ollama Cloud models.")
        if got:
            self.run("Saving…", lambda: setup.set_values("ollama", got), RELOGIN)

    def edit_restic(self):
        rs = self.st["status"]["restic"]  # a field is required while its own value is unset
        have = rs["repository"]["set"]
        got = self.ask("Backups (restic)",
                       [("repository", "Repository, e.g. sftp:nas:/backup/fw13", False, not have),
                        ("password", "Repository password", True, not rs["password"]["set"])],
                       note=("Leave a field blank to keep its current value. Changing the password here doesn't "
                             "change the repository's own password." if have else
                             "A new repository gets this password; keep a copy somewhere safe — without it the "
                             "backups can't be read. The first backup copies your whole home folder."),
                       generate="password")
        if not got:
            return
        self.restic = None

        def work():
            ok, msg = setup.set_values("restic", got)
            if not ok:
                return ok, msg
            self.restic = setup.restic_test()
            state, msg = self.restic
            # A new setup turns the daily backup on; finishing an incomplete one does unless it was turned off.
            if state == "ok" and (not have or (not rs["password"]["set"] and not store.get("restic_timer_off"))):
                ok, note = setup.backup_timer(True)
                return ok, "Saved and connected — daily backup is on" if ok else note
            if state == "ok":
                return True, "Saved and connected"
            return state == "missing", f"Saved — {msg[:1].lower()}{msg[1:]}" if state == "missing" else \
                f"Saved, but: {msg}"
        self.run("Saving and connecting…", work)

    def remove(self, table):
        if table == "restic":
            self.restic = None
            self.stop_poll()
        self.run("Removing…", lambda: setup.remove(table),
                 "Removed — log out and back in" if table != "restic" else "Removed; daily backup is off")

    # --- restic actions -----------------------------------------------------
    def restic_test(self):
        def work():
            self.restic = setup.restic_test()
            return True, ""
        self.run("Connecting to the repository…", work)

    def restic_init(self):
        def work():
            ok, msg = setup.restic_init()
            if not ok:
                return ok, msg
            self.restic = setup.restic_test()
            if self.restic[0] == "ok" and not store.get("restic_timer_off"):
                setup.backup_timer(True)
            return True, "Repository created"
        self.run("Initialising the repository…", work)

    def on_timer(self, _sw, on):
        if not self.busy:
            self.run("Turning the daily backup on…" if on else "Turning the daily backup off…",
                     lambda: setup.backup_timer(on))
        return True  # the switch is rebuilt from what systemd reports

    def backup_now(self):
        def done(res):
            ok, msg = res
            if ok:
                self.start_poll()
            else:
                self.set_status(msg, "bad")
            self.render()
        self.set_status("Starting the backup…")
        bg(setup.backup_now, done)

    def start_poll(self):
        if not self.poll:
            self.poll = GLib.timeout_add_seconds(2, self.on_poll)

    def stop_poll(self):
        if self.poll:
            GLib.source_remove(self.poll)
            self.poll = None

    def on_poll(self):
        bg(setup.backup_state, self.got_backup, fail=lambda _e: None)
        return True

    def got_backup(self, b):
        if b is None or self.st is None or not self.poll:
            return False
        self.st["backup"] = b
        if not b["running"]:
            self.stop_poll()
            good = b["result"] == "success"
            self.set_status("Backup finished" if good else "Backup failed — see View log", "dim" if good else "bad")
        if not (self.busy or self.confirming):
            self.render()
        return False

    # --- shell ---------------------------------------------------------------
    def set_shell(self, path):
        if not path:
            return

        def work():
            ok, msg = setup.set_shell(path)
            if ok is None:  # no AccountsService (Minimal): sudo usermod in a terminal
                GLib.idle_add(lambda: launch(*msg) and False)
                return True, "Finish in the terminal (sudo asks for your password), then reopen this page"
            return ok, msg
        self.run("Changing the login shell…", work, "Login shell changed — new logins and terminals use it")

    def closing(self):
        self.stop_poll()


def build():
    return Fw13Page()
