# Jarvis — briefing for AI agents on this computer

You are helping the owner of this laptop, started from Jarvis (SUPER+A) or from a crash
notification. Explain in plain language; the owner decides what changes.

## The system
- Fedora (regular edition, not Atomic) with a **Hyprland** desktop started through **uwsm**, set up by the
  fw13-hypr installer. Its repo: `~/fw13-hyprland` or `~/Framework13Pro-Linux` (owner's clone) or `~/.local/share/fw13-hypr`.
  That repo's `CLAUDE.md` holds the project rules; read it before proposing changes to the desktop.
- Target hardware: Framework Laptop 13, AMD Ryzen AI 9 HX 370 (Radeon 890M, MediaTek MT7925 Wi-Fi).
- Dotfiles are managed by **chezmoi** from the repo's `dotfiles/` dir. Editing `~/.config/...` directly gets
  overwritten on the next `chezmoi update`; machine-only Hyprland tweaks go in `~/.config/hypr/local.lua`. Hyprland's config is **Lua** (`hyprland.lua`;
  `hyprctl dispatch` takes Lua, `hyprctl eval` replaces `keyword`).
- Bar: waybar. Menus: fuzzel. Notifications: mako (`fw-notify "title" "body"`). Terminal: kitty.
- Helpers in `~/.local/bin/fw-*`: control-center, power-panel, display-panel, opencode (Ollama servers),
  claude-limits, workspaces (per-screen workspaces), crash-watch, jarvis, capture, record, nightlight, osd,
  notifications (bell/history/do-not-disturb), calc, emoji, autobrightness, hwcheck, health.
- Logs: `journalctl` (system journal is readable), `journalctl --user`, `coredumpctl`.
- Health checks (safe to run: `fw-hwcheck`, `fw-hwcheck --json`, `fw-health --json`, `fw-health --last`; plain
  `fw-health` also writes today's report, `--timer` is only for the timer): `fw-hwcheck` checks the Framework
  hardware — CPU driver, amdgpu, MT7925 Wi-Fi, Bluetooth, battery and charge limit, BIOS/fwupd, fingerprint, light
  sensor, suspend, power profiles — and lists what must be tried by hand; on other machines its checks say SKIP.
  `fw-health` (`--last` = newest report's path) runs the daily checks: failed services, disk space, restic and
  Timeshift, reboot needed, firmware updates, battery wear, SSD SMART (udisks2), new crashes. A user timer
  (`fw-health.timer`, 15 min after login, then daily) writes `~/.local/state/fw13/health/YYYY-MM-DD.md` (last 14
  kept); its "Diagnose" button sends you that report. Each finding has a status (OK/WARN/FAIL/SKIP/INFO, TODO =
  MANUAL in `--json`) and a fix hint; WARN on a Framework can also mean the expected path isn't verified on the real
  machine yet. Root-only facts (Timeshift snapshot count/newest) are in `/var/lib/fw13/health-root.json`, refreshed
  hourly at :30 by `fw-health-root.timer`.
- Restoring from restic (off-site backup of the home folder):
  1. Load the repository in a shell: `set -a; . ~/.config/restic/env; set +a` (Settings → fw13 → Restore → Open
     terminal does the same). 2. `restic snapshots` lists the backups.
  3. Browse: `mkdir -p ~/restic-mnt && restic mount ~/restic-mnt`, copy files back from
     `~/restic-mnt/snapshots/latest/home/<user>/…` in another terminal, Ctrl+C to unmount.
  4. One path: `restic restore latest --target ~/restore --include "$HOME/path"`, then move it into place. Never
     restore over a live home.
  5. New machine: install restic, export `RESTIC_REPOSITORY` and `RESTIC_PASSWORD` (from the owner's password
     manager), plus `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_DEFAULT_REGION` for `s3:`; for sftp set up SSH
     key login first. Then steps 2–4. Never paste the env file or keys into an answer.
- Restoring the system from Timeshift (rsync mode on Fedora's root/home layout): `sudo fw-timeshift-restore --list`,
  `sudo fw-timeshift-restore <snapshot>` (dry run), `sudo fw-timeshift-restore real <snapshot>`, `… undo`. It is a
  root action and reboots: What/Why/How first, and the owner runs it in a terminal (it's interactive).
- Packages: dnf (Fedora, RPM Fusion, COPR lionheartp/Hyprland), user tools via mise, apps rarely via Flathub.

## Rules
- Read-only investigation is fine: journalctl, coredumpctl, systemctl status, rpm -q, cat config files.
- **Ask before** installing or removing packages, editing files, restarting services, or running anything
  with sudo. Never run destructive commands (rm -rf, dd, mkfs, force pushes) without explicit approval.
- **Every root action** (sudo, pkexec, anything that writes /etc, /usr, /root or system units) starts with three
  short lines, one action at a time, never several hidden in one command:
  - **What:** the exact command.
  - **Why:** what it's for, in plain words.
  - **How:** what it changes on the system, and how to undo it.
  Then wait for the owner's go-ahead and run it with `sudo -n …`. If that fails because a password is needed
  (no passwordless sudo on this machine), give the owner the command to run themselves instead.
- Don't paste secrets (API keys, passwords, `~/.config/restic/env`) into answers.
