"""
Net Gain News publisher logos for search-engine structured data and Google News, derived from the OFFICIAL artwork in
templates/brand/ (never redrawn from a font):

  net_gain_news_logo_stacked.png   2000x2000, the mark above "Net Gain / News", cream (#edeae4) on near-black (#13110d)
  net_gain_news_mark.png           1024x1024, the mark alone, same colours

The publisher is the SITE (Net Gain News), not any one show: Google News keys a publication to the website and names it
from the site name. Outputs (templates/):

  publisher_logo_news_wide_60_dark.png    horizontal lockup, 60 px tall (Google: at most 60 px tall and 600 px wide)
  publisher_logo_news_square_512_dark.png the official stacked logo at 512 px (Publisher Center; AIOSEO's Organization logo)
  publisher_logo_news_mark_512_dark.png   the mark alone at 512 px (site icon)
  ...and a "_light" twin of each with the colours flipped (near-black on white) for light surfaces.

The horizontal lockup puts the official pieces on one line - mark, "Net Gain", "News" - with the spacing of the site's
header lockup (mark-to-text gap 0.56 cap heights, word space 0.42). Every pixel of artwork comes from the official files;
colour flips re-colour the same ink coverage.

Usage: python make_publisher_logo.py
"""

import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.join(HERE, "templates", "brand")
TEMPLATES = os.path.join(HERE, "templates")

DARK = {"bg": (19, 17, 13), "fg": (237, 234, 228)}        # the official colours
LIGHT = {"bg": (255, 255, 255), "fg": (19, 17, 13)}       # the same artwork, flipped
THEMES = {"dark": DARK, "light": LIGHT}

WIDE_HEIGHT = 60           # Google: at most 60 px tall ...
WIDE_MAX_WIDTH = 600       # ... and at most 600 px wide
WIDE_CAP_HEIGHT = 34       # cap height of the wordmark inside the 60 px strip
WIDE_PAD_X = 20
SQUARE_SIDE = 512

MARK_GAP_CAPS = 0.56       # gap from the mark to the wordmark, in cap heights (site header lockup)
WORD_GAP_CAPS = 0.42       # space between "Net Gain" and "News", in cap heights
INK = 60                   # alpha above this counts as ink when finding bounds
NOISE_FLOOR = 24           # the source files carry faint compression noise in their background; below this is background


def _coverage(path, theme=DARK):
    """The artwork as an 8-bit ink-coverage mask: 0 = background, 255 = full foreground."""
    luminance = Image.open(path).convert("L")
    lo, hi = sum(theme["bg"]) // 3, sum(theme["fg"]) // 3
    mask = luminance.point(lambda v: max(0, min(255, round((v - lo) * 255 / (hi - lo)))))
    return mask.point(lambda v: 0 if v < NOISE_FLOOR else v)


def _runs(projection, merge_gap=0):
    runs, start, last = [], None, None
    for i, on in enumerate(projection):
        if on:
            if start is None:
                start = i
            elif merge_gap and i - last > merge_gap + 1:
                runs.append((start, last))
                start = i
            last = i
        elif start is not None and not merge_gap:
            runs.append((start, last))
            start = None
    if start is not None:
        runs.append((start, last))
    return runs


def _binary(mask):
    return mask.point(lambda v: 255 if v > INK else 0)


