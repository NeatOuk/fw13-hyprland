"""fw-settings pages. Each module has build() -> Gtk.Widget; the page may define refresh() on itself.

PAGES: (id, icon, title, module name). Order = sidebar order. A page in NEEDS is listed (sidebar, search,
`fw-settings <id>`, Jarvis cards) only when its command is installed.
"""
import shutil

NEEDS = {"syncthing": "syncthing"}  # page id → command it needs

_ALL = [
    ("network",    "", "Network",    "network"),
    ("bluetooth",  "", "Bluetooth",  "bluetooth"),
    ("sound",      "", "Sound",      "sound"),
    ("display",    "", "Display",    "display"),
    ("power",      "", "Power",      "power"),
    ("appearance", "", "Appearance", "appearance"),
    ("input",      "", "Input",      "input"),
    ("jarvis",     "", "Jarvis",     "jarvis"),
    ("agent",      "\uf120", "Coding agent", "agent"),
    ("security",   "", "Security",   "security"),
    ("system",     "", "System",     "system"),
    ("apps",       "\uf009", "Apps",       "apps"),
    ("syncthing",  "\uf2f1", "Syncthing",  "syncthing"),
    ("fw13",       "", "My Framework", "fw13"),
]
PAGES = [p for p in _ALL if p[0] not in NEEDS or shutil.which(NEEDS[p[0]])]
