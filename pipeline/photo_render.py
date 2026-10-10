"""
Draws the three finished graphics (16:9, 1200x630 website, 3000x3000 square) from one library photo: the episode's crop
recipe, the show's duotone, an optional caption plate, then the show's own frame (footer band and logo) on top - the
same compositing step every other image mode uses.

No network here: the photo and frames come in as arguments and PIL images come out.
"""

from PIL import Image

import cards
from image_compositing import _hex_to_rgb, apply_duotone, composite_frame, visible_window
from photo_library import crop_box

FORMATS = {"16x9": (1280, 720), "1200x630": (1200, 630), "square": (3000, 3000)}
MAX_SOURCE_SIDE = 4500          # larger photos are scaled down first (memory and time); crops stay sharp at output size
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _lighten(rgb, amount):
    return tuple(int(round(c + (255 - c) * amount)) for c in rgb)


def date_text(episode_date):
    return f"{MONTHS[episode_date.month - 1]} {episode_date.day}, {episode_date.year}"


def prepare_photo(photo, duotone=None):
    """The photo at working size, in the show's duotone (shadow_hex, highlight_hex) when one is set."""
    photo = photo.convert("RGB")
    if max(photo.size) > MAX_SOURCE_SIDE:
        photo.thumbnail((MAX_SOURCE_SIDE, MAX_SOURCE_SIDE), Image.LANCZOS)
    if duotone:
        photo = apply_duotone(photo, duotone[0], duotone[1])
    return photo


def draw_caption(canvas, window, topic, when, shadow_rgb, text_rgb, square):
    """
    A solid plate along the bottom of the photo window: story 1's topic word on the left (when there is one) and the
    date on the right. Raises cards.CardLayoutError - before drawing anything - if the topic word cannot be set
    legibly; the caller then draws the date alone.
    """
    from PIL import ImageDraw

    left, top, right, bottom = window
    plate_h = round((bottom - top) * (0.11 if square else 0.15))
    pad = round(plate_h * 0.34)
    plate = (left, bottom - plate_h, right, bottom)
    mid = (plate[1] + plate[3]) / 2

    date_font = cards.mono(max(12, round(plate_h * 0.26)), False)
    date_x = right - pad - cards.tlen(when, date_font, 0.02)

    topic_font = topic_base = None
    if topic:
        width = date_x - (left + pad) - pad
        size = cards.fit_wh(topic, width, plate_h * 0.62, smin=int(plate_h * 0.3), smax=int(plate_h * 0.9))
        topic_font = cards.cond(size)
        topic_base = cards.obase(topic_font, mid, plate)
        ink = topic_font.getbbox(cards._g(topic), anchor="ls")
        if topic_base + ink[3] > plate[3] - plate_h * 0.04:
            raise cards.CardLayoutError("caption does not fit its plate")

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay.paste(shadow_rgb + (238,), plate)
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB"))

    d = ImageDraw.Draw(canvas)
    cards.ttext(d, (date_x, mid + cards.cap(date_font) / 2), when, date_font, text_rgb, 0.02, anchor="ls")
    if topic_font:
        cards.ttext(d, (left + pad, topic_base), topic, topic_font, text_rgb, -0.01, anchor="ls")


def render_formats(photo, focal, variant, frames, duotone=None, caption=None):
    """
    photo:    PIL image (EXIF orientation already applied).
    focal:    (x, y) fractions of the photo that every crop keeps in frame.
    variant:  from photo_library.choose_variant.
    frames:   {"16x9": png bytes, "1200x630": png bytes, "square": png bytes}.
    duotone:  (shadow_hex, highlight_hex) or None for natural colour.
    caption:  None for no plate, else {"topic": str|None, "date": date} - drawn as topic + date, or date alone.
    Returns {"16x9": image, "1200x630": image, "square": image}.
    """
    working = prepare_photo(photo, duotone)
    width, height = working.size
    shadow = _hex_to_rgb(duotone[0]) if duotone else (30, 38, 32)
    highlight = _hex_to_rgb(duotone[1]) if duotone else (200, 200, 200)
    text_rgb = _lighten(highlight, 0.8)

    out = {}
    for spec, (out_w, out_h) in FORMATS.items():
        left, top, right, bottom = visible_window(frames[spec], out_w, out_h)
        win_w, win_h = right - left, bottom - top
        box = crop_box(width, height, focal, variant, win_w, win_h)
        region = working.resize((win_w, win_h), Image.LANCZOS, box=box)

        canvas = Image.new("RGB", (out_w, out_h), shadow)
        canvas.paste(region, (left, top))
        if caption:
            when = date_text(caption["date"])
            window = (left, top, right, bottom)
            try:
                draw_caption(canvas, window, caption.get("topic"), when, shadow, text_rgb, spec == "square")
            except cards.CardLayoutError:
                draw_caption(canvas, window, None, when, shadow, text_rgb, spec == "square")
        out[spec] = composite_frame(canvas, frames[spec])
    return out