def stacked_parts():
    """(mark, net_gain, news, cap_height, baselines) cut out of the official stacked logo as ink-coverage masks.

    Each text mask is cropped with the same vertical extent relative to its baseline, so they align when placed side by side.
    """
    coverage = _coverage(os.path.join(BRAND, "net_gain_news_logo_stacked.png"))
    _, rows = _binary(coverage).getprojection()
    bands = _runs(rows, merge_gap=60)           # the mark's two bars are one band; each text line is a band
    assert len(bands) == 3, f"unexpected artwork layout: {bands}"

    def band_box(band):
        strip = _binary(coverage.crop((0, band[0], coverage.width, band[1] + 1)))
        left, _, right, _ = strip.getbbox()
        return left, right

    mark_left, mark_right = band_box(bands[0])
    mark = coverage.crop((mark_left, bands[0][0], mark_right + 1, bands[0][1] + 1))

    def text_line(band):
        left, right = band_box(band)
        strip = _binary(coverage.crop((left, band[0], right + 1, band[1] + 1)))
        columns, _ = strip.getprojection()
        first = _runs(columns)[0]                                  # the leading "N"
        n_rows = _binary(coverage.crop((left + first[0], band[0], left + first[1] + 1, band[1] + 1))).getprojection()[1]
        cap_top, baseline = _runs(n_rows)[0][0], _runs(n_rows)[0][1]
        return left, right, band[0], cap_top, baseline

    lines = []
    for band in bands[1:]:
        left, right, top, cap_top, baseline = text_line(band)
        lines.append((left, right, top + cap_top, top + baseline))
    cap = lines[0][3] - lines[0][2] + 1
    assert abs((lines[1][3] - lines[1][2] + 1) - cap) <= 2, "the two lines disagree on cap height"

    # same window relative to the baseline for both lines: room above the cap line for the "i" dot, a little below
    above, below = round(cap * 0.35), round(cap * 0.12)

    def cut(line):
        left, right, cap_top, baseline = line
        return coverage.crop((left, baseline - cap - above + 1, right + 1, baseline + below + 1))

    return mark, cut(lines[0]), cut(lines[1]), cap, above


def _tint(coverage, theme):
    layer = Image.new("RGB", coverage.size, theme["fg"])
    base = Image.new("RGB", coverage.size, theme["bg"])
    return Image.composite(layer, base, coverage)


def horizontal_lockup(theme_name="dark"):
    """Mark, "Net Gain", "News" on one line, as an ink-coverage mask (cap height = the official artwork's)."""
    mark, net_gain, news, cap, above = stacked_parts()
    gap_mark, gap_word = round(cap * MARK_GAP_CAPS), round(cap * WORD_GAP_CAPS)
    height = net_gain.height
    width = mark.width + gap_mark + net_gain.width + gap_word + news.width
    canvas = Image.new("L", (width, height), 0)
    cap_centre = above + cap // 2
    canvas.paste(mark, (0, cap_centre - mark.height // 2))
    x = mark.width + gap_mark
    canvas.paste(net_gain, (x, 0))
    canvas.paste(news, (x + net_gain.width + gap_word, 0))
    return canvas, cap, above


def wide_logo(theme_name="dark"):
    """The horizontal lockup, 60 px tall, on the theme's background, as wide as it needs (never over 600)."""
    lockup, cap, above = horizontal_lockup()
    scale = WIDE_CAP_HEIGHT / cap
    lockup = lockup.resize((round(lockup.width * scale), round(lockup.height * scale)), Image.LANCZOS)
    canvas = Image.new("L", (lockup.width + 2 * WIDE_PAD_X, WIDE_HEIGHT), 0)
    cap_centre = round((above + cap / 2) * scale)
    canvas.paste(lockup, (WIDE_PAD_X, WIDE_HEIGHT // 2 - cap_centre))
    assert canvas.width <= WIDE_MAX_WIDTH, "lockup too wide for a 60 px logo"
    return _tint(canvas, THEMES[theme_name])


def square_logo(theme_name="dark"):
    """The official stacked logo at 512 px (the artwork's own padding is kept)."""
    coverage = _coverage(os.path.join(BRAND, "net_gain_news_logo_stacked.png"))
    return _tint(coverage.resize((SQUARE_SIDE, SQUARE_SIDE), Image.LANCZOS), THEMES[theme_name])


def mark_logo(theme_name="dark"):
    """The official mark-only artwork at 512 px."""
    coverage = _coverage(os.path.join(BRAND, "net_gain_news_mark.png"))
    return _tint(coverage.resize((SQUARE_SIDE, SQUARE_SIDE), Image.LANCZOS), THEMES[theme_name])


def main():
    for theme in THEMES:
        for name, make in (("wide_60", wide_logo), ("square_512", square_logo), ("mark_512", mark_logo)):
            image = make(theme)
            path = os.path.join(TEMPLATES, f"publisher_logo_news_{name}_{theme}.png")
            image.save(path, optimize=True)
            print(path, image.size)


if __name__ == "__main__":
    main()
