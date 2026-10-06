# CLAUDE.md — fw13-hypr

Fedora 44 **bootc** (image-based, atomic) OS image + chezmoi dotfiles for a **Framework Laptop 13, AMD Ryzen AI 9 HX 370** (Radeon 890M, MediaTek MT7925 Wi-Fi/BT), running **Hyprland** via uwsm. The OS is a container image; the user layer is distro-agnostic (chezmoi + mise) so it can be reapplied on Arch or any other distro.

## Hard rules

1. **Ask before adding ANY package**, including weak deps, helpers, and "obvious" utilities. Propose name + source + why; wait for approval. Never slip one in through a script (e.g. `jq`, `libnotify`, `rsync`) — use what's already installed (see `fw-notify` using `gdbus`).
2. **Prefer official sources**, in this order: Fedora repos → vendor's own repo (Microsoft, mise) → RPM Fusion → COPR → upstream installer → Flathub. State the source tier when proposing.
3. **Weak deps are off globally** (`install_weak_deps=False`). Anything needed must be listed explicitly in `image/packages/*.txt`. Fedora ships per-vendor firmware (amd-gpu, amd-ucode, mt7xxx) only as weak deps of `linux-firmware` — never remove those lines.
4. **Never install apps on Flathub** without per-app approval. The remote is added; it stays empty by default.
5. **No secrets in git.** Credentials (Chromium OAuth, restic repo/password) come from chezmoi `promptStringOnce` in `dotfiles/.chezmoi.toml.tmpl` and render into `private_` (0600) files.
6. **OS rollback is bootc's job** (`bootc rollback`). Timeshift is rsync mode, scoped to `/var/home` + `/etc` only. Never configure Timeshift btrfs mode or full-system restore.
7. Hardware is AMD. Do not add Intel-specific packages/params.
8. Visual style: clean/minimal, Tokyo Night, flat borders, thin bar. **Keys stay simple and conventional** — do not port Omarchy's (or any distro's) keymap/menus.

## Layout

```
image/
  Containerfile              FROM quay.io/fedora/fedora-bootc:${FEDORA_VERSION}; ARG HYPR_COPR
  build.sh                   repos → packages → greetd/tuigreet → fingerprint PAM → services → manifest
  packages/NN-*.txt          one package per line, '#' comments; grouped by purpose
  repos/*.repo               vendor repos (vscode, mise)
  rootfs/                    copied to / (helpers in /usr/bin, systemd units in /usr/lib/systemd/system)
dotfiles/                    chezmoi source (.chezmoiroot = dotfiles)
  .chezmoi.toml.tmpl         one-time prompts (secrets) — never commit values
  .chezmoiignore             conditional on blank secrets
  dot_config/hypr/*.conf     hyprland.conf sources monitors/theme/autostart/looknfeel/input/windows/bindings/local
  dot_local/bin/executable_fw-*   small helpers (capture, record, nightlight, notify, system-menu)
scripts/                     build-image, switch-local, make-iso, bloat-report
.github/workflows/build.yml  build + lint + manifest summary; push to GHCR on main/nightly; optional qcow2
```

## Package sources (current)

| Source | Notes |
|---|---|
| Fedora | everything not listed below |
| COPR `lionheartp/Hyprland` | hyprland, hyprlock, hypridle, hyprpaper, hyprpolkitagent, hyprpicker, hyprsunset, hyprland-guiutils, xdg-desktop-portal-hyprland. Hyprland was **retired from Fedora in F43**; swap via `--build-arg HYPR_COPR=…` (`""` = Fedora only) |
| RPM Fusion | steam, steam-devices, ffmpeg, gstreamer1-plugins-bad-freeworld |
| Vendor | `code` (packages.microsoft.com), `mise` (mise.jdx.dev/rpm) |
| mise (user, `~/.config/mise/config.toml`) | node LTS, chezmoi, starship, `npm:@anthropic-ai/claude-code` |

Declined by the user — do not re-propose unless asked: `mesa-va-drivers-freeworld`, toolbox, Docker CE, ProtonUp-Qt, Nerd Fonts, snapper/btrfs-assistant, Qt5 removal, CJK font removal.

## Commands

```bash
./scripts/build-image.sh                 # sudo podman build → localhost/fw13-hypr:latest
./scripts/bloat-report.sh [IMAGE]        # print /usr/share/fw13-hypr-manifest.txt
./scripts/make-iso.sh                    # bootc-image-builder anaconda-iso, btrfs
./scripts/switch-local.sh                # bootc switch to local image (rollback: bootc rollback)
HOME=$(mktemp -d) chezmoi init --source=$PWD --apply   # dry-run dotfiles into a throwaway home
```

CI: `.github/workflows/build.yml`. Image: `ghcr.io/neatouk/fw13-hypr:latest` (GHCR names must be lowercase). Build fails on any unresolvable package — that's intended; fix the name, don't add `--skip-unavailable`.

## Conventions

- **Hyprland ≥ 0.53 syntax**: `windowrule = match:class ^(x)$, float on`; gestures `gesture = 3, horizontal, workspace`. No `windowrulev2`.
- Launch GUI apps through uwsm: `uwsm app -- <cmd>`; fuzzel uses `--launch-prefix="uwsm app -- "`.
- Session env goes in `dotfiles/dot_config/environment.d/` (read by systemd --user), not Hyprland `env =`.
- Icons: **Font Awesome 6 Free/Brands only** (no Nerd Font codepoints ≥ U+F0000). Fonts: JetBrains Mono, Noto (incl. Khmer).
- Notifications from scripts: `fw-notify "title" "body"` (gdbus), not `notify-send`.
- chezmoi naming: `dot_`, `private_`, `executable_`, `create_` (create-once, e.g. `hypr/local.conf`, `fcitx5/profile`), `modify_` (keeps distro `.bashrc`), `run_onchange_after_`. `~/.config` has exactly one source dir (`dot_config/`) — put private subdirs under it as `private_<name>`.
- Prompt strings in `.chezmoi.toml.tmpl` must not contain commas (breaks `--promptString`).
- Shell scripts: `#!/usr/bin/env bash`, `set -euo pipefail` for root/setup scripts; must pass `bash -n`.
- Commits end with the `Co-Authored-By` / `Claude-Session` trailers.

## Verification before declaring done

- `bash -n` on every script; `jq`/JSON-parse `waybar/config.jsonc` (strip `//` comments); TOML-parse mise/starship.
- Duplicate-keybind check on `hypr/bindings.conf` (ALT+TAB pairs are intentional elsewhere; none expected now).
- chezmoi dry-run into a temp HOME, both with secrets blank and filled.
- CI green, and read the manifest: package count, size, top 30, per-repo size, Hypr provenance.
- Hardware-only checks (cannot be done in CI/VM): MT7925 Wi-Fi/BT, VA-API (`vainfo` via distrobox), fingerprint, suspend/resume, tuned-ppd profiles, ambient light sensor, Steam + gamescope.

## Known unverified

Fedora 44 names for some fonts (`google-noto-sans-khmer-fonts`, `fontawesome-fonts-all`), `mt7xxx-firmware`, `tuigreet`, `swayosd`; exact package set in `lionheartp/Hyprland`; whether `timeshift` hard-requires a cron daemon (harmless if so — scheduling uses `fw-timeshift.timer`).

## License

GPL-3.0-only (`LICENSE`). Third-party packages keep their own licenses.
