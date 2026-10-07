"""
Code-built episode cards (replaces AI-generated episode graphics for shows set to
image mode "cards").

Why this exists: YouTube auto-labels some uploads "Made with AI", and AI-generated
episode art was the leading suspect. These cards are drawn entirely in code from
the episode's own facts (headline, topic words, date, the Edtech Index snapshot),
in the brand's greens and fonts, so there is no generated imagery in the picture.

Nine templates are served round-robin per show (TEMPLATE_ORDER). The order keeps
similar treatments apart (headline cards, keyword cards, index cards, date/audio
cards), including across the wrap from the last template back to the first.

Each template draws in two geometries: "wide" (a virtual 1280x720 canvas, used for
the 16:9 YouTube art and, scaled, the 1200x630 website art) and "square" (3000x3000
podcast art). Content is centred between the top of the frame's visible window and
its footer band, so the space above and below is equal.

Hard rules baked in (each has a test):
  * the layout never lets text ink - descenders included - leave the block it sits
    in (CardLayoutError, so the caller can try the next template);
  * the large background day numeral stays inside the graphic for every possible
    date (numeral_fit sizes it for the widest two-digit day);
  * light green is never used as a fill - only dark-green tiles, with light green
    reserved for text, shapes and bars; no uppercase display text.

No network calls here: everything comes in as arguments and a PIL image comes out.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parent / "fonts"

# Brand palette (the site's two greens plus working tones derived for the cards).
GROUND = (34, 48, 39)
DARKT = (46, 68, 55)       # tile fill
MID = (61, 107, 74)        # brand dark green: declines, quiet bars
ACC = (133, 168, 112)      # brand light green: text, shapes, rises
DIM = (120, 150, 128)      # captions
LIGHT = (232, 239, 228)    # tickers in the movers card only
NUMERAL = (44, 66, 52)     # the giant backdrop day numeral

# Served in this order, round-robin (see module docstring).
TEMPLATE_ORDER = ["A", "B1", "D6", "C", "E", "D3", "D8", "F", "D5"]
INDEX_TEMPLATES = {"C", "F"}
KEYWORD_TEMPLATES = {"B1", "D3"}
HEADLINE_TEMPLATES = {"A", "E"}
WEEKDAY_TEMPLATES = {"D5", "D6", "D8"}

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]

WIDE_SIZE = (1280, 720)
SQUARE_SIZE = (3000, 3000)
# Used when a frame has no transparent window to measure.
DEFAULT_WIDE_WINDOW = (8, 584)
DEFAULT_SQUARE_WINDOW = (0, 2600)


class CardLayoutError(ValueError):
    """The text does not fit its template; callers should try the next template."""


@dataclass
class CardContent:
    episode_date: date
    headline: str = ""
    keywords: list = field(default_factory=list)
    # {"pct": float, "ytd": float|None, "moves": [{"t": ticker, "co": company, "mv": percent}, ...]}
    index: dict = None


# --- fonts and text ------------------------------------------------------------

@lru_cache(maxsize=None)
def archivo(size, wght=700, wdth=100):
    f = ImageFont.truetype(str(FONT_DIR / "Archivo[wdth,wght].ttf"), size)
    f.set_variation_by_axes([wght, wdth])
    return f


@lru_cache(maxsize=None)
def plex(size, wght=400):
    f = ImageFont.truetype(str(FONT_DIR / "IBMPlexSans[wdth,wght].ttf"), size)
    f.set_variation_by_axes([wght, 100])
    return f


@lru_cache(maxsize=None)
def mono(size, medium=True):
    return ImageFont.truetype(str(FONT_DIR / f"IBMPlexMono-{'Medium' if medium else 'Regular'}.ttf"), size)


def cond(size):
    """Archivo Bold, slightly condensed: the display face for blocks."""
    return archivo(size, 700, 78)


def _adv(font, a, b=""):
    return font.getlength(a + b) - font.getlength(b) if b else font.getlength(a)


def tlen(text, font, tr=0.0):
    """Width of text with letter-spacing tr (in em); Pillow has none, so it is drawn glyph by glyph."""
    size = font.size
    width = 0
    for i, ch in enumerate(text):
        width += _adv(font, ch, text[i + 1] if i + 1 < len(text) else "") + tr * size
    return width - tr * size if text else 0


def ttext(d, xy, text, font, fill, tr=0.0, anchor="la"):
    x, y = xy
    size = font.size
    for i, ch in enumerate(text):
        d.text((x, y), ch, font=font, fill=fill, anchor=anchor)
        x += _adv(font, ch, text[i + 1] if i + 1 < len(text) else "") + tr * size


def wrap(text, font, max_width, tr=0.0):
    lines, cur = [], ""
    for word in text.split():
        candidate = (cur + " " + word).strip()
        if tlen(candidate, font, tr) <= max_width:
            cur = candidate
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def cap(font):
    b = font.getbbox("H")
    return b[3] - b[1]


def desc(font):
    return font.getbbox("gpqyj", anchor="ls")[3]


def sgn(value, fmt):
    return f"{value:+{fmt}}".replace("-", "−")


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def tile_color(move):
    """Heatmap tile: dark brand green for declines through light brand green for gains, clamped at +-3%."""
    t = max(-3, min(3, move)) / 3
    return _lerp(MID, ACC, t) if t >= 0 else _lerp(MID, DARKT, -t)


# --- the canvas -------------------------------------------------------------------

class Canvas:
    """A transparent layer to draw on; finish() centres its content in the frame window."""

    def __init__(self, kind, window):
        self.kind = kind
        self.square = kind == "square"
        self.W, self.H = SQUARE_SIZE if self.square else WIDE_SIZE
        self.top, self.bottom = window
        self.layer = Image.new("RGBA", (self.W, self.H), GROUND + (0,))
        self.d = ImageDraw.Draw(self.layer)
        self.bad = []
        self.numeral = None

    def geo(self):
        """Box, gap and corner radius for the block designs: equal padding above and below."""
        if self.square:
            return dict(box=(200, self.top + 180, 2800, self.bottom - 180), gap=40, r=40)
        return dict(box=(82, self.top + 82, 1198, self.bottom - 82), gap=14, r=14)

    def put(self, block, x, base, text, font, fill, tr=-0.01, what=""):
        """Draw text and record any ink (descenders included) that would leave its block."""
        l, t, r, b = font.getbbox(text, anchor="ls")
        m = min(block[2] - block[0], block[3] - block[1]) * 0.025
        ink = (x + l, base + t, x + r, base + b)
        if ink[0] < block[0] + m or ink[2] > block[2] - m or ink[1] < block[1] + m or ink[3] > block[3] - m:
            self.bad.append((what or text, [round(v) for v in ink], [round(v) for v in block]))
        ttext(self.d, (x, base), text, font, fill, tr, anchor="ls")

    def finish(self):
        """Centre the content between the window top and the footer band, add the numeral, return an RGB image."""
        bbox = self.layer.getchannel("A").getbbox()
        if not bbox:
            raise CardLayoutError("the card has no content")
        if self.bad:
            raise CardLayoutError("text does not fit its block: " + "; ".join(f"{w} ink {i} outside {b}" for w, i, b in self.bad))
        dy = int(round((self.top + self.bottom - bbox[1] - bbox[3]) / 2))
        base = Image.new("RGBA", (self.W, self.H), GROUND + (255,))
        if self.numeral:
            text = self.numeral
            if self.square:
                draw_numeral(ImageDraw.Draw(base), text, 2800, (self.top + self.bottom) / 2, 2300, 1500)
            else:
                draw_numeral(ImageDraw.Draw(base), text, 1198, (self.top + self.bottom) / 2, 640, 400)
        base.alpha_composite(self.layer, (0, dy))
        return base.convert("RGB")


# --- the giant background day numeral (template E) -------------------------------

@lru_cache(maxsize=None)
def numeral_fit(wmax, hmax):
    """Largest size at which the WIDEST two-digit day (01-31) fits wmax and the digits fit hmax."""
    best = None
    for s in range(100, 4000, 10):
        f = archivo(s)
        b = f.getbbox("0123456789", anchor="ls")
        if max(tlen(f"{n:02d}", f, -0.03) for n in range(1, 32)) <= wmax and (b[3] - b[1]) <= hmax:
            best = s
    return best


def draw_numeral(d, text, right, cy, wmax, hmax):
    s = numeral_fit(wmax, hmax)
    f = archivo(s)
    b = f.getbbox("0123456789", anchor="ls")
    height = b[3] - b[1]
    width = tlen(text, f, -0.03)
    ttext(d, (right - width, cy + height / 2 - b[3]), text, f, NUMERAL, -0.03, anchor="ls")
    return s


# --- small drawing helpers -------------------------------------------------------

def blk(c, box, fill):
    c.d.rounded_rectangle(box, radius=c.geo()["r"], fill=fill)


def ctext(d, x, cy, text, font, fill, tr=0.0):
    """Cap-height-centred on cy (used for numerals and single letters, which have no descenders)."""
    ttext(d, (x, cy + cap(font) / 2), text, font, fill, tr, anchor="ls")


def obase(font, cy, block):
    """Optical centring: cap-top..baseline centred on cy, descender hanging; only pushed up if it would leave the block."""
    b = cy + cap(font) / 2
    return min(b, block[3] - (block[3] - block[1]) * 0.04 - desc(font))


def fit_wh(text, width, max_height, smin=30, smax=900):
    """Largest condensed size where the text fits the width and cap+descender fit max_height (and is not below smin)."""
    candidates = [s for s in range(smin, smax) if tlen(text, cond(s), -0.01) <= width and cap(cond(s)) + desc(cond(s)) <= max_height]
    if not candidates:
        raise CardLayoutError(f"{text!r} does not fit in {width:.0f}x{max_height:.0f}")
    return max(candidates)


def fit_lines(text, size_to_font, width, max_lines, smax, smin, tr=-0.02, step=2):
    for size in range(smax, smin - 1, -step):
        lines = wrap(text, size_to_font(size), width, tr)
        if len(lines) <= max_lines:
            return size, lines
    raise CardLayoutError(f"{text!r} does not fit in {max_lines} lines at {smin}px or larger")


def label(d, x, ytop, text, size, col=DIM):
    f = mono(max(12, int(size)))
    ttext(d, (x, ytop + cap(f)), text, f, col, 0.02, anchor="ls")


def kicker(d, xy, text, size):
    ttext(d, xy, text.upper(), mono(size), ACC, 0.12)


def arrow(d, x, y, w, h, pointing_up, col):
    d.polygon([(x, y + h), (x + w, y + h), (x + w / 2, y)] if pointing_up else [(x, y), (x + w, y), (x + w / 2, y + h)], fill=col)


def headline_move(d, pct, x_num, base_y, num_size, today_size, color, gap):
    """'+0.23% today' on one baseline: the number big, 'today' attached right after it, smaller."""
    ft = archivo(num_size)
    txt = sgn(pct, ".2f") + "%"
    ttext(d, (x_num, base_y), txt, ft, color, -0.03, anchor="ls")
    d.text((x_num + tlen(txt, ft, -0.03) + gap, base_y), "today", font=plex(today_size, 600), fill=color, anchor="ls")


def move_color(pct):
    return ACC if pct >= 0 else MID


def bars_row(d, x0, y0, x1, y1, wide=True):
    """Audio-waveform bars, the same recipe as template A's: thin pills, fixed pitch, MID with every third ACC."""
    random.seed(7)
    hm = y1 - y0
    n = max(8, int((x1 - x0) / ((1280 if wide else 3000) * 0.0135)))
    pitch = (x1 - x0) / n
    bw = pitch * 0.58
    mid = (y0 + y1) / 2
    for i in range(n):
        h = hm * (0.23 + 0.77 * abs(math.sin(i * 0.55)) * random.uniform(0.5, 1.0))
        cx = x0 + i * pitch + (pitch - bw) / 2
        d.rounded_rectangle((cx, mid - h / 2, cx + bw, mid + h / 2), radius=bw / 2, fill=MID if i % 3 else ACC)


