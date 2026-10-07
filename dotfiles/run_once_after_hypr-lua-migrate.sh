#!/bin/sh
# One-time move to Hyprland's Lua config: carry over the user's own legacy files.
#  - displays.conf (fw-display-panel layouts) → displays.lua, if that has no layouts yet
#  - local.conf with real settings → can't be translated automatically; tell the user
hypr="$HOME/.config/hypr"
python3 - "$hypr/displays.conf" "$hypr/displays.lua" <<'PY'
import json, re, sys
legacy, target = sys.argv[1], sys.argv[2]
try:
    lines = [l.strip() for l in open(legacy)]
    current = open(target).read() if __import__("os").path.exists(target) else ""
except OSError:
    sys.exit(0)
if "hl.monitor(" in current:
    sys.exit(0)  # already has Lua layouts
out = []
for l in lines:
    m = re.match(r"monitor\s*=\s*desc:([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)(?:,\s*transform,\s*(\d+))?", l)
    if m:
        desc, mode, pos, scale, tf = (g.strip() if g else g for g in m.groups())
        out.append(f"hl.monitor({{ output = {json.dumps('desc:' + desc)}, mode = {json.dumps(mode)}, "
                   f"position = {json.dumps(pos)}, scale = {float(scale):g}"
                   + (f", transform = {tf} }})" if tf else " })"))
if out:
    with open(target, "w") as f:
        f.write("-- Written by fw-display-panel (bar display icon → Apply → Keep).\n"
                "-- One line per monitor, matched by description. Delete a line to return it to the default.\n")
        f.write("\n".join(out) + "\n")
    print(f"hypr-lua-migrate: {len(out)} saved display layout(s) → {target}")
PY
if [ -f "$hypr/local.conf" ] && grep -qvE '^[[:space:]]*(#|$)' "$hypr/local.conf"; then
  msg="Hyprland now uses Lua: move your settings from ~/.config/hypr/local.conf into local.lua (it is no longer read)."
  echo "hypr-lua-migrate: $msg"
  command -v fw-notify >/dev/null && fw-notify "Hyprland config" "$msg" 2>/dev/null || true
fi
exit 0
