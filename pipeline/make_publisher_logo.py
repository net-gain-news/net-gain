"""
Publisher logos for search-engine structured data (the Net Gain News organization's logo) and Google News Publisher Center.

The publisher is the SITE ("Net Gain News"), not any one show: Google News keys a publication to the website and names it
from the site name, so the sitemap, the schema publisher and the logo all say Net Gain News. The wordmark is the show
wordmark with "Edtech" swapped for "News" (same font, size and tracking, measured against the existing artwork).

Google's article guidance wants a rectangular logo no taller than 60 px and no wider than 600 px, and Publisher Center
wants a square one at least 512 px. A transparent wordmark would vanish on a white results page, so both are the
wordmark on the show's dark footer colour. Palettes mirror make_frames.py; the files land in templates/.

Usage: python make_publisher_logo.py [denim|sage]
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

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

# The show wordmark's artwork geometry (px, at its native 212 px height): the cap height of its "N", and the font settings
# that reproduce its show-name word exactly (Archivo 500, size 283, tracking -11 matched "Edtech" to the pixel).
FONT_PATH = os.path.join(HERE, "fonts", "Archivo[wdth,wght].ttf")
CAP_HEIGHT = 195
NAME_WEIGHT, NAME_SIZE, NAME_TRACKING = 500, 283, -11
WORD_GAP_MIN = 75          # gaps wider than this separate mark | "Net Gain" | show name (letter/word gaps are <= 61)


def _show_wordmark(palette_name):
    return Image.open(os.path.join(TEMPLATES, PALETTES[palette_name]["logo"])).convert("RGBA")


def _column_segments(image):
    """Runs of columns that have ink, as (first, last), merging gaps of 6 px or less."""
    columns, _ = image.getchannel("A").point(lambda v: 255 if v > 20 else 0).getprojection()
    segments, start, last, gap = [], None, None, 0
    for x, ink in enumerate(columns):
        if ink:
            if start is None:
                start = x
            last, gap = x, 0
        elif start is not None:
            gap += 1
            if gap > 6:
                segments.append((start, last))
                start = None
    if start is not None:
        segments.append((start, last))
    return segments


def news_wordmark(palette_name="denim"):
    """The show wordmark with its show-name word ("Edtech") replaced by "News", in the same colour, font and size."""
    show = _show_wordmark(palette_name)
    segments = _column_segments(show)
    breaks = [i for i in range(1, len(segments)) if segments[i][0] - segments[i - 1][1] > WORD_GAP_MIN]
    assert len(breaks) == 2, "unexpected wordmark layout: cannot find the show-name word"
    name_start = segments[breaks[1]][0]

    mark_colour = show.getpixel(((segments[0][0] + segments[0][1]) // 2, show.height // 2))
    blue = next(show.getpixel((x, y)) for x in range(name_start, name_start + 40) for y in range(show.height) if show.getpixel((x, y))[3] > 250)

    font = ImageFont.truetype(FONT_PATH, NAME_SIZE)
    font.set_variation_by_axes([NAME_WEIGHT, 100])
    baseline = 13 + CAP_HEIGHT

    scratch = Image.new("L", (3000, 600), 0)
    draw, x = ImageDraw.Draw(scratch), 100
    for ch in "News":
        draw.text((x, 400), ch, font=font, fill=255, anchor="ls")
        x += font.getlength(ch) + NAME_TRACKING
    ink = scratch.getbbox()
    word = scratch.crop((ink[0], 400 - baseline, ink[2], 400 - baseline + show.height))

    canvas = Image.new("RGBA", (name_start + word.width + 4, show.height), (0, 0, 0, 0))
    canvas.paste(show.crop((0, 0, name_start, show.height)), (0, 0))
    colour_layer = Image.new("RGBA", word.size, blue[:3] + (255,))
    canvas.paste(colour_layer, (name_start, 0), word)
    del mark_colour
    return canvas


def _wordmark(palette_name):
    return news_wordmark(palette_name)


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
    wordmark_path = os.path.join(TEMPLATES, f"logo_horizontal_{palette_name}_news.png")
    news_wordmark(palette_name).save(wordmark_path, optimize=True)
    print(wordmark_path)
    for name, image in (("wide_60", wide_logo(palette_name)), ("square_512", square_logo(palette_name))):
        path = os.path.join(TEMPLATES, f"publisher_logo_{palette_name}_news_{name}.png")
        image.save(path, optimize=True)
        print(path, image.size)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "denim")
