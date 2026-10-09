"""The terminal every fw13 launcher opens: kitty (default) or Ghostty, picked in Settings → fw13 (store `terminal`).

argv() maps one interface (command, window class, keep open, working folder) onto each terminal's flags, so callers
never name a terminal. Classes must be valid GTK application ids for Ghostty: fw13.jarvis, fw13.btop.

  fw-term [--class C] [--hold] [--dir D] [-e cmd…]   (bash, Lua, waybar, fuzzel) → execs the chosen terminal
  python3 -m fw13.terminal --print …                 prints the argv instead (tests)
"""
import os
import shutil
import sys

from . import store

# id → (label, program)
TERMINALS = {"kitty": ("kitty", "kitty"), "ghostty": ("Ghostty", "ghostty")}
DEFAULT = "kitty"


def installed():
    """[(id, label, is_installed)] in a fixed order, for the Settings combo."""
    return [(k, lbl, shutil.which(prog) is not None) for k, (lbl, prog) in TERMINALS.items()]


def current():
    """The chosen terminal if it's installed, else kitty."""
    t = store.get("terminal")
    if t in TERMINALS and shutil.which(TERMINALS[t][1]):
        return t
    return DEFAULT


def argv(cmd=None, cls=None, hold=False, cwd=None, term=None):
    term = term or current()
    if term == "ghostty":
        out = ["ghostty", "--gtk-single-instance=false"]
        if cls:
            out.append(f"--class={cls}")
        if hold:
            out.append("--wait-after-command=true")
        if cwd:
            out.append(f"--working-directory={cwd}")
    else:
        out = ["kitty"]
        if cls:
            out += ["--class", cls]
        if hold:
            out.append("--hold")
        if cwd:
            out += ["--directory", cwd]
    if cmd:
        out += ["-e", *cmd]
    return out


def main(args):
    cls, hold, cwd, show, cmd = None, False, None, False, None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--class" and i + 1 < len(args):
            cls, i = args[i + 1], i + 1
        elif a == "--dir" and i + 1 < len(args):
            cwd, i = args[i + 1], i + 1
        elif a == "--hold":
            hold = True
        elif a == "--print":
            show = True
        elif a == "-e":
            cmd = args[i + 1:]
            break
        else:
            print(f"fw-term: unknown option {a}", file=sys.stderr)
            return 2
        i += 1
    out = argv(cmd or None, cls, hold, cwd)
    if show:
        print("\n".join(out))
        return 0
    os.execvp(out[0], out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
