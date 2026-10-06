# fw13-hypr

Framework Laptop 13 (AMD Ryzen AI 9 HX 370 · Radeon 890M · MediaTek MT7925) on Fedora 44 bootc (image-based, atomic) with Hyprland: a clean, minimal look (Tokyo Night, flat borders, thin bar) and simple keys.

The OS is a container image built from `image/`. Your user environment is the chezmoi repo in `dotfiles/`. That layer only depends on mise, so if you hop to Arch later, the same `chezmoi init --apply` reproduces the desktop.

```
image/        Containerfile · build.sh · packages/*.txt · vendor repos · /usr/bin helpers  → the OS
dotfiles/     chezmoi source (.chezmoiroot points here)                                  → your $HOME
scripts/      build-image · switch-local · make-iso · bloat-report
.github/      nightly image build → ghcr.io  (laptop pulls via `bootc upgrade`)
```

## Package sources

All weak (optional) dependencies are **off**, so every package that gets installed is either listed in `image/packages/*.txt` or a hard dependency of one.

| Source | Packages |
|---|---|
| Fedora official | core plumbing, mesa-va-drivers, **amd-gpu-firmware, amd-ucode-firmware, mt7xxx-firmware**, greetd, tuigreet, waybar, fuzzel, mako, kitty, thunar, grim, slurp, wl-clipboard, cliphist, wf-recorder, swayosd, brightnessctl, playerctl, pavucontrol, nm-applet, blueman, btop, fcitx5 (+m17n, configtool), Noto fonts (incl. Khmer, CJK, emoji), JetBrains Mono, Font Awesome, chromium, gamescope, gamemode, mangohud, fwupd, fprintd (+pam), tuned (+ppd), iio-sensor-proxy, podman, distrobox, zsh (+plugins), fzf, fish, **timeshift, restic** |
| COPR lionheartp/Hyprland | hyprland, hyprlock, hypridle, hyprpaper, hyprpolkitagent, hyprpicker, hyprsunset, hyprland-guiutils, xdg-desktop-portal-hyprland (Hyprland was retired from Fedora in F43) |
| RPM Fusion | steam, steam-devices, ffmpeg, gstreamer1-plugins-bad-freeworld |
| Vendor repo | `code` (Microsoft), `mise` (mise.jdx.dev) |
| mise | node LTS, chezmoi, starship, `npm:@anthropic-ai/claude-code` |
| Flathub | remote added, **no apps** |

To swap the Hyprland source: `HYPR_COPR=sdegler/hyprland ./scripts/build-image.sh`.

## How much space it takes

Every build writes `/usr/share/fw13-hypr-manifest.txt`, which lists:
- the total package count and installed size
- the 30 largest packages
- size per source repo
- where each Hyprland package came from

To see it, run `./scripts/bloat-report.sh`. CI also prints it in the job summary.

Estimates until the first build (real numbers come from the manifest):

| | Packages | Size on disk |
|---|---|---|
| fedora-bootc base | ~450 | ~1.6 GB |
| **this image** | **~1,100–1,300** | **~4–5 GB** |
| Fedora Workstation | ~2,000 | ~7–9 GB |

Biggest items: Steam and its 32-bit libraries (~0.8–1 GB), VS Code, Chromium, Mesa/LLVM, Qt5+Qt6, Noto CJK.

## Install

- **Fresh install (recommended):** run `./scripts/build-image.sh` and then `./scripts/make-iso.sh`. Flash `output/bootiso/install.iso` and install. The ISO is built with **btrfs**.
- **From an existing Fedora Atomic install:** `./scripts/build-image.sh && ./scripts/switch-local.sh`, then reboot.
- **Updates:** push this repo to GitHub. CI builds `ghcr.io/neatouk/fw13-hypr:latest` every night. Run `sudo bootc switch ghcr.io/neatouk/fw13-hypr:latest` once; after that, `sudo bootc upgrade` keeps you current. The owner name in the image path must be lowercase.

## First login

