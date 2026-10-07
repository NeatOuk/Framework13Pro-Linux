# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## fw13-hypr

ML4W-style **installer** (`install.sh`) that adds a Hyprland (uwsm) desktop on top of **any regular Fedora ≥44** — Workstation/GNOME, KDE, spins, or Minimal — for a **Framework Laptop 13, AMD Ryzen AI 9 HX 370** (Radeon 890M, MediaTek MT7925). No custom image/ISO. Fedora only (user decision). Atomic editions are refused in preflight.

## Hard rules

1. **Ask before adding ANY package**, including weak deps, helpers, and "obvious" utilities. Propose name + source + why; wait for approval. Never slip one in through a script (e.g. `jq`, `libnotify`, `rsync`) — use what's already installed (see `fw-notify` using `gdbus`).
2. **Prefer official sources**, in this order: Fedora repos → vendor's own repo (Microsoft, mise) → RPM Fusion → COPR → upstream installer → Flathub. State the source tier when proposing.
3. **Weak deps off for our installs only** (`dnf --setopt=install_weak_deps=False`); never change the user's global dnf.conf. Anything needed must be listed in `packages/*.txt`. Keep the explicit firmware lines (amd-gpu, amd-ucode, mt7xxx) — on Minimal they'd otherwise be missing.
3a. **Never remove or replace the user's existing stack** (DE, display manager, power daemon). Detect and adapt: existing DM → just add the session; none → greetd+tuigreet (`15-login.txt`). power-profiles-daemon present → skip tuned (`61-power.txt`). Only sanctioned swap: ffmpeg-free → ffmpeg (`--allowerasing`).
3b. **Idempotent**: re-running must be safe.
4. **Never install apps on Flathub** without per-app approval. The remote is added; it stays empty by default.
5. **No secrets in git.** Credentials (Chromium OAuth, restic repo/password) come from chezmoi `promptStringOnce` in `dotfiles/.chezmoi.toml.tmpl` and render into `private_` (0600) files.
6. **Timeshift = whole system + /home, mode auto-detected** in `fw-timeshift-setup`: btrfs mode iff `/` is subvol `@`; otherwise rsync (Fedora's default `root`/`home` names). Scheduled by `fw-timeshift.timer` (`timeshift --check`), not cron.
7. Hardware is AMD. Do not add Intel-specific packages/params.
8. Visual style: clean/minimal, Tokyo Night by default or colours from the wallpaper (matugen, `fw13.theme`), flat borders, thin bar. **Keys stay simple and conventional** — do not port Omarchy's (or any distro's) keymap. Omarchy-*style* bar menus are OK (user decision): bar icons open fuzzel menus (`fw-control-center [section]`, `fw-system-menu`), not big GUI apps; GUI tools stay on right/middle-click.

## Layout

