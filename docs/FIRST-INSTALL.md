# First install on the Framework

What to expect when you run fw13-hyprland on a freshly installed Fedora, from the installer to the first day.

## Before you start

- **Fedora:** 44 **Workstation**, default btrfs layout (`root`/`home`), disk encryption on. Connect Wi-Fi in the Fedora installer; the MT7925 card works out of the box.
- **Power:** plug it in. Several GB get downloaded; Ollama with its ROCm libraries alone is about 5 GB installed.
- **Have ready** (any of them can be left blank and added later in Settings → fw13):
  - Chromium sign-in keys (`GOOGLE_API_KEY`, client ID, client secret)
  - restic repository and password (keep the password in a password manager)
  - Ollama Cloud API key

## 1. Run the installer

From GNOME's terminal:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/NeatOuk/fw13-hyprland/main/install.sh)
```

| Step | What you see |
|---|---|
| Preflight | Checks Fedora ≥ 44, asks "Continue?", then your sudo password once |
| Repositories | RPM Fusion, the Hyprland COPR, VS Code, mise, Cloudflare WARP |
| Packages | The longest part: one big dnf transaction (Hyprland, Steam, Chromium, VS Code, Ollama + ROCm, fonts…) |
| Citadel | Built from source into RPMs: a few minutes of compiler output |
| Login | greetd + tuigreet set up; GDM disabled (not removed), so GNOME stays one pick away |
| Fingerprint | Turned on for sudo, login and polkit |
| Dotfiles | chezmoi asks for the keys above, one by one, input hidden |
| Claude Code | Installed by Anthropic's own installer |
| Shell | Pick bash, zsh or fish |
| Questions at the end | "Enroll a fingerprint now?" (touch the sensor about 10 times), "Set up Timeshift snapshots now?" (yes), then a firmware update check |
| Report | `~/.local/state/fw13-hypr/install-report.txt`: packages added, total size, the largest 25 |

If anything fails, re-run the same one-liner; it is safe to repeat.

## 2. Reboot

A **text login screen** (tuigreet) replaces GNOME's: type your password, Hyprland is preselected. F2 switches the session to GNOME if you ever need it.

## 3. First Hyprland login

- **Look:** thin bar with the Framework gear on the left, Tokyo Night colours (or colours from your wallpaper).
- **Windows:** kitty on workspace 1, Chromium on workspace 2 (or on the external monitor's workspace 1).
- **Hardware check:** a "Hardware check" notification; **Open** shows the Framework checks (CPU driver, GPU, Wi-Fi, Bluetooth, battery and charge limit, firmware, fingerprint, light sensor, suspend). WARN can mean the expected value wasn't verifiable before real hardware existed: report those.
- **Citadel** asks about each app's first outgoing connection (Chromium, `warp-svc`, Steam…). Answer Always or Block; enforcement is on, so unanswered connections stay blocked.
- **Health:** about 15 minutes after login, `fw-health` runs. One notification with **Diagnose** if something needs attention; silent otherwise.

## 4. First hour

- `fwupdmgr update`: BIOS and the Secure Boot certificate updates.
- Battery icon → 80 % charge limit.
- SUPER+W: pick a wallpaper; the colours follow it.
- Optional: Settings → Display → auto-brightness (off by default; the curve still needs tuning on this panel).
- Try volume/brightness keys (popup at the bottom), SUPER+A (Jarvis), SUPER+. (emoji), SUPER+= (calculator), the bell icon.

## 5. Framework-only checks (Stage 7)

These could not be tested on other hardware:

- [ ] `fw-hwcheck` values: amd-pstate-epp, `amdgpu_bl*`, platform profiles, charge-limit path, light sensor
- [ ] Do not disturb hides popups while the bell still counts them
- [ ] Volume/brightness popup over a fullscreen game (gamescope) and the F-row keys
- [ ] Wi-Fi and Bluetooth after suspend/resume
- [ ] Fingerprint at sudo and at the login screen
- [ ] Steam, Battle.net (Lutris), VA-API (`vainfo` via distrobox)
- [ ] Ollama on the Radeon 890M (ROCm)
- [ ] Auto-brightness curve
- [ ] `sudo fw-timeshift-restore --list` and a dry run; a real restore + `undo` when comfortable
