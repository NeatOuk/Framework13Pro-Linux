# Framework13Pro-Linux (fw13-hypr)

An ML4W-style installer that turns **any regular Fedora install** (Workstation/GNOME, KDE Plasma, any spin, or Minimal) into a clean Hyprland desktop, tuned for the **Framework Laptop 13, AMD Ryzen AI 9 HX 370**. It adds what's needed and removes nothing.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/NeatOuk/Framework13Pro-Linux/main/install.sh)
```

Or `git clone` the repo and run `./install.sh`. Run it as your normal user; it asks for sudo when it needs it. It's safe to re-run. Reboot when it finishes, then pick **Hyprland (uwsm)** at the login screen.

## Fresh install on the Framework (Wi-Fi only)

1. Install any Fedora 44+ edition. Connecting Wi-Fi in the installer is enough; the MT7925 card works out of the box.
   - **Minimal Install:** also tick the **"Common NetworkManager Submodules"** add-on, or you'll have no Wi-Fi after reboot.
   - **USB tethering** from your phone works as a fallback, with no drivers needed.
2. Log in and run the one-liner above.
3. Reboot.

## What it does

| Step | Detail |
|---|---|
| Repos | RPM Fusion (free + nonfree), COPR `lionheartp/Hyprland` (Hyprland was dropped from Fedora's repos in F43), Microsoft (VS Code), mise |
| Packages | `packages/*.txt`, installed with **optional dependencies off**, so only what's listed (plus hard dependencies) gets installed |
| Login | **Keeps your existing GDM/SDDM** and adds a Hyprland session. On a Minimal install with no login screen, it installs **greetd + tuigreet** |
| Power | Keeps `power-profiles-daemon` if it's installed; otherwise installs `tuned` + `tuned-ppd` |
| Codecs | Replaces `ffmpeg-free` with RPM Fusion `ffmpeg`, the only package it swaps out |
| Fingerprint | Turns on fingerprint for sudo, login and polkit (`authselect … with-fingerprint`) |
| Dotfiles | chezmoi applies `dotfiles/` to your home folder. It asks once for your Chromium OAuth keys and restic repository, which are never stored in git |
| Tools | mise installs node LTS, chezmoi and starship; Claude Code comes from Anthropic's native installer (updates itself) |
| Shell | Lets you pick zsh, fish or bash |
| Extras | Adds the Flathub remote (no apps installed), offers fingerprint enrollment, sets up Timeshift, and checks for firmware updates |
| Report | `~/.local/state/fw13-hypr/install-report.txt`: how many packages it added, their total size, and the largest 25 |

Not supported: Atomic editions (Silverblue/Kinoite), since they can't install packages this way. The installer stops on those.

## Backups

**Timeshift** snapshots the whole system plus your home folder. Run `sudo fw-timeshift-setup` (the installer offers to). It picks the mode by itself:

| Disk layout | Mode | Schedule |
|---|---|---|
| btrfs with `@`/`@home` subvolumes | **btrfs** (instant, no extra space) | hourly ×12, daily ×7, weekly ×4, boot ×3 |
| Fedora's default btrfs (`root`/`home`), ext4, xfs | **rsync** (copies files, then incremental) | daily ×7, weekly ×4, boot ×3 |

It leaves out caches, the Steam library, mise, containers and `~/Downloads`. To restore, run `sudo timeshift --restore` or use `timeshift-launcher` (`SUPER+Shift+B`). A systemd timer (`fw-timeshift.timer`) handles the schedule, so cron isn't needed.

For an off-laptop copy, **restic** backs up your home folder daily (user systemd timer, encrypted, keeps 7 daily / 4 weekly / 6 monthly). Configure it with the restic prompt during install.

## Look & keys

- **Look:** Tokyo Night colors, flat square borders, small gaps, a thin bar (launcher and workspaces | clock | tray and status) and a centered lock screen.
- **Bar menus:** the sliders icon (right end) opens the **control center**: volume, Wi-Fi, Bluetooth, power profile, night light. The power icon next to it opens lock / suspend / log out / reboot / shut down. Clicking the Wi-Fi, Bluetooth or volume icon jumps straight to that section; bar menus open right below the icon you clicked; right-click (middle-click for volume) opens the full settings app.
- **Keys:**

| Key | Action |
|---|---|
| SUPER+Return / Space | Terminal (kitty) / launcher (fuzzel) |
| SUPER+B / E / C | Chromium / Thunar / VS Code |
| SUPER+Shift+A / T / B | Claude Code / btop / Timeshift |
| SUPER+Q / F / T / J / P | Close / fullscreen / float / change split / pseudo-tile |
| SUPER+S / Shift+S | Scratchpad / send window to scratchpad |
| SUPER+L / Escape | Lock / power menu |
| SUPER+Arrows (+Shift / +Ctrl) | Focus / move / resize |
| SUPER+1..9 (+Shift), SUPER+Tab | Go to workspace / move window there, previous workspace |
| SUPER+V | Clipboard history |
| Print / Shift+Print / Alt+Print / SUPER+Print | Region shot / full shot / start or stop recording / color picker |
| SUPER+N | Night light |
| SUPER+, (+Shift) | Dismiss notification (all) |
| Ctrl+Space | Switch to/from Khmer (fcitx5) |
| 3-finger swipe | Switch workspace |

## Updating

| What | How |
|---|---|
| Everything (packages, dotfiles, tools) | Re-run the one-liner. It pulls the latest repo into `~/.local/share/fw13-hypr` and only adds what's missing (if you cloned the repo yourself: `git pull && ./install.sh`) |
| Fedora + Hyprland packages | `sudo dnf upgrade` |
| Dotfiles only | `chezmoi update` (your `~/.config/hypr/local.conf` is never overwritten) |
| Claude Code | Updates itself; `claude update` to force it |
| BIOS / firmware | `fwupdmgr refresh && fwupdmgr update` |

## Testing

- **CI** (`.github/workflows/test.yml`) runs the real installer in a clean `fedora:44` container on every push and once a week.
  - **It catches** renamed or missing packages, repo problems and script errors, and checks that the key programs and dotfiles ended up in place.
  - **Results:** the install report appears in the job summary.
- **Hardware only:** these can only be checked on the laptop itself: the Hyprland session, Wi-Fi/Bluetooth, fingerprint, suspend, VA-API video decode, the ambient light sensor, and Steam with gamescope.

## Layout

```
install.sh                 entry point (preflight → repos → packages → system files → login/power → user phase → report)
packages/NN-*.txt          one package per line; 15-login and 61-power are conditional
repos/*.repo               vendor repos (vscode, mise)
system/                    copied into /usr/local/bin and /etc/systemd/system
dotfiles/                  chezmoi source (.chezmoiroot)
```

## License

GPL-3.0 — see [LICENSE](LICENSE). Packages installed by the script keep their own licenses.