```
install.sh                 preflight → repos → packages → system files → login/power → fingerprint/services → user phase → report
                           flags: --yes --ci --system-only --user-only; env: HYPR_COPR, REPO_URL, CHECKOUT
packages/NN-*.txt          one package per line, '#' comments on their own line only (pkgs() splits on whitespace); 15-login, 61-power conditional; matugen is installed separately as `'matugen >= 4'` (needs the COPR)
repos/*.repo               vendor repos (vscode, mise)
system/usr/local/bin/      fw-timeshift-setup
system/etc/systemd/system/ fw-timeshift.{service,timer}
dotfiles/                  chezmoi source (.chezmoiroot = dotfiles)
  .chezmoi.toml.tmpl       one-time prompts (secrets) — never commit values
  dot_local/lib/fw13/       shared Python library → ~/.local/lib/fw13 (scripts sys.path.insert ~/.local/lib): hypr (Lua hyprctl helpers),
                           displays, power, sound, net (nmcli; passwd-file, never argv), bt (org.bluez via Gio), hyprsettings (settings.lua: verify-config in a temp copy, then write + hl.config live), idle (owns hypridle.conf), system, store (~/.config/fw13/settings.json), ui_theme (flat CSS), ui_display, pages/*,
                           theme (palette: matugen from the wallpaper or TOKYO_NIGHT → generated files in ~/.config/fw13/theme/ + live reload;
                           GTK: "fw13" theme in ~/.local/share/themes = adw-gtk3[-dark] + gtk3/gtk4.css, set via GSettings only inside Hyprland,
                           `python3 -m fw13.theme session-start|session-end` from fw-theme-session.service; Qt: qt6ct via uwsm/env-hyprland),
                           wallpaper (library ~/Pictures/Wallpapers, thumbnails ~/.cache/fw13/thumbs, effects; renders desktop.jpg/lock.jpg
                           from the untouched original, palette from a small copy of it; hyprpaper restart = pkill -x + uwsm app)
                           Generated in ~/.config/fw13/theme/: hypr.lua hyprlock.conf waybar.css fuzzel.ini mako kitty.conf (create_ seeds)
                           + gtk3.css gtk4.css qt6ct-colors.conf (written by theme.init/ensure_files) + desktop.jpg lock.jpg (fw13.wallpaper)
                           Colour rule: colour literals live only in theme.py TOKYO_NIGHT, the create_ seeds of ~/.config/fw13/theme/ and hypr/theme.lua's
                           documented fallback (used only if the generated hypr.lua is missing or broken);
                           base configs (hypr, hyprlock, waybar, fuzzel, mako, kitty, ui_*) include the generated files, never hard-code hex
  dot_config/hypr/*.lua    hyprland.lua require()s monitors/displays/autostart/looknfeel(+theme)/input/windows/bindings/settings (fw-settings-generated)/local (Lua config; hyprlock/hypridle/hyprpaper keep their own .conf)
  dot_local/bin/executable_fw-*   capture, record, nightlight, notify, clipboard (SUPER+V: cliphist pick → paste via hl.dsp.send_shortcut; key must be lowercase `v`), system-menu, control-center, power-panel, display-panel (layer-shell popup around fw13.ui_display), settings (Settings app: Gtk.Application, single instance, `fw-settings [page] [--toggle]`; pages in lib/fw13/pages), workspaces (Python daemon: per-screen ranges eDP 1–9, others 11–19…; SUPER+N goes through it; login layout), jarvis (agent launcher; briefing in dot_local/share/jarvis/AGENTS.md), crash-watch (user service; journal coredump/unit-failed → notify → Diagnose), opencode (Ollama server list → generated ~/.config/fw-opencode/opencode.json via OPENCODE_CONFIG), claude-limits (statusLine rate_limits → bar; settings via dot_claude/modify_settings.json), menu-anchor (bar menus open below the clicked icon via FW_BAR=1), wallpaper (SUPER+W: layer-shell picker strip, pidfile toggle; `fw-wallpaper set|add|effects` CLI), warp-panel (bar cloud icon: layer-shell WARP panel over lib/fw13/warp.py = `warp-cli --accept-tos -j`, only after the user accepted Cloudflare's ToS in the panel (store `warp_tos`); `--bar` JSON, signal 11; `--toggle` on right-click; Zero Trust join via `registration new <team>` + browser; "Consumer only" settings greyed/hidden for Zero Trust; Cloudflare's own warp-taskbar hidden in Hyprland via `dot_config/autostart` NotShowIn)
.github/workflows/test.yml lint (shellcheck + config syntax) → install (./install.sh --ci in fedora:44, weekly cron too)
                           → screenshot (experimental, continue-on-error: vkms + .github/ci-screenshot.sh, uploads shot/)
```

## Package sources (current)