def _date_bits(content):
    dt = content.episode_date
    return dict(
        weekday=WEEKDAYS[dt.weekday()], wd3=WEEKDAYS[dt.weekday()][:3],
        month=MONTHS[dt.month - 1], mon3=MONTHS[dt.month - 1][:3], day=dt.day, year=str(dt.year), wd=dt.weekday(),
    )


# --- templates ---------------------------------------------------------------------

def tpl_A(c, content):
    """Headline plus an audio waveform; the date line sits at the foot."""
    b = _date_bits(content)
    d = c.d
    if c.square:
        pad, cw = 200, 2600
        kicker(d, (pad, 175), f"{b['wd3']} · {b['mon3']} {b['day']}, {b['year']}", 96)
        size, lines = fit_lines(content.headline, archivo, cw, 5, 300, 200, step=4)
        y = 425
        f = archivo(size)
        for ln in lines:
            ttext(d, (pad, y), ln, f, ACC, -0.02)
            y += int(size * 1.06)
        random.seed(7)
        n = 62
        bw = cw / n
        for i in range(n):
            h = int(60 + 150 * abs(math.sin(i * 0.5)) * random.uniform(0.5, 1.0))
            x = pad + i * bw
            d.rounded_rectangle((x, 2345 - h // 2, x + bw * 0.52, 2345 + h // 2), radius=14, fill=MID if i % 3 else ACC)
    else:
        size, lines = fit_lines(content.headline, archivo, 720, 5, 72, 48)
        y = 110
        f = archivo(size)
        pitch = round(size * 84 / 72)
        for ln in lines:
            ttext(d, (70, y), ln, f, ACC, -0.02)
            y += pitch
        kicker(d, (70, y + 44), f"{b['weekday']} · {b['month']} {b['day']}, {b['year']}", 22)
        random.seed(7)
        for i in range(22):
            h = int(60 + 200 * abs(math.sin(i * 0.55)) * random.uniform(0.5, 1.0))
            cx = 850 + i * 17
            d.rounded_rectangle((cx, 290 - h // 2, cx + 10, 290 + h // 2), radius=5, fill=MID if i % 3 else ACC)


def tpl_E(c, content):
    """Giant faint day numeral behind a headline."""
    b = _date_bits(content)
    d = c.d
    c.numeral = f"{b['day']:02d}"
    if c.square:
        kicker(d, (200, 175), f"{b['wd3']} · {b['mon3']} {b['year']}", 96)
        size, lines = fit_lines(content.headline, archivo, 2400, 5, 360, 200, step=4)
        y = 585
        f = archivo(size)
        for ln in lines:
            ttext(d, (200, y), ln, f, ACC, -0.02)
            y += int(size * 1.06)
    else:
        kicker(d, (70, 124), f"{b['weekday']} · {b['month']} {b['year']}", 22)
        size, lines = fit_lines(content.headline, archivo, 760, 5, 70, 48)
        y = 216
        f = archivo(size)
        pitch = round(size * 82 / 70)
        for ln in lines:
            ttext(d, (70, y), ln, f, ACC, -0.02)
            y += pitch


def _heatmap(c, moves):
    d = c.d
    n = len(moves)
    if c.square:
        cols, gap = 10, 18
        tw = (2600 - gap * (cols - 1)) / cols
        rows = math.ceil(n / cols)
        th = min(240, 1090 / rows - gap)
        y0 = 1155
        for k, m in enumerate(moves):
            r, col = divmod(k, cols)
            x = 200 + col * (tw + gap)
            y = y0 + r * (th + gap)
            d.rounded_rectangle((x, y, x + tw, y + th), radius=22, fill=tile_color(m["mv"]))
        ky = y0 + rows * (th + gap) + 60
        kw = 1150
        for i in range(kw):
            d.line((200 + i, ky, 200 + i, ky + 54), fill=tile_color(-3 + 6 * i / kw))
        fm = mono(64, False)
        d.text((200, ky + 72), "DOWN 3%+", font=fm, fill=DIM)
        d.text((200 + kw / 2 - fm.getlength("FLAT") / 2, ky + 72), "FLAT", font=fm, fill=DIM)
        d.text((200 + kw - fm.getlength("UP 3%+"), ky + 72), "UP 3%+", font=fm, fill=DIM)
        d.multiline_text((200 + kw + 90, ky - 6), f"Each tile is one of the {n}\ncompanies in the index,\nshowing today’s move",
                         font=plex(60), fill=DIM, spacing=10)
    else:
        cols, tw, gap = 25, 42, 4
        rows = math.ceil(n / cols)
        rows_h = 50 if rows <= 2 else 34
        y0 = 322
        for k, m in enumerate(moves):
            r, col = divmod(k, cols)
            x = 70 + col * (tw + gap)
            y = y0 + r * (rows_h + 8)
            d.rounded_rectangle((x, y, x + tw, y + rows_h), radius=6, fill=tile_color(m["mv"]))
        ky = y0 + rows * (rows_h + 8) + 32
        w = 520
        for i in range(w):
            d.line((70 + i, ky, 70 + i, ky + 18), fill=tile_color(-3 + 6 * i / w))
        f = mono(18, False)
        d.text((70, ky + 26), "DOWN 3%+", font=f, fill=DIM)
        d.text((70 + w // 2 - f.getlength("FLAT") / 2, ky + 26), "FLAT", font=f, fill=DIM)
        d.text((70 + w - f.getlength("UP 3%+"), ky + 26), "UP 3%+", font=f, fill=DIM)
        d.multiline_text((70 + w + 34, ky - 4), f"Each tile is one of the {n} companies\nin the index, showing today’s move",
                         font=plex(21), fill=DIM, spacing=6)


def _move_row_square(d, pct, x, base, max_width, color):
    txt = sgn(pct, ".2f") + "%"
    size = 200
    for sz in range(480, 200, -6):
        if tlen(txt, archivo(sz), -0.03) + 34 + plex(int(sz * 0.38), 600).getlength("today") <= max_width:
            size = sz
            break
    headline_move(d, pct, x, base, size, int(size * 0.38), color, 34)


def tpl_C(c, content):
    """Arrow plus the day's index move, with a heatmap of every constituent."""
    ix = content.index
    pct = ix["pct"]
    col = move_color(pct)
    d = c.d
    if c.square:
        arrow(d, 200, 275, 560, 490, pct >= 0, col)
        _move_row_square(d, pct, 840, 765, 1960, col)
        f1 = plex(96, 600)
        d.text((200, 905), "Edtech Index ", font=f1, fill=DIM)
        if ix.get("ytd") is not None:
            d.text((200 + f1.getlength("Edtech Index "), 905), sgn(ix["ytd"], ".1f") + "% so far this year", font=plex(96), fill=DIM)
    else:
        arrow(d, 70, 100, 160, 138, pct >= 0, col)
        headline_move(d, pct, 262, 236, 150, 58, col, 22)
        d.text((266, 268), "Edtech Index ", font=plex(28, 600), fill=DIM)
        if ix.get("ytd") is not None:
            d.text((266 + plex(28, 600).getlength("Edtech Index "), 268), sgn(ix["ytd"], ".1f") + "% so far this year", font=plex(28), fill=DIM)
    _heatmap(c, ix["moves"])


def tpl_F(c, content):
    """Arrow plus the day's index move, then three gainers and three decliners."""
    ix = content.index
    pct = ix["pct"]
    col = move_color(pct)
    d = c.d
    moves = sorted(ix["moves"], key=lambda m: m["mv"])
    losers, gainers = moves[:3], moves[-3:][::-1]
    if c.square:
        arrow(d, 200, 275, 500, 440, pct >= 0, col)
        _move_row_square(d, pct, 780, 725, 2020, col)
        d.text((790, 805), "Edtech Index", font=plex(130, 600), fill=col)
        for x, rows, rc, up in [(200, gainers, ACC, True), (1540, losers, MID, False)]:
            arrow(d, x + 4, 1335, 110, 92, up, rc)
            for i, r in enumerate(rows):
                yy = 1525 + i * 400
                d.text((x, yy), r["t"], font=mono(150), fill=LIGHT)
                ttext(d, (x + 590, yy - 14), sgn(r["mv"], ".1f") + "%", archivo(160), rc, -0.01)
    else:
        arrow(d, 70, 100, 140, 122, pct >= 0, col)
        headline_move(d, pct, 244, 222, 140, 52, col, 22)
        d.text((250, 248), "Edtech Index", font=plex(32, 600), fill=col)
        for x, rows, rc, up in [(70, gainers, ACC, True), (690, losers, MID, False)]:
            arrow(d, x + 2, 336, 22, 18, up, rc)
            for i, r in enumerate(rows):
                yy = 376 + i * 50
                d.text((x, yy + 2), r["t"], font=mono(36), fill=LIGHT)
                ttext(d, (x + 240, yy - 2), sgn(r["mv"], ".1f") + "%", archivo(38), rc, -0.01)


def tpl_B1(c, content):
    """Three topic words, one per story, each beside its number."""
    words = content.keywords[:3]
    g = c.geo()
    x0, y0, x1, y1 = g["box"]
    gap = g["gap"]
    h = (y1 - y0 - 2 * gap) / 3
    numw = h * 0.56
    pad = h * 0.14
    avail = x1 - (x0 + numw + gap) - 2 * pad
    size = min(int(h * 0.62), min(fit_wh(w, avail, h * 0.84, smin=int(h * 0.4)) for w in words))
    for i, word in enumerate(words):
        y = y0 + i * (h + gap)
        nb = (x0, y, x0 + numw, y + h)
        blk(c, nb, DARKT)
        f, fn = cond(size), archivo(size)
        base = y + h / 2 + (cap(f) - desc(f)) / 2
        dg = str(i + 1)
        c.put(nb, x0 + (numw - tlen(dg, fn, -0.03)) / 2, base, dg, fn, ACC, -0.03, what=f"numeral {dg}")
        bx = x0 + numw + gap
        bb = (bx, y, x1, y + h)
        blk(c, bb, DARKT)
        c.put(bb, bx + pad, base, word, f, ACC, what=word)


def tpl_D3(c, content):
    """The lead story's word big, the other two smaller beneath."""
    words = content.keywords[:3]
    g = c.geo()
    x0, y0, x1, y1 = g["box"]
    gap = g["gap"]
    height = y1 - y0
    top_h = (height - gap) * 0.58
    bot_h = height - gap - top_h
    pad = top_h * 0.08
    tb = (x0, y0, x1, y0 + top_h)
    blk(c, tb, DARKT)
    label(c.d, x0 + pad, y0 + pad, "01", top_h * 0.06, ACC)
    size = fit_wh(words[0], (x1 - x0) - 2 * pad, top_h * 0.52, smin=int(top_h * 0.2))
    f = cond(size)
    c.put(tb, x0 + pad, y0 + top_h - pad - desc(f), words[0], f, ACC, what=words[0])
    bw = (x1 - x0 - gap) / 2
    padb = bot_h * 0.08
    y = y0 + top_h + gap

    def small_fit(word):
        parts = word.split(" ")
        ok = [s for s in range(int(bot_h * 0.16), 900)
              if all(tlen(p, cond(s), -0.01) <= bw - 2 * padb for p in parts)
              and (len(parts) - 1) * s * 0.95 + cap(cond(s)) + desc(cond(s)) <= bot_h * 0.66]
        if not ok:
            raise CardLayoutError(f"{word!r} does not fit its block")
        return max(ok)

    sz = min(small_fit(w) for w in words[1:])
    f = cond(sz)
    for i in range(2):
        bx = x0 + i * (bw + gap)
        bb = (bx, y, bx + bw, y1)
        blk(c, bb, DARKT)
        label(c.d, bx + padb, y + padb, f"0{i + 2}", bot_h * 0.07, ACC)
        parts = words[i + 1].split(" ")
        yy = y1 - padb - desc(f) - (len(parts) - 1) * sz * 0.95
        for p in parts:
            c.put(bb, bx + padb, yy, p, f, ACC, what=p)
            yy += sz * 0.95


def tpl_D5(c, content):
    """The weekday spelled out, over an M-T-W-T-F strip with today outlined."""
    b = _date_bits(content)
    g = c.geo()
    x0, y0, x1, y1 = g["box"]
    gap, r = g["gap"], g["r"]
    height = y1 - y0
    top_h = height * 0.5
    tb = (x0, y0, x1, y0 + top_h)
    blk(c, tb, DARKT)
    pad = top_h * 0.08
    label(c.d, x0 + pad, y0 + pad, f"{b['mon3']} {b['day']}, {b['year']}", top_h * 0.08)
    size = fit_wh(b["weekday"], (x1 - x0) - 2 * pad, top_h * 0.62)
    f = cond(size)
    c.put(tb, x0 + pad, y0 + top_h - pad - desc(f), b["weekday"], f, ACC, what=b["weekday"])
    yy = y0 + top_h + gap
    bh = y1 - yy
    bw = (x1 - x0 - 4 * gap) / 5
    f = cond(int(min(bh * 0.62, bw * 1.0)))
    for i, letter in enumerate("MTWTF"):
        bx = x0 + i * (bw + gap)
        blk(c, (bx, yy, bx + bw, y1), DARKT)
        if i == b["wd"]:
            c.d.rounded_rectangle((bx, yy, bx + bw, y1), radius=r, outline=ACC, width=max(4, int(height * 0.009)))
            col = ACC
        else:
            col = DIM if i < b["wd"] else MID
        ctext(c.d, bx + (bw - tlen(letter, f, -0.01)) / 2, yy + bh / 2, letter, f, col, -0.01)


def tpl_D6(c, content):
    """A play button beside Today / weekday / date, over an audio waveform."""
    b = _date_bits(content)
    g = c.geo()
    x0, y0, x1, y1 = g["box"]
    gap = g["gap"]
    height, width = y1 - y0, x1 - x0
    top_h = (height - gap) * 0.64
    pw = (width - gap) / 2
    blk(c, (x0, y0, x0 + pw, y0 + top_h), DARKT)
    s = min(pw, top_h) * 0.46
    cx, cy = x0 + pw / 2, y0 + top_h / 2
    c.d.polygon([(cx - s * 0.32, cy - s * 0.5), (cx - s * 0.32, cy + s * 0.5), (cx + s * 0.52, cy)], fill=ACC)
    rx = x0 + pw + gap
    rw = x1 - rx
    rh = top_h - 2 * gap
    hs = [rh * 0.40, rh * 0.30, rh * 0.30]
    y = y0
    for i, t in enumerate(["Today", b["wd3"], f"{b['mon3']} {b['day']}"]):
        bb = (rx, y, x1, y + hs[i])
        blk(c, bb, DARKT)
        pad = hs[i] * 0.12
        size = fit_wh(t, rw - 2 * pad - (hs[i] * 0.9 if i == 2 else 0), hs[i] * 0.62)
        f = cond(size)
        c.put(bb, rx + pad, obase(f, y + hs[i] / 2, bb), t, f, ACC, what=t)
        if i == 2:
            fm = mono(max(12, int(hs[i] * 0.15)))
            ttext(c.d, (x1 - pad - tlen(b["year"], fm, 0.02), y + pad + cap(fm)), b["year"], fm, DIM, 0.02, anchor="ls")
        y += hs[i] + gap
    by = y0 + top_h + gap
    blk(c, (x0, by, x1, y1), DARKT)
    pad = (y1 - by) * 0.12
    bars_row(c.d, x0 + pad, by + pad, x1 - pad, y1 - pad, wide=not c.square)


def tpl_D8(c, content):
    """A giant Today, a waveform, and a podcast-style scrubber across the week."""
    b = _date_bits(content)
    g = c.geo()
    x0, y0, x1, y1 = g["box"]
    gap = g["gap"]
    height, width = y1 - y0, x1 - x0
    avail = height - 2 * gap
    t_h, m_h = avail * 0.40, avail * 0.22
    b_h = avail - t_h - m_h
    tb = (x0, y0, x1, y0 + t_h)
    blk(c, tb, DARKT)
    size = fit_wh("Today", width - 2 * t_h * 0.07, t_h * 0.66)
    f = cond(size)
    c.put(tb, x0 + t_h * 0.07, obase(f, y0 + t_h / 2, tb), "Today", f, ACC, what="Today")
    my = y0 + t_h + gap
    blk(c, (x0, my, x1, my + m_h), DARKT)
    p = m_h * 0.14
    bars_row(c.d, x0 + p, my + p, x1 - p, my + m_h - p, wide=not c.square)
    by = my + m_h + gap
    blk(c, (x0, by, x1, y1), DARKT)
    p = b_h * 0.1
    label(c.d, x0 + p, by + p, f"{b['weekday']} · {b['mon3']} {b['day']}, {b['year']}", b_h * 0.1)
    tx0, tx1 = x0 + p + b_h * 0.1, x1 - p - b_h * 0.1
    ty = by + b_h * 0.56
    th = max(6, b_h * 0.07)
    slot = (tx1 - tx0) / 5
    px = tx0 + slot * (b["wd"] + 0.5)
    c.d.rounded_rectangle((tx0, ty - th / 2, tx1, ty + th / 2), radius=th / 2, fill=MID)
    c.d.rounded_rectangle((tx0, ty - th / 2, px, ty + th / 2), radius=th / 2, fill=ACC)
    rr = b_h * 0.12
    c.d.ellipse((px - rr, ty - rr, px + rr, ty + rr), fill=ACC)
    f = cond(int(b_h * 0.2))
    for i, letter in enumerate("MTWTF"):
        cxl = tx0 + slot * (i + 0.5)
        ctext(c.d, cxl - tlen(letter, f, -0.01) / 2, by + b_h * 0.86, letter, f, ACC if i <= b["wd"] else MID, -0.01)


TEMPLATES = {
    "A": tpl_A, "B1": tpl_B1, "C": tpl_C, "D3": tpl_D3, "D5": tpl_D5,
    "D6": tpl_D6, "D8": tpl_D8, "E": tpl_E, "F": tpl_F,
}
assert set(TEMPLATES) == set(TEMPLATE_ORDER)


# --- rotation ------------------------------------------------------------------------

def template_available(template, content):
    """Whether this episode has what the template needs (the rest of the rotation covers for it)."""
    if template in INDEX_TEMPLATES:
        ix = content.index or {}
        return ix.get("pct") is not None and len(ix.get("moves") or []) >= 6
    if template in KEYWORD_TEMPLATES:
        return len([k for k in content.keywords if k]) >= 3
    if template in HEADLINE_TEMPLATES:
        return bool((content.headline or "").strip())
    if template in WEEKDAY_TEMPLATES:
        return content.episode_date.weekday() <= 4
    return True


def candidate_templates(previous, content):
    """The templates to try, in rotation order starting just after `previous` (first template if none/unknown)."""
    start = (TEMPLATE_ORDER.index(previous) + 1) % len(TEMPLATE_ORDER) if previous in TEMPLATE_ORDER else 0
    order = TEMPLATE_ORDER[start:] + TEMPLATE_ORDER[:start]
    return [t for t in order if template_available(t, content)]


# --- rendering -------------------------------------------------------------------------

def render_card(template, content, kind, window):
    """One card as a full-canvas RGB image (1280x720 for 'wide', 3000x3000 for 'square')."""
    canvas = Canvas(kind, window)
    TEMPLATES[template](canvas, content)
    return canvas.finish()


def render_formats(template, content, frames):
    """
    All three finished formats for one template, as PIL images ready to encode.
    `frames` maps "16x9", "1200x630" and "square" to the show's frame PNG bytes; each frame's own
    transparent window decides where the content is centred (so a different footer height just works).
    The 1200x630 website art is the wide card scaled to fit that frame's window.
    """
    from image_compositing import composite_frame, visible_window

    out = {}
    l16, t16, r16, b16 = visible_window(frames["16x9"], *WIDE_SIZE)
    wide = render_card(template, content, "wide", (t16, b16))
    out["16x9"] = composite_frame(wide, frames["16x9"])

    l12, t12, r12, b12 = visible_window(frames["1200x630"], 1200, 630)
    scale = (b12 - t12) / (b16 - t16)
    art = wide.resize((round(WIDE_SIZE[0] * scale), round(WIDE_SIZE[1] * scale)), Image.LANCZOS)
    canvas = Image.new("RGB", (1200, 630), GROUND)
    canvas.paste(art, ((1200 - art.width) // 2, round(t12 - t16 * scale)))
    out["1200x630"] = composite_frame(canvas, frames["1200x630"])

    ls, ts, rs, bs = visible_window(frames["square"], *SQUARE_SIZE)
    out["square"] = composite_frame(render_card(template, content, "square", (ts, bs)), frames["square"])
    return out
