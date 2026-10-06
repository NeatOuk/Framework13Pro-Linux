# CLAUDE.md — fw13-hypr

ML4W-style **installer** (`install.sh`) that adds a Hyprland (uwsm) desktop on top of **any regular Fedora ≥42** — Workstation/GNOME, KDE, spins, or Minimal — for a **Framework Laptop 13, AMD Ryzen AI 9 HX 370** (Radeon 890M, MediaTek MT7925). No custom image/ISO. Fedora only (user decision). Atomic editions are refused in preflight.

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
8. Visual style: clean/minimal, Tokyo Night, flat borders, thin bar. **Keys stay simple and conventional** — do not port Omarchy's (or any distro's) keymap/menus.

## Layout

```
install.sh                 preflight → repos → packages → system files → login/power → fingerprint/services → user phase → report
                           flags: --yes --ci --system-only --user-only; env: HYPR_COPR, REPO_URL, CHECKOUT
packages/NN-*.txt          one package per line, '#' comments (15-login, 61-power conditional)
repos/*.repo               vendor repos (vscode, mise)
system/usr/local/bin/      fw-timeshift-setup
system/etc/systemd/system/ fw-timeshift.{service,timer}
dotfiles/                  chezmoi source (.chezmoiroot = dotfiles)
  .chezmoi.toml.tmpl       one-time prompts (secrets) — never commit values
  dot_config/hypr/*.conf   hyprland.conf sources monitors/theme/autostart/looknfeel/input/windows/bindings/local
  dot_local/bin/executable_fw-*   capture, record, nightlight, notify, system-menu
.github/workflows/test.yml shellcheck + config syntax, then ./install.sh --ci in fedora:43 and fedora:44 containers
```

## Package sources (current)

| Source | Notes |
|---|---|
| Fedora | everything not listed below (swayosd is not packaged for Fedora 44 → dropped; volume/brightness keys use wpctl/brightnessctl) |
| COPR `lionheartp/Hyprland` | hyprland, hyprlock, hypridle, hyprpaper, hyprpolkitagent, hyprpicker, hyprsunset, hyprland-guiutils, xdg-desktop-portal-hyprland. Hyprland was **retired from Fedora in F43**; swap via `--build-arg HYPR_COPR=…` (`""` = Fedora only) |
| RPM Fusion | steam, steam-devices, ffmpeg, gstreamer1-plugins-bad-freeworld |
| Vendor | `code` (packages.microsoft.com), `mise` (mise.jdx.dev/rpm) |
| mise (user, `~/.config/mise/config.toml`) | node LTS, chezmoi, starship, `npm:@anthropic-ai/claude-code` |

Declined by the user — do not re-propose unless asked: `mesa-va-drivers-freeworld`, toolbox, Docker CE, ProtonUp-Qt, Nerd Fonts, snapper/btrfs-assistant, Qt5 removal, CJK font removal, swayosd COPR, Arch support, bootc/ISO image.

## Commands

```bash
./install.sh                     # full install (interactive)
./install.sh --ci                # what CI runs in a fedora container (root, non-interactive)
./install.sh --user-only         # re-apply dotfiles/mise/shell only
HOME=$(mktemp -d) chezmoi init --source=$PWD --apply   # dry-run dotfiles into a throwaway home
shellcheck -S warning install.sh system/usr/local/bin/* dotfiles/dot_local/bin/executable_*
```

Package-resolution failures are intended to fail loudly — fix the name (and ask the user if it means a source change); never add `--skip-unavailable`.

## Conventions

- **Hyprland ≥ 0.53 syntax**: `windowrule = match:class ^(x)$, float on`; gestures `gesture = 3, horizontal, workspace`. No `windowrulev2`.
- Launch GUI apps through uwsm: `uwsm app -- <cmd>`; fuzzel uses `--launch-prefix="uwsm app -- "`.
- Session env goes in `dotfiles/dot_config/environment.d/` (read by systemd --user), not Hyprland `env =`.
- Icons: **Font Awesome 6 Free/Brands only** (no Nerd Font codepoints ≥ U+F0000). Fonts: JetBrains Mono, Noto (incl. Khmer).
- Notifications from scripts: `fw-notify "title" "body"` (gdbus), not `notify-send`.
- chezmoi naming: `dot_`, `private_`, `executable_`, `create_` (create-once, e.g. `hypr/local.conf`, `fcitx5/profile`), `modify_` (keeps distro `.bashrc`), `run_onchange_after_`. `~/.config` has exactly one source dir (`dot_config/`) — put private subdirs under it as `private_<name>`.
- Prompt strings in `.chezmoi.toml.tmpl` must not contain commas (breaks `--promptString`).
- Shell scripts: `#!/usr/bin/env bash`, `set -euo pipefail`; must pass `shellcheck -S warning`. Build package arg lists with `mapfile`, not `$(...)`. Wrap `eval "$(mise activate bash)"` in `set +u`.
- Commits end with the `Co-Authored-By` / `Claude-Session` trailers.

## Verification before declaring done

- `bash -n` on every script; `jq`/JSON-parse `waybar/config.jsonc` (strip `//` comments); TOML-parse mise/starship.
- Duplicate-keybind check on `hypr/bindings.conf` (ALT+TAB pairs are intentional elsewhere; none expected now).
- chezmoi dry-run into a temp HOME, both with secrets blank and filled.
- CI green on fedora:43 and fedora:44; read the install report in the job summary (added count, size, top 25, Hypr provenance).
- Hardware-only checks (cannot be done in CI/VM): MT7925 Wi-Fi/BT, VA-API (`vainfo` via distrobox), fingerprint, suspend/resume, tuned-ppd profiles, ambient light sensor, Steam + gamescope.

## Known unverified

Package names resolved on Fedora 44 + lionheartp in the first CI build (only swayosd failed → dropped). Unverified: Fedora 43 resolution, whether the COPR ships `hyprland-uwsm.desktop` (installer adds one in /usr/local/share/wayland-sessions if not), Timeshift rsync filter behaviour on a real system.

## License

GPL-3.0-only (`LICENSE`). Third-party packages keep their own licenses.
