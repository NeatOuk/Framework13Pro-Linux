#!/bin/sh
# hypridle.conf is owned by Settings → Power (generated from ~/.config/fw13/settings.json, defaults
# dim 2.5 min · lock 5 · screen off 5.5 · suspend 15). Write it once on install; this also replaces
# older copies whose `hyprctl dispatch dpms` commands stopped working with the Lua Hyprland config.
python3 -c 'import os, sys; sys.path.insert(0, os.path.expanduser("~/.local/lib")); from fw13 import idle; idle.write()' || true
