"""
Publisher logos for search-engine structured data (NewsArticle.publisher.logo) and Google News Publisher Center.

Google's article guidance wants a rectangular logo no taller than 60 px and no wider than 600 px, and Publisher Center
wants a square one at least 512 px. A transparent wordmark would vanish on a white results page, so both are the
wordmark on the show's dark footer colour. Palettes mirror make_frames.py; the files land in templates/.

Usage: python make_publisher_logo.py [denim|sage]
"""

import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates")

PALETTES = {
    "denim": {"bar": (31, 42, 58), "logo": "logo_horizontal_denim.png"},
    "sage": {"bar": (30, 38, 32), "logo": "logo_horizontal.png"},
}

WIDE_HEIGHT = 60           # Google: at most 60 px tall ...
WIDE_MAX_WIDTH = 600       # ... and at most 600 px wide
WIDE_PAD = (20, 12)        # left/right, top/bottom around the wordmark
SQUARE_SIDE = 512          # Publisher Center: square, 512 px or more
SQUARE_LOGO_WIDTH = 400


def _wordmark(palette_name):
    return Image.open(os.path.join(TEMPLATES, PALETTES[palette_name]["logo"])).convert("RGBA")


def wide_logo(palette_name="denim"):
    """Rectangular logo: 60 px tall, as wide as the wordmark needs (never over 600)."""
    mark = _wordmark(palette_name)
    height = WIDE_HEIGHT - 2 * WIDE_PAD[1]
    width = round(mark.width * height / mark.height)
    mark = mark.resize((width, height), Image.LANCZOS)
    canvas = Image.new("RGB", (width + 2 * WIDE_PAD[0], WIDE_HEIGHT), PALETTES[palette_name]["bar"])
    canvas.paste(mark, (WIDE_PAD[0], WIDE_PAD[1]), mark)
    assert canvas.width <= WIDE_MAX_WIDTH, "wordmark too wide for a 60 px logo"
    return canvas


def square_logo(palette_name="denim"):
    """Square logo for Publisher Center: the wordmark centred on the dark colour."""
    mark = _wordmark(palette_name)
    height = round(mark.height * SQUARE_LOGO_WIDTH / mark.width)
    mark = mark.resize((SQUARE_LOGO_WIDTH, height), Image.LANCZOS)
    canvas = Image.new("RGB", (SQUARE_SIDE, SQUARE_SIDE), PALETTES[palette_name]["bar"])
    canvas.paste(mark, ((SQUARE_SIDE - SQUARE_LOGO_WIDTH) // 2, (SQUARE_SIDE - height) // 2), mark)
    return canvas


def main(palette_name="denim"):
    for name, image in (("wide_60", wide_logo(palette_name)), ("square_512", square_logo(palette_name))):
        path = os.path.join(TEMPLATES, f"publisher_logo_{palette_name}_{name}.png")
        image.save(path, optimize=True)
        print(path, image.size)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "denim")
