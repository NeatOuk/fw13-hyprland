"""Settings search over every control: each page records its heading()/row() calls in page.index (pages/common.py),
so a new row is found as soon as it exists. SYNONYMS only adds words people type that no label contains.

  PYTHONPATH=~/.local/lib python3 -m fw13.pages.search test   build every page headless, check common queries
"""
import importlib
import sys
import time

from . import PAGES

TITLES = {pid: title for pid, _icon, title, _mod in PAGES}
ORDER = {pid: i for i, (pid, *_rest) in enumerate(PAGES)}

# (page id, section to jump to, row text ("" = the section itself), hint, extra words)
SYNONYMS = [
    ("network", "Wi-Fi", "", None, "wifi wlan wireless internet"),
    ("power", "Battery", "", None, "battery charge limit charging"),
    ("bluetooth", "My devices", "", None, "bluetooth headphones headset earbuds speaker"),
    ("appearance", "Theme", "Colours", None, "dark mode light mode colors colours from wallpaper palette"),
    ("input", "Touchpad", "", None, "touchpad trackpad mouse"),
    ("input", "Keyboard", "Keyboard shortcuts", "SUPER+K or SUPER+/ lists every shortcut",
     "hotkeys shortcuts keybindings keys"),
]


def hits(query, pages):
    """[(page id, section, row text, hint)] for a query: every word (case-insensitive) must appear in the page
    title/id, section, row text, hint or synonyms. A page or section whose name alone matches is one hit, not
    all its rows."""
    words = query.lower().split()
    if not words:
        return []
    entries = [(pid, s, t, h, "") for pid, page in pages.items() for s, t, h, _w in page.index]
    entries += SYNONYMS
    out, seen = [], set()
    for pid in sorted(TITLES, key=ORDER.get):
        page_words = f"{TITLES[pid]} {pid}".lower()
        if all(w in page_words for w in words):
            out.append((pid, "", "", None))
            continue
        for p, s, t, h, extra in entries:
            if p != pid or (s, t) in seen:
                continue
            if t and all(w in f"{page_words} {s}".lower() for w in words):
                continue  # the section's own hit covers its rows
            hay = f"{page_words} {s} {t} {h or ''} {extra}".lower()
            if all(w in hay for w in words):
                seen.add((s, t))
                out.append((pid, s, t, h))
        seen.clear()
    return out


def label(hit):
    pid, section, text, _hint = hit
    return " › ".join(x for x in (TITLES[pid], section, text) if x)


def find(page, section, text):
    """The widget of a hit on a built page (its current render), or the section heading, or None."""
    for want in ((section, text), (section, "")):
        for s, t, _h, w in page.index:
            if (s, t) == want:
                return w
    return None


CASES = [("hibernate", "power"), ("night light", "display"), ("noise", "sound"), ("vpn", "network"),
         ("ssh", "security"), ("warn at", "power"), ("weather", "system"), ("colour from", "appearance"),
         ("jarvis memory", "jarvis"), ("fan", "fw13"), ("wifi", "network"), ("shortcuts", None)]


def test():
    from gi.repository import GLib  # pages import Gtk 3 first
    pages, took = {}, {}
    for pid, _icon, _title, mod in PAGES:
        t = time.monotonic()
        pages[pid] = importlib.import_module(f"fw13.pages.{mod}").build()
        took[pid] = time.monotonic() - t
    print("build:", " ".join(f"{p} {s:.2f}s" for p, s in took.items()), f"total {sum(took.values()):.2f}s")

    def failing():
        return [(q, want) for q, want in CASES
                if not (hs := hits(q, pages)) or (want and want not in {h[0] for h in hs})]
    deadline = time.monotonic() + 20  # async pages (System, Security, My Framework) render after their loads
    ctx = GLib.MainContext.default()
    while failing() and time.monotonic() < deadline:
        if not ctx.iteration(False):
            time.sleep(0.05)
    for q, _want in CASES:
        print(f"{q!r}: " + "; ".join(label(h) for h in hits(q, pages)[:4]))
    bad = failing()
    assert not bad, f"no hit on the expected page: {bad}"
    assert all(find(pages[h[0]], h[1], h[2]) for h in hits("hibernate", pages)), "hit without a widget"
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        sys.exit(__doc__)