Log in through greetd/tuigreet and pick **Hyprland (uwsm)**. Open a terminal (`SUPER+Q` in Hyprland's built-in default config) and run `fw13-firstboot`. It walks through:

1. **Shell picker:** zsh, fish or bash.
2. **chezmoi via mise.** It asks once for:
   - your Chromium OAuth keys
   - your restic repository and password

   Both are stored in `~/.config/chezmoi/chezmoi.toml` and are never committed to git. Leave them blank to skip.
3. `mise install`: node, chezmoi, starship and Claude Code.
4. **Flathub remote** (no apps).
5. **Fingerprint** enrollment.
6. **Timeshift:** `fw-timeshift-setup` (see Backups below).
7. **Firmware check** through LVFS.

## Backups & rollback

| Layer | Mechanism | How to use |
|---|---|---|
| OS (`/usr`, read-only image) | bootc keeps the previous deployment | `sudo bootc rollback` · `sudo ostree admin pin 0` to keep a known-good image |
| `/var/home` + `/etc` | **Timeshift** (rsync mode): 12 hourly, 7 daily, 4 weekly | `sudo timeshift --list` · GUI with `SUPER+SHIFT+B` · restore single files by browsing the snapshot folder |
| Off-laptop | **restic** daily (user systemd timer): encrypted, deduplicated, keeps 7 daily / 4 weekly / 6 monthly | `systemctl --user list-timers` · `restic snapshots` |

How Timeshift is set up here:
- **What it backs up.** `fw-timeshift-setup` asks which drive to store snapshots on, then configures Timeshift to back up **only `/var/home` and `/etc`**. It skips caches, the Steam library, mise, containers, Trash and `~/Downloads`.
  - A second drive or partition also protects against disk failure.
  - The system disk only protects against mistakes and deletions.
- **Never use Timeshift's full-system Restore on this OS.** The OS is a read-only image; roll it back with `bootc rollback` instead.
- **Scheduling.** Timeshift normally schedules itself with cron, which this image doesn't include. A systemd timer (`fw-timeshift.timer`) runs `timeshift --check` every hour instead, and Timeshift creates and prunes snapshots based on the counts above.
  - If you change the counts in the GUI, they still apply.
  - The GUI's own scheduler checkbox does nothing here.
- **Tested filter.** I tested the include/exclude filter with rsync: only `etc/` and `var/home/` get copied, without caches or Downloads. Check your first real snapshot anyway.

## Look & keys

**Look:**
- Tokyo Night colors, flat square borders, 5/10 px gaps, subtle blur.
- A thin bar: launcher and workspace dots on the left, clock in the center, tray and status icons on the right.
- A centered lock screen.
- kitty, fuzzel and mako use the same colors.

| Key | Action |
|---|---|
| SUPER+Return | Terminal (kitty) |
| SUPER+Space | App launcher (fuzzel) |
| SUPER+B / E / C | Chromium / Thunar / VS Code |
| SUPER+Shift+A | Claude Code |
| SUPER+Shift+T | btop |
| SUPER+Shift+B | Timeshift |
| SUPER+Q | Close window |
| SUPER+F | Fullscreen |
| SUPER+T | Float |
| SUPER+J | Change split direction |
| SUPER+P | Pseudo-tile |
| SUPER+S / Shift+S | Scratchpad / send window to scratchpad |
| SUPER+L | Lock |
| SUPER+Escape | Power menu |
| SUPER+Arrows / Shift / Ctrl | Focus / move / resize |
| SUPER+1..9 / Shift | Go to workspace / move window there |
| SUPER+Tab | Previous workspace |
| SUPER+V | Clipboard history |
| Print / Shift+Print / Alt+Print | Region screenshot / full screenshot / start or stop recording |
| SUPER+Print | Color picker |
| SUPER+N | Night light |
| SUPER+, / Shift+, | Dismiss notification / dismiss all |
| Volume, brightness and media keys | swayosd popups |
| Ctrl+Space | Switch to/from Khmer (fcitx5) |
| 3-finger swipe | Switch workspace |

## Notes

- **AMD video:** `mesa-va-drivers` (Fedora) does AV1/VP9 hardware decode. H.264/HEVC stays on the CPU unless you swap in RPM Fusion's `mesa-va-drivers-freeworld`. Check what's supported with `vainfo` (from libva-utils, which isn't installed).
- **Khmer:** in Chromium, enable `chrome://flags/#wayland-text-input-v3` for the input method.
- **Gaming:** in Steam launch options, use `gamemoderun mangohud %command%` or `gamescope -f -- %command%`. Tearing and VRR are already set up for games.
- **Containers:** podman is rootless. `podman.socket` provides a Docker-compatible API. `distrobox create -i archlinux` gives you an Arch toolbox.
- **Wallpaper:** `~/.config/hypr/wallpaper.jpg`. Per-machine tweaks go in `~/.config/hypr/local.conf`, which chezmoi doesn't touch.
- **Unverified when this was written:** some Fedora package names (fonts, `mt7xxx-firmware`), the exact package set in the lionheartp COPR. `build.sh` stops on any missing package, so a wrong name breaks the build, never the laptop.
