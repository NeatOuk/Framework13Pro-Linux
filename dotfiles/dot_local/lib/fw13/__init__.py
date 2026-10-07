"""Shared code for the fw13-hypr Python tools (fw-settings, fw-display-panel, fw-workspaces, …).

Deployed to ~/.local/lib/fw13; scripts do `sys.path.insert(0, os.path.expanduser("~/.local/lib"))`.
Modules without "ui" in the name don't import GTK.
"""
