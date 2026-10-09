# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## fw13-hypr

ML4W-style **installer** (`install.sh`) that adds a Hyprland (uwsm) desktop on top of **any regular Fedora ≥44** — Workstation/GNOME, KDE, spins, or Minimal — for a **Framework Laptop 13, AMD Ryzen AI 9 HX 370** (Radeon 890M, MediaTek MT7925). No custom image/ISO. Fedora only (user decision). Atomic editions are refused in preflight.

## Hard rules

1. **Ask before adding ANY package**, including weak deps, helpers, and "obvious" utilities. Propose name + source + why; wait for approval. Never slip one in through a script (e.g. `jq`, `libnotify`, `rsync`) — use what's already installed (see `fw-notify` using `gdbus`).
2. **Prefer official sources**, in this order: Fedora repos → vendor's own repo (Microsoft, mise) → RPM Fusion → COPR → upstream installer → Flathub. State the source tier when proposing.
3. **Weak deps off for our installs only** (`dnf --setopt=install_weak_deps=False`); never change the user's global dnf.conf. Anything needed must be listed in `packages/*.txt`. Keep the explicit firmware lines (amd-gpu, amd-ucode, mt7xxx) — on Minimal they'd otherwise be missing.
3a. **Never remove or replace the user's existing stack** (DE, display manager, power daemon). Detect and adapt. **One exception (user decision): the login screen is always greetd + tuigreet** (`15-login.txt`); an existing GDM/SDDM is disabled, not removed (`KEEP_DM=1` keeps it and only adds the session; GDM 50 has no DefaultSession key, an older line is removed). power-profiles-daemon present → skip tuned (`61-power.txt`). Only sanctioned swap: ffmpeg-free → ffmpeg (`--allowerasing`).
3b. **Idempotent**: re-running must be safe.
4. **Never install apps on Flathub** without per-app approval. The remote is added; the only approved app is LocalSend (see Package sources), everything else stays off.
5. **No secrets in git.** Credentials (Chromium OAuth, restic repo/password) come from chezmoi `promptStringOnce` in `dotfiles/.chezmoi.toml.tmpl` and render into `private_` (0600) files.
6. **Timeshift = whole system + /home, mode auto-detected** in `fw-timeshift-setup`: btrfs mode iff `/` is subvol `@`; otherwise rsync (Fedora's default `root`/`home` names). Scheduled by **Timeshift's own /etc/cron.d jobs** (it writes them itself when a `schedule_*` flag is on; cronie is a dependency of Fedora's package) — user decision; the old fw-timeshift timer is removed by install.sh. Timeshift's restore can't mount Fedora's `root` subvolume (it hard-codes `@`), so rsync-mode restores go through `fw-timeshift-restore`.
7. Hardware is AMD. Do not add Intel-specific packages/params.
8. Visual style: clean/minimal, Tokyo Night by default or colours from the wallpaper (matugen, `fw13.theme`), flat borders, thin bar. **Keys stay simple and conventional** — do not port Omarchy's (or any distro's) keymap. Omarchy-*style* bar menus are OK (user decision): bar icons open fuzzel menus (`fw-control-center [section]`, `fw-system-menu`), not big GUI apps; GUI tools stay on right/middle-click.

## Layout

```
install.sh                 preflight → repos → packages → system files → login/power → fingerprint/services → user phase → report
                           flags: --yes --ci --system-only --user-only; env: HYPR_COPR, REPO_URL, CHECKOUT
packages/NN-*.txt          one package per line, '#' comments on their own line only (pkgs() splits on whitespace); 15-login, 61-power conditional; matugen is installed separately as `'matugen >= 4'` (needs the COPR)
repos/*.repo               vendor repos (vscode, mise)
rpm/                       specs we build locally: telegram-desktop-official.spec (build_telegram_rpm in install.sh)
system/usr/local/bin/      fw-timeshift-setup, fw-timeshift-restore (rsync-mode restore on Fedora's root/home btrfs: snapshot root, rsync onto
                           the copy, swap by rename; kernels side by side + grubby; holds Timeshift's lock; undo), fw-health-root
system/etc/systemd/system/ fw-health-root.{service,timer} (:30 hourly → /var/lib/fw13/health-root.json, 0644; install.sh copies the folder only if it has files)
dotfiles/                  chezmoi source (.chezmoiroot = dotfiles)
  .chezmoi.toml.tmpl       one-time prompts (secrets) — never commit values
  dot_local/lib/fw13/       shared Python library → ~/.local/lib/fw13 (scripts sys.path.insert ~/.local/lib): hypr (Lua hyprctl helpers),
                           displays, power, sound, net (nmcli; passwd-file, never argv), bt (org.bluez via Gio), hyprsettings (settings.lua: verify-config in a temp copy, then write + hl.config live), idle (owns hypridle.conf), system, store (~/.config/fw13/settings.json), ui_theme (flat CSS), ui_display, pages/* (incl. `jarvis`: Settings → Jarvis, store `jarvis_model`/`jarvis_effort` → `jarvis.claude_args()` = `--model`/`--effort` for the panel's `claude` runs, Continue in terminal and `fw-jarvis` via `python3 -m fw13.jarvis`),
                           theme (ensure_files also rewrites a generated file of ours that lacks a line in theme.REQUIRED; palette: matugen from the wallpaper or TOKYO_NIGHT → generated files in ~/.config/fw13/theme/ + live reload;
                           GTK: "fw13" theme in ~/.local/share/themes = adw-gtk3[-dark] + gtk3/gtk4.css, set via GSettings only inside Hyprland,
                           `python3 -m fw13.theme session-start|session-end` from fw-theme-session.service; Qt: qt6ct via uwsm/env-hyprland),
                           wallpaper (library ~/Pictures/Wallpapers, thumbnails ~/.cache/fw13/thumbs, effects; renders desktop.jpg/lock.jpg
                           from the untouched original, palette from a small copy of it; hyprpaper restart = pkill -x + uwsm app)
                           setup (fw13 page backend: chezmoi.toml [data.chromium|restic|ollama] rewritten 0600 under a lock + `chezmoi apply
                           --exclude=scripts <targets>`; files removed only when unchanged from what chezmoi wrote; restic via env= only, timer
                           state in store `restic_timer_off` honoured by run_onchange_after_restic-enable; shell via AccountsService SetShell),
                           defaultapps (each Hyprland login + chezmoi run_onchange: GNOME apps and other-desktop-only entries hidden via
                           NoDisplay copies in ~/.local/share/fw13/hyprland/applications (our own fw-calc/fw-emoji entries there carry no marker and are left alone), on XDG_DATA_DIRS for Hyprland only (uwsm/env-hyprland;
                           fuzzel ignores NotShowIn/OnlyShowIn); defaults in ~/.config/hyprland-mimeapps.list: Thunar, Chromium, GNOME viewers;
                           types the user set in mimeapps.list are left out)
                           power (+ tuning(): read-only CPU driver/EPP/boost/platform profile/ABM/tuned readout), als (light sensor via
                           SensorProxy + auto-brightness curve), health (fw-hwcheck hardware group + fw-health daily group; expected Framework
                           values in one table, non-Framework → SKIP), notify (shared notification + session_env; crash-watch and health use it),
                           setup also owns optional [data.restic_creds] (S3 keys only; AWS_* rendered only for s3:; restic-backup.service is a
                           template adding -o sftp.args=-oBatchMode=yes for sftp:)
                           Generated in ~/.config/fw13/theme/: hypr.lua hyprlock.conf waybar.css fuzzel.ini mako kitty.conf (create_ seeds)
                           + gtk3.css gtk4.css qt6ct-colors.conf fcitx5-theme.conf framework-logo.svg (written by theme.init/ensure_files) + desktop.jpg lock.jpg (fw13.wallpaper)
                           Session-only app theming (session_start/session_end, Hyprland only): fcitx5 Theme=fw13 in classicui.conf (old values
                           restored), Chromium extensions.theme.system_theme=1 once per profile when unset and Chromium isn't running (opt-in Appearance switch `chromium_gtk_force` also replaces a theme the user chose and writes `~/.config/fw13/theme/chromium-policy.json` = BrowserThemeColor from the accent, re-read live via SIGHUP; install.sh links `/etc/chromium/policies/managed/fw13-theme.json` to it), VS Code
                           workbench.colorCustomizations (on by default, Appearance switch, strict JSON only, removed at logout); TUIs follow kitty's 16 colours
                           (btop color_theme TTY via create_btop.conf, FZF_DEFAULT_OPTS/BAT_THEME in uwsm/env-hyprland)
                           Colour rule: colour literals live only in theme.py TOKYO_NIGHT, the create_ seeds of ~/.config/fw13/theme/ and hypr/theme.lua's
                           documented fallback (used only if the generated hypr.lua is missing or broken);
                           base configs (hypr, hyprlock, waybar, fuzzel, mako, kitty, ui_*) include the generated files, never hard-code hex
  dot_config/hypr/*.lua    hyprland.lua require()s monitors/displays/autostart/looknfeel(+theme)/input/windows/bindings/settings (fw-settings-generated)/local (Lua config; hyprlock/hypridle/hyprpaper keep their own .conf)
  dot_local/bin/executable_fw-*   capture, record, nightlight, notify, clipboard (SUPER+V: cliphist pick → paste via hl.dsp.send_shortcut; key must be lowercase `v`), clip-key (SUPER+C copy / SUPER+X cut: send_shortcut to the focused window, Ctrl+Shift+C in terminals, no cut there; VS Code moved to SUPER+SHIFT+C), system-menu, control-center, power-panel, display-panel (layer-shell popup around fw13.ui_display), settings (Settings app: Gtk.Application, single instance, `fw-settings [page] [--toggle]`; pages in lib/fw13/pages), workspaces (Python daemon: per-screen ranges eDP 1–9, others 11–19…; SUPER+N goes through it; login layout), jarvis (SUPER+A → jarvis-panel: layer-shell Ask box, inline answers via `claude -p --output-format stream-json`, read-only tools + `--add-dir /` with secret paths denied; changes only as ```jarvis-action``` JSON cards (What/Why/How, Run/Skip) that the panel runs with `bash -c` on Run (root cards via `pkexec`, `sudo` stripped: polkit asks for password/fingerprint) and feeds back via `--resume`; each answer may end with a ```jarvis-followups``` JSON list shown as buttons, and Enter while an answer is open asks a follow-up in the same conversation ("New question" starts afresh); Continue = `claude --resume <session>`; `fw-jarvis repo|crash|open|diagnose|menu` for the terminal sessions; working folder ~/jarvis (created if missing; all agent runs and "Continue in terminal" start there) with the briefing dotfiles/jarvis/AGENTS.md incl. the What/Why/How rule for root actions), crash-watch (user service; journal coredump/unit-failed → notify → Diagnose), opencode (Ollama server list → generated ~/.config/fw-opencode/opencode.json via OPENCODE_CONFIG), claude-limits (statusLine rate_limits → bar; settings via dot_claude/modify_settings.json), menu-anchor (bar menus open below the clicked icon via FW_BAR=1), wallpaper (SUPER+W: layer-shell picker strip, pidfile toggle; `fw-wallpaper set|add|effects` CLI), osd (volume/mic/brightness popup: mako progress hint, id reused via $XDG_RUNTIME_DIR/fw-osd.id, [app-name=fw-osd] shown under DND), notifications (bar bell custom/notifications, signal 12 from mako on-notify; fuzzel history/DND/dismiss all; unread via store notif_seen {mako pid:starttime, id}), calc (SUPER+=: fuzzel loop over qalc -t, argv only; ast fallback), emoji (SUPER+.: GTK3 emoji data, paste like clipboard), autobrightness (user service, off by default; manual change pauses until wake/login; hypridle hooks pause/resume), hwcheck (--first-login once, store hwcheck_shown) and health (fw-health.timer 15 min after login then daily; reports in ~/.local/state/fw13/health/, keep 14; notify only on changed findings or weekly; --timer only under systemd), warp-panel (bar cloud icon: layer-shell WARP panel over lib/fw13/warp.py = `warp-cli --accept-tos -j`, only after the user accepted Cloudflare's ToS in the panel (store `warp_tos`); `--bar` JSON, signal 11; `--toggle` on right-click; Zero Trust join via `registration new <team>` + browser; "Consumer only" settings greyed/hidden for Zero Trust; Cloudflare's own warp-taskbar hidden in Hyprland via `dot_config/autostart` NotShowIn)
docs/FIRST-INSTALL.md      what a fresh Framework install looks like + Stage 7 hardware checklist; CONTRIBUTING.md (dev quick start, roadmap), CODE_OF_CONDUCT.md
.github/workflows/test.yml lint (shellcheck + config syntax) → install (./install.sh --ci in fedora:44, weekly cron too)
                           → screenshot (experimental, continue-on-error: vkms + .github/ci-screenshot.sh, uploads shot/)
```

## Package sources (current)

| Source | Notes |
|---|---|
| Fedora | everything not listed below (incl. qalculate for fw-calc, udisks2 + dnf5-plugins for fw-health, fuse3 for `restic mount`) (swayosd is not packaged for Fedora 44 → dropped; volume/brightness keys use wpctl/brightnessctl) |
| COPR `lionheartp/Hyprland` | hyprland, hyprlock, hypridle, hyprpaper, hyprpolkitagent, hyprpicker, hyprsunset, hyprland-guiutils, xdg-desktop-portal-hyprland. Hyprland was **retired from Fedora in F43** and the COPR only builds F44+ (hence the ≥44 preflight); swap via `HYPR_COPR=… ./install.sh` (`HYPR_COPR=` = Fedora only) |
| COPR `lionheartp/Hyprland` (theme) | matugen 4.2.0 (wallpaper → Material You palette). Not from Fedora: F44 ships 3.1.0, which rejects the engine's `--prefer`/`-t scheme-*` flags. Installed as `'matugen >= 4'` only when `HYPR_COPR` is set (a COPR without 4.x fails loudly); otherwise the theme stays Tokyo Night |
| Fedora (AI) | ollama (system service, local models for OpenCode) |
| Fedora (dev) | podman, distrobox, gh (GitHub CLI) |
| RPM Fusion | steam, steam-devices, ffmpeg, gstreamer1-plugins-bad-freeworld |
| Vendor | `code` (packages.microsoft.com), `mise` (mise.jdx.dev/rpm), `cloudflare-warp` (pkg.cloudflareclient.com, `repos/cloudflare-warp.repo`, `packages/97-warp.txt` + its hard dep `nss-tools` from Fedora; installer enables `warp-svc`) |
| mise (user, `~/.config/mise/config.toml`) | node LTS, chezmoi, starship, opencode (self-update off) |
| Built from source as RPMs (owner's repos) | **Citadel** outbound firewall: `citadel` (github.com/NeatOuk/citadel-app, `main`, release stamped `.gitYYYYMMDD.<sha>`) + `citadel-helper` (github.com/NeatOuk/citadel-helper, tag `v1.3.2`), built by `build_citadel_rpm` in install.sh with their own .spec files (no prebuilt packages exist); build tools + PySide6 in `packages/95-citadel.txt`. Override with `CITADEL_APP_REF`/`CITADEL_HELPER_REF`. User phase enables `citadel.service` and `citadel enforce on` (user decision). The helper's polkit rule lets wheel use it without a password (by design). |
| Repackaged official binary (telegram.org) | **Telegram Desktop** (user decision: the official build, as an RPM). `build_telegram_rpm` reads the version from telegram.org's download redirect, downloads the tarball (no checksum is published: HTTPS only) plus the launcher entry, D-Bus service and icons from github.com/telegramdesktop/tdesktop at the same tag, and builds `telegram-desktop-official` (`/opt/telegram`, `/usr/bin/Telegram`, `Conflicts: telegram-desktop`). Its self-updater is off via `externalupdater.d`; re-running install.sh rebuilds when telegram.org has a newer version, otherwise it's a no-op |
| Flathub (user remote) | **LocalSend** `org.localsend.localsend_app` (user decision, the only Flathub app; not in Fedora). Installed with `flatpak install --user`; the installer does not open its port 53317 (user decision), so the laptop can send but not receive |
| Upstream installer | Claude Code via `curl -fsSL https://claude.ai/install.sh \| bash` → `~/.local/bin/claude`, self-updating. Not via mise npm: that skipped the package's postinstall, so no binary |

Declined by the user — do not re-propose unless asked: `mesa-va-drivers-freeworld`, toolbox, Docker CE, ProtonUp-Qt, Nerd Fonts, snapper/btrfs-assistant, Qt5 removal, CJK font removal, swayosd COPR, Arch support, bootc/ISO image, a single-process shell (Quickshell/AGS/DankMaterialShell replacing Waybar/fuzzel/mako/our panels), and the other ideas from the Oct 2026 comparison with ML4W/JaKooLit/Omarchy/end-4/HyDE/Caelestia (overview with live previews, theme gallery, keybind cheat sheet, OCR, DDC/CI brightness, clamshell handling, bar weather/reminders): the current design stays.

## Commands

```bash
./install.sh                     # full install (interactive)
./install.sh --ci                # what CI runs in a fedora container (root, non-interactive)
./install.sh --user-only         # re-apply dotfiles/mise/shell only
T=$(mktemp -d); HOME=$T XDG_CONFIG_HOME=$T/.config XDG_DATA_HOME=$T/.local/share XDG_STATE_HOME=$T/.local/state XDG_CACHE_HOME=$T/.cache \
  chezmoi init --source=$PWD --apply --exclude=scripts   # dry-run dotfiles into a throwaway home (isolate every XDG dir)
XDG_RUNTIME_DIR=$(mktemp -d) Hyprland --verify-config -c "$T/.config/hypr/hyprland.lua"   # check the rendered Lua config
# lint, as CI does: split scripts by shebang, shellcheck the bash ones, ast-parse the Python ones
sh=() py=()
for f in install.sh system/usr/local/bin/* dotfiles/dot_local/bin/executable_*; do
  case "$(head -1 "$f")" in *python3*) py+=("$f") ;; *) sh+=("$f") ;; esac
done
shellcheck -S warning "${sh[@]}"
python3 -c 'import ast,sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]' "${py[@]}" $(find dotfiles/dot_local/lib -name '*.py')
```

There is no unit-test suite: verification is lint + dry-run + CI install (`.github/workflows/test.yml`) + the hardware checklist in `docs/FIRST-INSTALL.md`. Local dotfile edits are not what `chezmoi update` applies (it pulls the pushed repo), so push before testing on the machine. `CONTRIBUTING.md` has the commit conventions (`feat(area):`, `fix(area):`, `chore:`, `docs:`; update README and this file in the same change) and the roadmap.

**Commits (user decision):** commit (and push) every change as soon as it is made, one change per commit; never add `Co-Authored-By` or other attribution/session trailers to commit messages.

Package-resolution failures are intended to fail loudly — fix the name (and ask the user if it means a source change); never add `--skip-unavailable`.

## Conventions

- **Hyprland config is Lua** (hyprlang `.conf` deprecated since 0.55, dropped soon). API for the installed version: `/usr/share/hypr/stubs/hl.meta.lua`; example: `/usr/share/hypr/hyprland.lua`. `hl.bind("SUPER + X", hl.dsp.…, { repeating/locked/mouse = true })`, `hl.window_rule({ name, match = { class = … }, float = true })`, `hl.on("hyprland.start", …)` for autostart.
- **hyprctl in Lua mode**: `hyprctl dispatch '<lua dispatcher>'` (old `dispatch workspace 2` → "Invalid dispatcher"); `hyprctl eval '<lua>'` replaces `keyword`/`--batch`. Quote Lua strings from Python with `json.dumps`. The config manager is chosen at Hyprland start: switching .conf↔.lua needs a re-login, not `hyprctl reload`.
- `Hyprland --verify-config -c <hyprland.lua>` checks syntax + unknown keys (not dispatcher args — test those, see below).
- **Live tests never act on the active window** (it's the user's terminal): always pass `window = "address:0x…"` for a verified throwaway window, and never selector-less close/move/scratchpad.
- **Stop processes by PID, never `pkill -f <pattern>`** from an agent's shell: the tool runs `bash -c '<whole command>'`, so the pattern matches that shell and kills it. Read the helper's pidfile in `$XDG_RUNTIME_DIR` and check `/proc/$pid/cmdline`, or use `pgrep -x <name>`.
- **App windows tile** (user decision): new apps and tools get no float/size/center window rule; only inherent popups (pavucontrol, blueman-manager, progress dialogs) and Jarvis task windows float. Ask before adding a float rule.
- Launch GUI apps through uwsm: `uwsm app -- <cmd>`; fuzzel uses `--launch-prefix="uwsm app -- "`.
- Session env goes in `dotfiles/dot_config/environment.d/` (read by systemd --user), not Hyprland `env =`.
- Icons: **Font Awesome 6 Free/Brands only** (no Nerd Font codepoints ≥ U+F0000). One exception (user decision): the bar's launcher button is Framework's gear, `framework-logo.svg` generated by fw13.theme in the accent colour (path from Simple Icons, CC0) and drawn as a waybar CSS background. Fonts: JetBrains Mono, Noto (incl. Khmer).
- Notifications from scripts: `fw-notify "title" "body"` (gdbus), not `notify-send`.
- **Theme files** live in `~/.config/fw13/theme/` and base configs reference them (`source`/`@import`/`include`; hyprpaper/hyprlock read desktop.jpg/lock.jpg there); a new themed app gets a generated file there, not colours in its config. A user's own `~/.config/gtk-4.0/gtk.css` (no fw13 marker line) is never clobbered. GSettings/gtk.css changes happen only inside Hyprland and are restored at logout (rule 3a: GNOME/KDE share the account).
- chezmoi naming: `dot_`, `private_`, `executable_`, `create_` (create-once, e.g. `hypr/local.lua`, `hypr/displays.lua`, `fcitx5/profile`), `modify_` (keeps distro `.bashrc`), `run_onchange_after_`. `~/.config` has exactly one source dir (`dot_config/`) — put private subdirs under it as `private_<name>`.
- Prompt strings in `.chezmoi.toml.tmpl` must not contain commas (breaks `--promptString`), and are duplicated verbatim in `install.sh`'s CI `--promptString` args — change both together.
- Secret-dependent files are skipped via `dotfiles/.chezmoiignore` when their prompt was left blank (Chromium OAuth env, restic env + timer). New secret-backed files need a matching ignore rule.
- Outside `--ci`, the user phase runs `chezmoi init --apply "$REPO_URL"` then `chezmoi update --init` (re-runs pull new dotfiles and re-render chezmoi.toml from the newer template; promptStringOnce keeps values, a new key prompts once even with `--yes`; tables without a prompt, like `restic_creds`, are written back by the template) — it applies the **pushed** repo, not the local tree. Test local dotfile edits with the temp-HOME dry-run in Commands.
- Scripts are bash unless they need a GUI (`fw-display-panel`: Python + GTK3 + GtkLayerShell; pin `gi.require_version` for Gtk **and** Gdk 3.0 or Gdk 4 loads). Shell scripts: `#!/usr/bin/env bash`, `set -euo pipefail`; must pass `shellcheck -S warning`. Build package arg lists with `mapfile`, not `$(...)`. Wrap `eval "$(mise activate bash)"` in `set +u`.

## Verification before declaring done

- `bash -n` on every script; JSON-parse `waybar/config.jsonc` (strip `//` comments) and TOML-parse mise/starship — the python snippet in the CI `lint` job does both.
- `Hyprland --verify-config` on the rendered `hyprland.lua`; duplicate-keybind check via `hyprctl -j binds` (72 binds today).
- chezmoi dry-run into a temp HOME, both with secrets blank and filled.
- CI green on fedora:44; read the install report in the job summary (added count, size, top 25, Hypr provenance).
- Hardware-only checks (cannot be done in CI/VM): MT7925 Wi-Fi/BT, VA-API (`vainfo` via distrobox), fingerprint, suspend/resume, tuned-ppd profiles, ambient light sensor, Steam + gamescope.

## Known unverified

Package names resolved on Fedora 44 + lionheartp in the first CI build (only swayosd failed → dropped). Unverified: whether the COPR ships `hyprland-uwsm.desktop` (installer adds one in /usr/local/share/wayland-sessions if not), Timeshift rsync filter behaviour on a real system, Telegram honouring `externalupdater.d` (no update prompt) and not adding its own `org.telegram.desktop._<hash>.desktop` next to the packaged one.

## License

GPL-3.0-only (`LICENSE`). Third-party packages keep their own licenses.
