# fw13-hyprland (fw13-hypr)

An ML4W-style installer that turns **any regular Fedora install** (Workstation/GNOME, KDE Plasma, any spin, or Minimal) into a clean Hyprland desktop, tuned for the **Framework Laptop 13, AMD Ryzen AI 9 HX 370**. It adds what's needed and removes nothing.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/NeatOuk/fw13-hyprland/main/install.sh)
```

Or `git clone` the repo and run `./install.sh`. Run it as your normal user; it asks for sudo when it needs it. It's safe to re-run. Reboot when it finishes, then pick **Hyprland (uwsm)** at the login screen.

## Fresh install on the Framework (Wi-Fi only)

1. Install any Fedora 44+ edition. Connecting Wi-Fi in the installer is enough; the MT7925 card works out of the box.
   - **Minimal Install:** also tick the **"Common NetworkManager Submodules"** add-on, or you'll have no Wi-Fi after reboot.
   - **USB tethering** from your phone works as a fallback, with no drivers needed.
2. Log in and run the one-liner above.
3. Reboot.

What you'll see at each step, and the Framework-only checks to do afterwards: [docs/FIRST-INSTALL.md](docs/FIRST-INSTALL.md).

## What it does

| Step | Detail |
|---|---|
| Repos | RPM Fusion (free + nonfree), COPR `lionheartp/Hyprland` (Hyprland was dropped from Fedora's repos in F43), Microsoft (VS Code), mise, Devolutions (Remote Desktop Manager) |
| Packages | `packages/*.txt`, installed with **optional dependencies off**, so only what's listed (plus hard dependencies) gets installed |
| Login | A clean **text login** (greetd + tuigreet): pick your user, password, and F2 for the session (Hyprland is preselected; GNOME/KDE stay selectable). An existing GDM/SDDM is **disabled, not removed**: run `KEEP_DM=1 ./install.sh` to keep it, or switch back later with `sudo systemctl disable greetd && sudo systemctl enable gdm` |
| Framework tool | `framework_tool` (Framework's official command-line tool, from their GitHub release, checksum-pinned) in `/usr/local/bin`: firmware versions, charge limit, fan, keyboard backlight and other EC settings — e.g. `sudo framework_tool --versions` |
| Power | Keeps `power-profiles-daemon` if it's installed; otherwise installs `tuned` + `tuned-ppd`. Adds `upower` for battery info and the charge limit. The power profile follows the charger: **Performance** when plugged in, **Balanced** on battery (a profile you pick by hand lasts until the next plug/unplug) |
| Codecs | Replaces `ffmpeg-free` with RPM Fusion `ffmpeg`, the only package it swaps out |
| Fingerprint | Turns on fingerprint for sudo, login and polkit (`authselect … with-fingerprint`) |
| Dotfiles | chezmoi applies `dotfiles/` to your home folder. It asks once for your Chromium OAuth keys and restic repository, which are never stored in git |
| Tools | mise installs node LTS, chezmoi and starship; Claude Code comes from Anthropic's native installer (updates itself) |
| Shell | Lets you pick zsh, fish or bash |
| Extras | Adds the Flathub remote (no apps installed), offers fingerprint enrollment, sets up Timeshift, and checks for firmware updates |
| Telegram | **Telegram Desktop**, the official build from telegram.org, packaged as an RPM (`telegram-desktop-official`) so dnf owns it (`dnf remove telegram-desktop-official` removes it). Its own updater is off; re-run the installer to update it (it rebuilds only when telegram.org has a newer version). The icon in the bar's tray is Telegram's own |
| Citadel | Installs **Citadel**, an outbound firewall: when an app connects somewhere new it asks (Allow once / Always / Block) in its window, tray icon or a notification, and your answers become per-app policies. **Enforcement is on**, so blocked or unanswered connections really are blocked. It's built from [citadel-app](https://github.com/NeatOuk/citadel-app) and [citadel-helper](https://github.com/NeatOuk/citadel-helper) as RPMs (`dnf remove citadel citadel-helper` removes it). Turn blocking off any time with `citadel enforce off` or in Citadel → Settings |
| Report | `~/.local/state/fw13-hypr/install-report.txt`: how many packages it added, their total size, and the largest 25 |

On **Minimal** or another install without GNOME or KDE, the installer warns before it starts and again at the end: Hyprland alone has no file mounting, printing or document viewers, so install GNOME first with `sudo dnf group install workstation-product-environment` (it stays selectable at login). The installer doesn't add it for you.

Not supported: Atomic editions (Silverblue/Kinoite), since they can't install packages this way. The installer stops on those.

## Backups

**Timeshift** snapshots the whole system plus your home folder. Run `sudo fw-timeshift-setup` (the installer offers to). It picks the mode by itself:

| Disk layout | Mode | Schedule |
|---|---|---|
| btrfs with `@`/`@home` subvolumes | **btrfs** (instant, no extra space) | hourly ×12, daily ×7, weekly ×4, boot ×3 |
| Fedora's default btrfs (`root`/`home`), ext4, xfs | **rsync** (copies files, then incremental) | daily ×7, weekly ×4, boot ×3 |

It leaves out caches, the Steam library, mise, containers and `~/Downloads`. Timeshift schedules itself (its own cron jobs). To restore on Fedora's default layout, use `sudo fw-timeshift-restore` (Timeshift's own restore only works on the `@` subvolume layout); on an `@` layout, `sudo timeshift --restore` or `timeshift-launcher` (`SUPER+Shift+B`).

**Restoring the system** (Fedora's default layout, rsync mode):

```bash
sudo fw-timeshift-restore --list            # snapshots
sudo fw-timeshift-restore <snapshot>        # dry run: shows what would change
sudo fw-timeshift-restore real <snapshot>   # restore, then reboot
sudo fw-timeshift-restore undo              # go back to the system from before the restore
```

It copies the current system, restores the snapshot onto the copy and swaps the two only if that worked, so the running system is never overwritten. It keeps `/home`, Wi-Fi/VPN connections, Bluetooth pairings, fingerprints and Timeshift's settings, and holds Timeshift's lock so scheduled snapshots wait. The snapshot's kernel is added next to the current ones and made the default. The first boot relabels SELinux (several minutes, then one automatic reboot). The old system stays as subvolume `root.fw-before` until you delete it.

For an off-laptop copy, **restic** backs up your home folder daily (user systemd timer, encrypted, keeps 7 daily / 4 weekly / 6 monthly). Configure it with the restic prompt during install or later in Settings → My Framework, which has presets for a **NAS over SFTP** and **Backblaze B2 (S3)**; S3 keys (also Wasabi, R2, MinIO) are entered there, never in a file by hand. Settings → My Framework → Restore opens a terminal with the repository loaded: `restic snapshots`, `restic mount ~/restic-mnt` to browse (fuse3), or `restic restore latest --target ~/restore --include ~/path`. Keep the repository password in a password manager: without it the backup can't be read.

## Look & keys

- **Look:** colors that follow your wallpaper (Material You, generated by [matugen](https://github.com/InioX/matugen)) or the fixed Tokyo Night palette, flat square borders, small gaps, a thin bar (launcher and workspaces | clock | tray and status) and a lock screen styled like the text login (tuigreet).
- **Settings:** the sliders icon (right end), SUPER+I or "Settings" in the launcher opens our **Settings** app, in the same flat style:
  - **Network:** Wi-Fi (connect, forget, hidden networks; passwords never appear in a command line), Ethernet, and every VPN in one list (NetworkManager's OpenVPN, OpenConnect for FortiGate SSL / AnyConnect / GlobalProtect, Cisco IPsec and WireGuard, plus strongSwan IKEv2): Connect / Disconnect, **Edit…** (nm-connection-editor, or a form for IKEv2: name, server, gateway ID, your ID, username, password, pre-shared key, networks; asks for your password, keeps the previous file as `<name>.conf.bak`, the password and key are never shown and stay unchanged when left empty; Delete), and add one: **IKEv2 (FortiGate / strongSwan)…**, **OpenVPN, OpenConnect, Cisco… or import a file**, **WireGuard file…**. The bar's shield lists them all too.
  - **Bluetooth:** on/off, your devices (connect, forget, battery), scan and pair.
  - **Sound:** output and input devices, volume. **Display:** brightness, arrange screens, refresh rate, scale, night light with a **Schedule** (Off, Sunset to sunrise for the weather city, 19:00 to 06:30 when offline or without one, or Custom times; checked every 5 minutes and changed only at the switch-over times, so SUPER+N wins until the next one; Zen keeps it on). **Power:** battery, profile, 80 % charge limit, screen & sleep timeouts, separately for plugged in and on battery, and when to warn about a low battery (**Warn at** 20, 10 and 5 %, 10 and 5 %, or off: 20 % is a normal notification with the time left, 10 % and 5 % stay up until dismissed and show even in Focus/Zen; 5 % says what the laptop does at 2 %; warnings reset when you plug in).
  - **Appearance:** wallpaper (with an effect: none, blur, dim, grey, blur + dim), theme (colors from the wallpaper, dark or light, or Tokyo Night), font (one fixed-width font for the bar, launcher, notifications, lock screen, panels and terminals; JetBrains Mono by default), gaps, borders. The theme recolors the window borders, bar, launcher, notifications, terminal, lock screen, our own panels and GTK/Qt apps (GTK 3 apps at once; libadwaita and Qt apps when they next start; switching Qt apps to these colors the first time needs a re-login, since qt6ct is set for the Hyprland session only). The Citadel window follows after a restart; its tray icon is drawn by Citadel itself. The generated colors live in `~/.config/fw13/theme/`; your own `~/.config/gtk-4.0/gtk.css` is never overwritten, and GNOME/KDE on the same account get their GTK settings back when you log out of Hyprland. It needs matugen 4 from the Hyprland COPR (Fedora's 3.1.0 is too old); installed with `HYPR_COPR=` empty, it stays Tokyo Night. **Input:** touchpad, key repeat, keyboard layouts, input methods (Khmer).
  - **Security:** fingerprint (enrolled count, enrol, remove all), lock screen (a pointer to the per-power-source timeouts in Power, Lock now), disk encryption: how the LUKS disk unlocks at boot (**Password only**, **TPM + PIN** or **TPM automatic**; the choice opens a terminal running `sudo fw-disk-unlock`, which asks for your disk passphrase, enrols the TPM (PCR 7), updates `/etc/crypttab` (or the kernel line), adds dracut's TPM module and rebuilds the initramfs of every installed kernel; **TPM automatic** is offered only with Secure Boot on, and only guards against the disk leaving the laptop, so TPM + PIN is the safer choice; the passphrase is never removed and stays the fallback), Secure Boot on/off (changed in the BIOS, F2), the Citadel firewall's state (Open Citadel), whether the strongSwan VPN toggle needs a password (VPNs are managed in Network), SSH keys (whether Fedora's `gcr-ssh-agent` runs and how many keys it holds, each `~/.ssh/*.pub` with its fingerprint, **Add to agent** runs `ssh-add` in a terminal that asks the passphrase, **Copy public key**; without a key, **Create key…** runs `ssh-keygen -t ed25519` in a terminal), and the login screen. Root-only facts come from the hourly `fw-health-root`, so opening the page never asks for a password.
  - **System:** date, time zone, automatic time, device name, weather city and °C/°F for the bar, software updates (count from dnf's cache, **Snapshot + update…**), firmware updates (fwupd), about this computer.
  - **My Framework:** first the laptop's hardware: live fan speed and fan mode (automatic or a fixed 25–100 %), keyboard backlight, fingerprint-reader LED brightness, how long the laptop waits before fully powering off when shut down, and reports from `framework_tool` (firmware versions, battery and charger, temperatures, privacy switches, USB-C ports, input modules, chassis-open count, display and audio expansion cards, deep-sleep count, power-off delay, controller log). Changes ask for your password through polkit; reports open in a terminal. Below that, what the installer asked once, changeable later: Chromium sign-in keys, the Ollama Cloud key for OpenCode, restic off-site backups (repository and password, test connection, set up a new repository, back up now, daily on/off, last run, log) and your login shell (bash, zsh or fish). Keys are typed into hidden fields, never shown again, and stored only in `~/.config/chezmoi/chezmoi.toml` and the private files made from it; new keys take effect after you log out and back in. It also shows where your dotfiles come from (Update dotfiles, Re-run user setup) and what the installer set up (fingerprint and the login screen moved to Security).
  Appearance and Input are saved to `~/.config/hypr/settings.lua`, checked by Hyprland before it's used; your `local.lua` still wins over it. It opens as a normal tiled window; clicking the sliders icon again closes it. GNOME's own settings are in the GNOME session.
- **Apps that follow the theme:** besides the desktop, GTK and Qt apps: terminal tools through the terminal's 16 colors (kitty or Ghostty) (prompt, shells, git, btop, fzf, bat), Chromium (switched to its GTK theme at login, unless you picked a Chromium theme yourself), the Khmer input popup (fcitx5), and VS Code if you turn on Settings → Appearance → VS Code (off by default: it writes colors into VS Code's `settings.json` while you're in Hyprland and removes them at logout, so Settings Sync could copy them). GNOME apps (libadwaita) pick up new colors when they next start. For Claude Code pick `/theme` → dark-ansi, for OpenCode the `system` theme. Admin apps that run as root (Timeshift and other password-prompt tools) use the same theme, also in GNOME. Steam and web pages keep their own look.
- **Games:** Steam (RPM Fusion) with gamescope, GameMode and MangoHud, and **Lutris** for Windows launchers: for **Battle.net** open Lutris, search "Battle.net", Install, then sign in. Blizzard doesn't support Linux officially; it runs through Wine (Lutris downloads its own runner), which works well for most Blizzard games but can break briefly after a Battle.net update.
- **Apps and defaults:** inside Hyprland the launcher hides GNOME's own apps (Files, Maps, Weather, Text Editor, GNOME Settings…) and entries meant for other desktops; they stay installed and visible in the GNOME session. Folders open in Thunar, links in Chromium, and pictures, PDFs, text, video and music in GNOME's viewers (Image Viewer, Document Viewer, Text Editor, Video Player, Audio Player). These defaults are Hyprland-only (`~/.config/hyprland-mimeapps.list`); a default you set yourself (Thunar → Open With → Set as default) wins from the next login.
- **Chromium Memory Saver:** on by default with maximum savings, so background tabs are put to sleep sooner and give back their memory (a recommended policy in `/etc/chromium/policies/recommended/fw13-memory.json`). You can still turn it off or pick another level in `chrome://settings/performance`.
- **Wallpapers:** pictures live in `~/Pictures/Wallpapers` (originals are never changed; the desktop and lock images are rendered from them). SUPER+W opens a strip of them: click (or arrows + Enter) to use one, **+ Add…** copies pictures in. Settings → Appearance has the full gallery. From a terminal: `fw-wallpaper set|add <files>`, `fw-wallpaper effects <desktop> <lock>`.
- **Profile:** the icon left of the clock picks **Normal**, **Focus** (no notifications: the bell's Do not disturb) or **Zen** (no notifications, no gaps, borders or rounding, night light on). Leaving Zen puts gaps, borders and night light back as they were; turning Do not disturb off on the bell leaves Focus/Zen; each login starts in Normal.
- **Keep awake:** the coffee cup left of the profile icon (or SUPER+Shift+K) stops the screen from dimming, locking and the laptop from going to sleep until you click it again or log out (closing the lid still suspends). It turns itself off with a notification when the battery drops below 20 % on battery.
- **Weather:** right of the clock, an icon and the temperature for the city set in Settings → System → **Weather** (hidden until you set one; type `Paris, US` to pick between places with the same name). The tooltip shows today and the next two days. Data from [Open-Meteo](https://open-meteo.com) (no account), refreshed every 30 minutes; offline it shows the last value, dimmed. With Citadel enforcing, allow `python3` to reach open-meteo.com at its gate the first time. Click opens Settings → System.
- **Notifications:** the bell left of the settings icon shows unread notifications; click it for the history (pick one to copy its text), **Do not disturb** and **Dismiss all**; right-click toggles Do not disturb. Volume, mic and brightness keys show a small bar at the bottom of the screen (also during Do not disturb).
- **Health:** at the first Hyprland login `fw-hwcheck` checks the Framework hardware (CPU driver, GPU, Wi-Fi, Bluetooth, battery and charge limit, firmware, fingerprint, light sensor, suspend incl. whether the last suspend reached deep sleep, power profiles) and lists what to try by hand. `fw-health` runs 15 minutes after login and then daily: failed services, disk space, backups (restic and Timeshift), reboot needed, firmware updates, battery wear, SSD health and new crashes. It stays quiet when all is fine; otherwise a notification offers **Diagnose** (Jarvis reads the report). Reports are in `~/.local/state/fw13/health/`.
- **Software updates:** 20 minutes after login and then daily, `fw-updates --check` counts pending updates from dnf's cache (no password, no download; Fedora's `dnf-makecache.timer` refreshes it) plus firmware updates from fwupd (`fwupdmgr get-updates`, on the metadata Fedora's `fwupd-refresh.timer` keeps fresh), e.g. *33 package updates · 1 firmware update (Fingerprint Sensor 01000334)*, and shows a notification when either number changed or a day passed. **Update now** (or Settings → System → **Snapshot + update…**) opens a terminal that first takes a Timeshift snapshot (or runs `fw-timeshift-setup` if Timeshift isn't set up), stops if the snapshot fails unless you type `y`, then runs `dnf upgrade --refresh`, `flatpak update --user` and tells you whether a reboot is needed; firmware is installed from Settings → System → **Firmware updates** (needs AC power and a reboot), which the terminal reminds you of. Same from a terminal: `fw-updates apply`.
- **Auto-brightness:** Settings → Display (or the display panel) turns on brightness from the light sensor (off by default). Changing brightness yourself pauses it until the next wake or login.
- **Bar menus:** The power icon next to it opens lock / suspend / log out / reboot / shut down. The battery icon opens the **power panel**: charge state, time to full or empty, power profile, an 80% charge limit toggle, battery health and the CPU/power tuning in effect (driver, energy preference, platform profile, panel power saving, tuned profile); the battery tooltip shows the power draw in watts. The display icon opens the **display panel**: a brightness slider for the laptop screen, and for each connected monitor its position (drag it), refresh rate and scale. **Apply** asks you to keep the change and reverts after 15 seconds otherwise; kept layouts are saved in `~/.config/hypr/displays.conf`, per monitor model. Scrolling on the display icon changes brightness. Clicking the Wi-Fi, Bluetooth or volume icon jumps straight to that section; bar menus open right below the icon you clicked; right-click (middle-click for volume) opens the full settings app.
- **Cloudflare WARP:** the cloud icon (accent when connected) opens the **WARP panel**: on/off, mode, DNS filter and protocol, exit IP and Cloudflare location, tunnel endpoint, handshake, latency, loss and traffic, account (free, WARP+ key, or **Join organization** for Cloudflare Zero Trust: you sign in in the browser), the split-tunnel include/exclude list, fallback domains, trusted networks and your organization's policy. Right-click the icon to connect or disconnect. It asks you to accept Cloudflare's Terms of Service once before talking to WARP. Settings your Zero Trust organization controls are shown but greyed out. Cloudflare's own tray app is hidden in Hyprland (the panel's **Cloudflare app** button starts it). With Citadel enforcing, allow `warp-svc` at its gate the first time.
- **VPN (strongSwan):** a shield icon (accent when connected) appears once a connection file exists in `/etc/strongswan/swanctl/conf.d/<name>.conf` (connection and child both named `<name>`, secrets inside, root-only). Click it to connect or disconnect: no password for an admin (wheel) user at the laptop, through the root helper `fw-vpn-ctl` that can only bring that one connection up or down (polkit rule `50-fw13-vpn.rules`). The tooltip lists the networks the tunnel carries.
- **AI:** SUPER+A opens **Jarvis**: type a question and the answer appears right in the panel (Claude, or OpenCode on one of your Ollama servers). Jarvis can read files, logs and settings (not your key and password files) and a few root-only facts. When something needs changing, it proposes one step at a time as a card with **What / Why / How** and **Run** / **Skip**: nothing runs until you press Run, and the output goes back to Jarvis, which checks it and proposes the next step. Bigger jobs go to **Continue in terminal**, the same conversation as a full session. Settings → Jarvis picks the Claude **model** (an alias such as opus/sonnet, or a full name) and **effort** (low to max); empty = Claude Code's default. The panel's buttons start a repo task with what you typed, diagnose the last crash, or open Claude/OpenCode. The ✱ icon shows your Claude plan limits (5-hour and weekly %, reset times), updated whenever Claude Code runs. The `>_` icon manages **Ollama servers for OpenCode**: the laptop's own Ollama, your self-hosted servers (add/remove, online status, model list) and Ollama Cloud (key asked once during install), and picks the default server and model. When an app crashes or a service fails, a notification offers **Diagnose**: it saves a crash report and asks which agent should read it, so you decide what leaves the laptop. Silence noisy ones in `~/.config/fw-crash-watch/ignore`.
- **Screens:** each screen has its own workspaces 1–9 and its own row of circles in the bar. At login, your terminal opens on the laptop's workspace 1 and Chromium on the external monitor's workspace 1 (the laptop's workspace 2 if no monitor is connected). Unplugging a monitor moves its windows to the laptop; plugging it back in returns them.
- **Keys:**

| Key | Action |
|---|---|
| SUPER+Return / Space | Terminal (kitty or Ghostty, Settings → My Framework) / launcher (fuzzel) |
| SUPER+B / E / Shift+C | Chromium / Thunar / VS Code |
| SUPER+C / X | Copy / cut in the focused window (Ctrl+Shift+C in terminals; no cut there) |
| SUPER+A | Jarvis (AI assistant) |
| SUPER+Shift+A / T / B | Claude Code / btop / Timeshift |
| SUPER+Q / F / T / J / P | Close / fullscreen / float / change split / pseudo-tile |
| SUPER+S / Shift+S | Scratchpad / send window to scratchpad |
| SUPER+L / Escape | Lock / power menu |
| SUPER+Arrows (+Shift / +Ctrl) | Focus / move / resize |
| SUPER+1..9 (+Shift), SUPER+Tab | Go to workspace / move window there (on the focused screen: every screen has its own 1–9), previous workspace |
| SUPER+V | Clipboard history (the picked item is pasted into the window you were in) |
| Print / Shift+Print / Alt+Print / SUPER+Print | Region shot / full shot / start or stop recording / color picker |
| Alt+Shift+4 / Alt+Shift+3 | Snip a region / click a window → annotate in swappy (Ctrl+C copies, Ctrl+S saves to ~/Pictures/Screenshots) |
| SUPER+N | Night light |
| SUPER+Shift+K | Keep awake on / off (the coffee cup in the bar) |
| SUPER+W | Wallpaper picker |
| SUPER+K or SUPER+/ | Keyboard shortcuts cheat sheet (searchable; also lists your own binds in `hypr/local.lua` that have a `description`) |
| SUPER+. / SUPER+= | Emoji picker (pasted into the window you were in) / calculator (Enter copies the result) |
| SUPER+, (+Shift) | Dismiss notification (all) |
| Ctrl+Space | Switch to/from Khmer (fcitx5) |
| 3-finger swipe | Switch workspace |

## Updating

| What | How |
|---|---|
| Everything (packages, dotfiles, tools) | Re-run the one-liner. It pulls the latest repo into `~/.local/share/fw13-hypr` and only adds what's missing (if you cloned the repo yourself: `git pull && ./install.sh`) |
| Fedora + Hyprland packages | `sudo dnf upgrade` |
| Dotfiles only | `chezmoi update` (your `~/.config/hypr/local.lua` is never overwritten) |
| Claude Code | Updates itself; `claude update` to force it |
| BIOS / firmware | `fwupdmgr refresh && fwupdmgr update` |

## Testing

- **CI** (`.github/workflows/test.yml`) runs the real installer in a clean `fedora:44` container on every push and once a week.
  - **It catches** renamed or missing packages, repo problems and script errors, and checks that the key programs and dotfiles ended up in place.
  - **Results:** the install report appears in the job summary.
- **Hardware only:** these can only be checked on the laptop itself: the Hyprland session, Wi-Fi/Bluetooth, fingerprint, suspend, VA-API video decode, the ambient light sensor, and Steam with gamescope.

## Hyprland config (Lua)

Hyprland's config is **Lua** (`~/.config/hypr/hyprland.lua`, which `require()`s `monitors`, `displays`, `looknfeel`, `input`, `windows`, `bindings`, …). The old `.conf` (hyprlang) format is deprecated since Hyprland 0.55 and due to be dropped, so this repo moved early.

- **Your own tweaks** go in `~/.config/hypr/local.lua` (Lua, e.g. `hl.config({ input = { kb_layout = "us,de" } })`). A leftover `local.conf` is no longer read; the installer warns if it had settings.
- **Saved display layouts** from the display panel live in `~/.config/hypr/displays.lua`.
- **Check a config without starting Hyprland:** `Hyprland --verify-config -c ~/.config/hypr/hyprland.lua` (CI runs this too). It catches syntax errors and unknown settings, but not wrong dispatcher arguments.
- **Scripts talk Lua too:** `hyprctl dispatch 'hl.dsp.focus({ workspace = "3" })'`, and `hyprctl eval '<lua>'` replaces `hyprctl keyword`.
- **Log in with "Hyprland (uwsm)"**: without uwsm the desktop portal (file pickers, screen sharing) and other session services don't start, so the installer hides the plain "Hyprland" entry (`/usr/local/share/wayland-sessions/hyprland.desktop`, `NoDisplay=true`). Under uwsm the standard autostart list also runs; `~/.config/autostart` hides nm-applet and blueman there, since the bar replaces their tray icons.

**Notes / later:**
- Per-screen workspaces are still a Python helper (`fw-workspaces`: a daemon plus one process per SUPER+N). With Lua they could live in the config itself: SUPER+N as a Lua function using `hl.get_active_monitor()`, hotplug via `hl.on(...)` monitor events, the login layout via exec rules. That means no background process and faster keys; it was left as a straight port for now to keep the migration small.
- In Hyprland 0.56.2, `hyprctl binds` reports the SUPER+drag binds without the `mouse` flag, but dragging works.

## Layout

```
install.sh                 entry point (preflight → repos → packages → system files → login/power → user phase → report)
packages/NN-*.txt          one package per line; 15-login and 61-power are conditional
repos/*.repo               vendor repos (vscode, mise)
system/                    copied into /usr/local/bin and /etc/systemd/system
dotfiles/                  chezmoi source (.chezmoiroot)
```

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md) (setup, rules, tests, roadmap). Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

GPL-3.0 — see [LICENSE](LICENSE). Packages installed by the script keep their own licenses.
