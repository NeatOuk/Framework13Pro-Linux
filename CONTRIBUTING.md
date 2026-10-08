# Contributing / continuing development

How to pick up work on fw13-hyprland. The full rules and file map are in [CLAUDE.md](CLAUDE.md); this is the quick start.

## Set up

```bash
git clone https://github.com/NeatOuk/fw13-hyprland ~/fw13-hyprland
cd ~/fw13-hyprland
```

A machine already set up by the installer has everything needed (Hyprland, chezmoi via mise, shellcheck via `mise use -g shellcheck`, Python GTK). The installed copy lives in `~/.local/share/fw13-hypr` (installer) and `~/.local/share/chezmoi` (dotfiles); both track the pushed repo, not your clone.

## Where things live

| Area | Path |
|---|---|
| Installer | `install.sh`, `packages/*.txt`, `repos/*.repo` |
| Root files | `system/usr/local/bin/`, `system/etc/systemd/system/` |
| Dotfiles (chezmoi source) | `dotfiles/`: Hyprland Lua config in `dot_config/hypr/`, helpers in `dot_local/bin/executable_fw-*`, the shared Python library in `dot_local/lib/fw13/` |
| Jarvis briefing | `dotfiles/dot_local/share/jarvis/AGENTS.md` |
| CI | `.github/workflows/test.yml` |

## Rules that matter most

1. **Ask before adding any package** (weak deps and "small utilities" included). Order of sources: Fedora → vendor repo → RPM Fusion → COPR → upstream installer → Flathub.
2. **Never remove the user's existing stack** (DE, display manager, power daemon); detect and adapt. Re-running must be safe.
3. **No secrets in git or in command lines.** Secrets come from chezmoi prompts into `private_` 0600 files.
4. **Hyprland-only behaviour stays gated**: GNOME/KDE on the same account must be unaffected.
5. Hyprland config is **Lua**; colours come only from the generated theme files; icons are Font Awesome 6 Free.
6. Live tests never act on the active window, and processes are stopped by PID (never `pkill -f`).

## Test before you commit

```bash
# Lint (what CI runs): split scripts by their shebang line
sh=() py=()
for f in install.sh system/usr/local/bin/* dotfiles/dot_local/bin/executable_*; do
  case "$(head -1 "$f")" in *python3*) py+=("$f") ;; *) sh+=("$f") ;; esac
done
shellcheck -S warning "${sh[@]}"
python3 -c 'import ast,sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]' \
  "${py[@]}" $(find dotfiles/dot_local/lib -name '*.py')

# Dotfiles into a throwaway home (isolate every XDG dir), secrets blank
T=$(mktemp -d); HOME=$T XDG_CONFIG_HOME=$T/.config XDG_DATA_HOME=$T/.local/share \
  XDG_STATE_HOME=$T/.local/state XDG_CACHE_HOME=$T/.cache \
  chezmoi init --source=$PWD --apply --exclude=scripts

# Hyprland config check on the rendered copy
XDG_RUNTIME_DIR=$(mktemp -d) Hyprland --verify-config -c "$T/.config/hypr/hyprland.lua"
```

Also: JSON-parse `waybar/config.jsonc` (strip `//` comments), check for duplicate keybinds (`hyprctl -j binds`), and render once with secrets filled. CI must be green on `fedora:44`.

Local dotfile edits are **not** what `chezmoi update` applies: it pulls the pushed repo. Push first, then `chezmoi update --init` on the machine.

## Commits

- One feature or fix per commit, conventional prefix: `feat(area):`, `fix(area):`, `chore:`, `docs:`.
- Update README (user-facing) and CLAUDE.md (rules, layout) in the same change.
- Hardware-only behaviour (Framework 13 AMD) goes on the checklist in [docs/FIRST-INSTALL.md](docs/FIRST-INSTALL.md) until verified.

## Roadmap

Done: Stages 1–6 (session/PATH fixes, power readout, OSD, notification bell, calculator and emoji, restic S3, health checks, auto-brightness, `fw-timeshift-restore` v1).

Next:
- **Stage 7, Framework-only:** the checklist in `docs/FIRST-INSTALL.md`.
- **Restore v2:** live-USB mode, `--with-home`, `cleanup`, a 7-day reminder to delete the old root.
- **Ollama:** decide on the Framework (ROCm adds about 5 GB; maybe make it optional).
- **Workspaces in Lua:** move `fw-workspaces` into the Hyprland config (no daemon).

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