| Source | Notes |
|---|---|
| Fedora | everything not listed below (swayosd is not packaged for Fedora 44 → dropped; volume/brightness keys use wpctl/brightnessctl) |
| COPR `lionheartp/Hyprland` | hyprland, hyprlock, hypridle, hyprpaper, hyprpolkitagent, hyprpicker, hyprsunset, hyprland-guiutils, xdg-desktop-portal-hyprland. Hyprland was **retired from Fedora in F43** and the COPR only builds F44+ (hence the ≥44 preflight); swap via `HYPR_COPR=… ./install.sh` (`HYPR_COPR=` = Fedora only) |
| COPR `lionheartp/Hyprland` (theme) | matugen 4.2.0 (wallpaper → Material You palette). Not from Fedora: F44 ships 3.1.0, which rejects the engine's `--prefer`/`-t scheme-*` flags. Installed as `'matugen >= 4'` only when `HYPR_COPR` is set (a COPR without 4.x fails loudly); otherwise the theme stays Tokyo Night |
| Fedora (AI) | ollama (system service, local models for OpenCode) |
| Fedora (dev) | podman, distrobox, gh (GitHub CLI) |
| RPM Fusion | steam, steam-devices, ffmpeg, gstreamer1-plugins-bad-freeworld |
| Vendor | `code` (packages.microsoft.com), `mise` (mise.jdx.dev/rpm), `cloudflare-warp` (pkg.cloudflareclient.com, `repos/cloudflare-warp.repo`, `packages/97-warp.txt` + its hard dep `nss-tools` from Fedora; installer enables `warp-svc`) |
| mise (user, `~/.config/mise/config.toml`) | node LTS, chezmoi, starship, opencode (self-update off) |
| Built from source as RPMs (owner's repos) | **Citadel** outbound firewall: `citadel` (github.com/NeatOuk/citadel-app, `main`, release stamped `.gitYYYYMMDD.<sha>`) + `citadel-helper` (github.com/NeatOuk/citadel-helper, tag `v1.3.2`), built by `build_citadel_rpm` in install.sh with their own .spec files (no prebuilt packages exist); build tools + PySide6 in `packages/95-citadel.txt`. Override with `CITADEL_APP_REF`/`CITADEL_HELPER_REF`. User phase enables `citadel.service` and `citadel enforce on` (user decision). The helper's polkit rule lets wheel use it without a password (by design). |
| Upstream installer | Claude Code via `curl -fsSL https://claude.ai/install.sh \| bash` → `~/.local/bin/claude`, self-updating. Not via mise npm: that skipped the package's postinstall, so no binary |

Declined by the user — do not re-propose unless asked: `mesa-va-drivers-freeworld`, toolbox, Docker CE, ProtonUp-Qt, Nerd Fonts, snapper/btrfs-assistant, Qt5 removal, CJK font removal, swayosd COPR, Arch support, bootc/ISO image.

## Commands

```bash
./install.sh                     # full install (interactive)
./install.sh --ci                # what CI runs in a fedora container (root, non-interactive)
./install.sh --user-only         # re-apply dotfiles/mise/shell only
HOME=$(mktemp -d) chezmoi init --source=$PWD --apply   # dry-run dotfiles into a throwaway home
shellcheck -S warning install.sh system/usr/local/bin/* $(grep -L python3 dotfiles/dot_local/bin/executable_*)   # bash only; CI ast-parses the Python ones
```

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
- Icons: **Font Awesome 6 Free/Brands only** (no Nerd Font codepoints ≥ U+F0000). Fonts: JetBrains Mono, Noto (incl. Khmer).
- Notifications from scripts: `fw-notify "title" "body"` (gdbus), not `notify-send`.
- **Theme files** live in `~/.config/fw13/theme/` and base configs reference them (`source`/`@import`/`include`; hyprpaper/hyprlock read desktop.jpg/lock.jpg there); a new themed app gets a generated file there, not colours in its config. A user's own `~/.config/gtk-4.0/gtk.css` (no fw13 marker line) is never clobbered. GSettings/gtk.css changes happen only inside Hyprland and are restored at logout (rule 3a: GNOME/KDE share the account).
- chezmoi naming: `dot_`, `private_`, `executable_`, `create_` (create-once, e.g. `hypr/local.lua`, `hypr/displays.lua`, `fcitx5/profile`), `modify_` (keeps distro `.bashrc`), `run_onchange_after_`. `~/.config` has exactly one source dir (`dot_config/`) — put private subdirs under it as `private_<name>`.
- Prompt strings in `.chezmoi.toml.tmpl` must not contain commas (breaks `--promptString`), and are duplicated verbatim in `install.sh`'s CI `--promptString` args — change both together.
- Secret-dependent files are skipped via `dotfiles/.chezmoiignore` when their prompt was left blank (Chromium OAuth env, restic env + timer). New secret-backed files need a matching ignore rule.
- Outside `--ci`, the user phase runs `chezmoi init --apply "$REPO_URL"` then `chezmoi update` (so re-runs pull new dotfiles) — it applies the **pushed** repo, not the local tree. Test local dotfile edits with the temp-HOME dry-run in Commands.
- Scripts are bash unless they need a GUI (`fw-display-panel`: Python + GTK3 + GtkLayerShell; pin `gi.require_version` for Gtk **and** Gdk 3.0 or Gdk 4 loads). Shell scripts: `#!/usr/bin/env bash`, `set -euo pipefail`; must pass `shellcheck -S warning`. Build package arg lists with `mapfile`, not `$(...)`. Wrap `eval "$(mise activate bash)"` in `set +u`.

## Verification before declaring done

- `bash -n` on every script; JSON-parse `waybar/config.jsonc` (strip `//` comments) and TOML-parse mise/starship — the python snippet in the CI `lint` job does both.
- `Hyprland --verify-config` on the rendered `hyprland.lua`; duplicate-keybind check via `hyprctl -j binds` (70 binds today).
- chezmoi dry-run into a temp HOME, both with secrets blank and filled.
- CI green on fedora:44; read the install report in the job summary (added count, size, top 25, Hypr provenance).
- Hardware-only checks (cannot be done in CI/VM): MT7925 Wi-Fi/BT, VA-API (`vainfo` via distrobox), fingerprint, suspend/resume, tuned-ppd profiles, ambient light sensor, Steam + gamescope.

## Known unverified

Package names resolved on Fedora 44 + lionheartp in the first CI build (only swayosd failed → dropped). Unverified: whether the COPR ships `hyprland-uwsm.desktop` (installer adds one in /usr/local/share/wayland-sessions if not), Timeshift rsync filter behaviour on a real system.

## License

GPL-3.0-only (`LICENSE`). Third-party packages keep their own licenses.
