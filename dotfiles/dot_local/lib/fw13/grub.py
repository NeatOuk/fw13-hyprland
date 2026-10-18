"""GRUB boot menu theme, drawn from the desktop theme: the wallpaper blurred and dimmed, the menu on a rounded card,
the selected entry as an accent bar, Framework's gear above.

`sudo fw-grub-theme` runs this as you (runuser) and copies the folder to /boot/grub2/themes/fw13; GRUB can't read your
home folder (it may be encrypted) and only draws PNG/JPEG, so everything is rendered here first (Pillow; the gear's SVG
through GdkPixbuf). Files: theme.txt, background.jpg (none without a desktop image), card_*.png and select_*.png
(GRUB's 9-slice pixmap styles: nw n ne w c e sw s se), logo.png. Fonts (JetBrains Mono Regular/Bold 32 px) are made
by fw-grub-theme with grub2-mkfont; FONT/BOLD below must match the names it makes.

  python3 -m fw13.grub [DIR]   render (default ~/.config/fw13/theme/grub)
  python3 -m fw13.grub test    self-check into a temporary folder
"""
import os
import sys
import tempfile

from . import theme

OUT = os.path.join(theme.DIR, "grub")
DESKTOP = os.path.join(theme.DIR, "desktop.jpg")
SIZE = (2880, 1920)   # the panel's native mode, which GRUB_GFXMODE=auto picks
FONT, BOLD = "JetBrains Mono Regular 32", "JetBrains Mono Bold 32"
CARD_R, SEL_R, LOGO = 36, 16, 120   # corner radii and gear size, px
SLICES = ("nw", "n", "ne", "w", "c", "e", "sw", "s", "se")


def _rgba(hexcolor, alpha):
    c = hexcolor.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def nine_slice(Image, ImageDraw, fill, r, out_dir, prefix):
    """A rounded rectangle cut into GRUB's 9 pieces (corners r x r, edges and centre 1 px stretched by GRUB)."""
    big = Image.new("RGBA", (2 * r + 1, 2 * r + 1), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle((0, 0, 2 * r, 2 * r), radius=r, fill=fill)
    boxes = {"nw": (0, 0, r, r), "n": (r, 0, r + 1, r), "ne": (r + 1, 0, 2 * r + 1, r),
             "w": (0, r, r, r + 1), "c": (r, r, r + 1, r + 1), "e": (r + 1, r, 2 * r + 1, r + 1),
             "sw": (0, r + 1, r, 2 * r + 1), "s": (r, r + 1, r + 1, 2 * r + 1), "se": (r + 1, r + 1, 2 * r + 1, 2 * r + 1)}
    for name in SLICES:
        big.crop(boxes[name]).save(os.path.join(out_dir, f"{prefix}_{name}.png"))


def background(Image, ImageFilter, p, out_dir):
    """The desktop image covering the screen, blurred and dimmed toward the theme's background; False without one."""
    try:
        img = Image.open(DESKTOP).convert("RGB")
    except OSError:
        return False
    w, h = img.size
    scale = max(SIZE[0] / w, SIZE[1] / h)
    img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    left, top = (img.width - SIZE[0]) // 2, (img.height - SIZE[1]) // 2
    img = img.crop((left, top, left + SIZE[0], top + SIZE[1])).filter(ImageFilter.GaussianBlur(48))
    img = Image.blend(img, Image.new("RGB", SIZE, _rgba(p["bg"], 255)[:3]), 0.55)
    img.save(os.path.join(out_dir, "background.jpg"), "JPEG", quality=88)
    return True


def logo(p, out_dir):
    """Framework's gear in the accent colour as PNG (GRUB has no SVG); False when GdkPixbuf can't draw it."""
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
        loader.write(theme._framework_logo(p, LOGO).encode())
        loader.close()
        loader.get_pixbuf().savev(os.path.join(out_dir, "logo.png"), "png", [], [])
        return True
    except Exception:  # noqa: BLE001 — no gear is only a plainer menu
        return False


def theme_txt(p, has_bg, has_logo):
    lines = ['# ' + theme.HEAD, "# Installed into /boot/grub2/themes/fw13 by: sudo fw-grub-theme",
             'title-text: ""', f'desktop-color: "{p["bg"]}"', f'terminal-font: "{FONT}"']
    if has_bg:
        lines.append('desktop-image: "background.jpg"\ndesktop-image-scale-method: "crop"')
    if has_logo:
        lines.append(f'+ image {{ top = 33%-{LOGO + 48} left = 50%-{LOGO // 2} width = {LOGO} height = {LOGO} '
                     'file = "logo.png" }')
    lines += ["+ boot_menu {",
              "  left = 20% top = 33% width = 60% height = 26%",  # the rescue entry's title is ~82 characters
              '  menu_pixmap_style = "card_*.png"',
              '  selected_item_pixmap_style = "select_*.png"',
              f'  item_font = "{FONT}"', f'  item_color = "{p["fg"]}"',
              f'  selected_item_font = "{BOLD}"', f'  selected_item_color = "{p["fg_bright"]}"',
              "  item_height = 64 item_padding = 24 item_spacing = 8 icon_width = 0 icon_height = 0",
              "  scrollbar = false", "}"]
    for top, text, lid in (("66%", "Starting in %d s", ' id = "__timeout__"'),
                           ("71%", "↑ ↓ choose · Enter start · e edit", "")):
        lines.append(f'+ label {{{lid} top = {top} left = 0 width = 100% height = 48 align = "center" '
                     f'text = "{text}" font = "{FONT}" color = "{p["fg"]}" }}')
    return "\n".join(lines) + "\n"


def render(out_dir=OUT, p=None):
    from PIL import Image, ImageDraw, ImageFilter
    p = p or theme.palette()
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):   # a theme without a background or gear must not keep the old one
        if f.endswith((".png", ".jpg")):
            os.remove(os.path.join(out_dir, f))
    nine_slice(Image, ImageDraw, _rgba(p["bg"], 225), CARD_R, out_dir, "card")
    nine_slice(Image, ImageDraw, _rgba(p["accent"], 90), SEL_R, out_dir, "select")
    has_bg = background(Image, ImageFilter, p, out_dir)
    text = theme_txt(p, has_bg, logo(p, out_dir))
    with open(os.path.join(out_dir, "theme.txt"), "w") as f:
        f.write(text)
    return out_dir


def test():
    with tempfile.TemporaryDirectory() as t:
        render(t, theme.TOKYO_NIGHT)
        files = set(os.listdir(t))
        assert {f"{s}_{n}.png" for s in ("card", "select") for n in SLICES} <= files, files
        txt = open(os.path.join(t, "theme.txt")).read()
        assert ("background.jpg" in files) == ("background.jpg" in txt)
        assert ("logo.png" in files) == ("logo.png" in txt)
        from PIL import Image
        assert Image.open(os.path.join(t, "card_nw.png")).size == (CARD_R, CARD_R)
        assert Image.open(os.path.join(t, "card_c.png")).getpixel((0, 0)) == _rgba(theme.TOKYO_NIGHT["bg"], 225)
        assert txt.count("{") == txt.count("}") and "__timeout__" in txt
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        print(render(*(sys.argv[1:2] or [OUT])))
