# Jarvis — briefing for AI agents on this computer

You are helping the owner of this laptop, started from Jarvis (SUPER+A) or from a crash
notification. Explain in plain language; the owner decides what changes.

## The system
- Fedora (regular edition, not Atomic) with a **Hyprland** desktop started through **uwsm**, set up by the
  fw13-hypr installer. Its repo: `~/Framework13Pro-Linux` (owner's clone) or `~/.local/share/fw13-hypr`.
  That repo's `CLAUDE.md` holds the project rules; read it before proposing changes to the desktop.
- Target hardware: Framework Laptop 13, AMD Ryzen AI 9 HX 370 (Radeon 890M, MediaTek MT7925 Wi-Fi).
- Dotfiles are managed by **chezmoi** from the repo's `dotfiles/` dir. Editing `~/.config/...` directly gets
  overwritten on the next `chezmoi update`; machine-only Hyprland tweaks go in `~/.config/hypr/local.lua`. Hyprland's config is **Lua** (`hyprland.lua`;
  `hyprctl dispatch` takes Lua, `hyprctl eval` replaces `keyword`).
- Bar: waybar. Menus: fuzzel. Notifications: mako (`fw-notify "title" "body"`). Terminal: kitty.
- Helpers in `~/.local/bin/fw-*`: control-center, power-panel, display-panel, opencode (Ollama servers),
  claude-limits, workspaces (per-screen workspaces), crash-watch, jarvis, capture, record, nightlight.
- Logs: `journalctl` (system journal is readable), `journalctl --user`, `coredumpctl`.
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
