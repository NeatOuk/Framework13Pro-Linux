"""fw-settings pages. Each module has build() -> Gtk.Widget; the page may define refresh() on itself.

PAGES: (id, icon, title, module name). Order = sidebar order.
"""
PAGES = [
    ("network",    "", "Network",    "network"),
    ("bluetooth",  "", "Bluetooth",  "bluetooth"),
    ("sound",      "", "Sound",      "sound"),
    ("display",    "", "Display",    "display"),
    ("power",      "", "Power",      "power"),
    ("appearance", "", "Appearance", "appearance"),
    ("input",      "", "Input",      "input"),
    ("system",     "", "System",     "system"),
]
