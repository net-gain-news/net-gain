"""
The slim "latest newscast" line for the founder's email signature.

A transparent PNG (drawn at 3x so it is sharp on retina and phone screens) holding: the site's red LATEST flash, a
small caption ("NEWSCAST - OCT 16, 2026 - 5:06"), a LISTEN cue, and the headline, wrapped to at most two lines. It is
340 display pixels wide so it fits a phone screen at its real size (a wider image is shrunk by mail apps, which is
what made the headline unreadably small on an iPhone, 2026-10-20). It is drawn in two colourways, one
for light mail canvases and one for dark, because the text is baked into the image; the signature swaps between them
with a dark-mode style rule. The pipeline renders both after every website publish and the plugin stores them at
fixed URLs, so a signature that points at them always shows the current newscast.

Colours are the corporate palette from the live site (cream / warm greys, plus the one red accent of the site's own
"LATEST" badge). Sizes below are in display pixels; everything is multiplied by SCALE when drawn.
"""

import base64
import io
import logging
from datetime import date as _date

from PIL import Image, ImageDraw

from cards import archivo, mono

logger = logging.getLogger("net_gain.signature_strip")

SCALE = 3
WIDTH, HEIGHT = 340, 54      # display pixels; the signature shows the image at exactly this size

RED = (0xD0, 0x20, 0x2C)
WHITE = (255, 255, 255)

THEMES = {
    "light": {"ink": (0x12, 0x11, 0x0E), "muted": (0x6C, 0x6A, 0x64), "link": (0x4A, 0x47, 0x3F)},
    "dark": {"ink": (0xED, 0xE9, 0xE2), "muted": (0xA2, 0x9F, 0x98), "link": (0xC8, 0xC4, 0xBC)},
}


def date_label(episode_date):
    """'2026-10-16' -> 'OCT 16, 2026'."""
    d = _date.fromisoformat(str(episode_date)[:10])
    return f"{d:%b} {d.day}, {d.year}".upper()


def length_label(seconds):
    """Seconds -> '5:06' / '1:02:03'; '' when unknown."""
    seconds = int(seconds or 0)
    if seconds <= 0:
        return ""
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def caption(episode_date, seconds):
    parts = ["NEWSCAST", date_label(episode_date)]
    length = length_label(seconds)
    if length:
        parts.append(length)
    return " · ".join(parts)


def _tracked_width(font, text, tracking):
    return sum(font.getlength(ch) + tracking for ch in text) - (tracking if text else 0)


def _draw_tracked(canvas, x, baseline, text, font, tracking, color):
    """Letter-spaced text, drawn through an alpha mask so the PNG keeps clean transparent edges."""
    mask = Image.new("L", canvas.size, 0)
    d = ImageDraw.Draw(mask)
    cx = x
    for ch in text:
        d.text((cx, baseline), ch, font=font, fill=255, anchor="ls")
        cx += font.getlength(ch) + tracking
    canvas.paste(color + (255,), (0, 0), mask)
    return cx - tracking


def _wrap_lines(words, font, max_width):
    """Greedy word wrap; returns the list of lines (a single over-long word stays on its own line)."""
    lines, line = [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if line and font.getlength(trial) > max_width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def _balance(words, font, lines):
    """A headline that wraps to two lines is split where the two come out most even, so no single word is stranded."""
    if len(lines) != 2 or len(words) < 3:
        return lines
    best = min(range(1, len(words)),
               key=lambda i: max(font.getlength(" ".join(words[:i])), font.getlength(" ".join(words[i:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def _fit_headline(text, max_width, max_lines=2):
    """
    Archivo Bold at 13 display px on one line if it fits, otherwise wrapped to two; shrunk to 11.5 before giving up,
    and only then ellipsised on the last line. Returns (lines, font).
    """
    words = text.split()
    for size in (13, 12.5, 12, 11.5):
        font = archivo(round(size * SCALE), 700, 100)
        lines = _balance(words, font, _wrap_lines(words, font, max_width))
        if len(lines) <= max_lines and all(font.getlength(l) <= max_width for l in lines):
            return lines, font
    font = archivo(round(11.5 * SCALE), 700, 100)
    lines = _wrap_lines(words, font, max_width)[:max_lines]
    last = lines[-1] if lines else ""
    while last and font.getlength(last + "…") > max_width:
        last = last[:-1].rstrip()
    if lines:
        lines[-1] = last + "…"
    return lines, font


def row1_layout():
    """(right edge of the longest caption, left edge of the LISTEN cue), in display pixels; the first must stay left of the second."""
    s = SCALE
    flash_font = mono(round(9 * s), medium=True)
    flash_w = _tracked_width(flash_font, "LATEST", 0.12 * 9 * s) + 12 * s
    cap_font = mono(round(9.5 * s), medium=False)
    longest = _tracked_width(cap_font, "NEWSCAST · SEP 30, 2026 · 1:02:03", 0.1 * 9.5 * s)
    listen_font = mono(round(9.5 * s), medium=False)
    listen_w = _tracked_width(listen_font, "LISTEN", 0.12 * 9.5 * s)
    cue_left = WIDTH * s - listen_w - 5 * s - 6 * s
    return (flash_w + 8 * s + longest) / s, cue_left / s


def render_strip(title, episode_date, seconds, theme):
    """PNG bytes (RGBA, WIDTH*SCALE x HEIGHT*SCALE) for one colourway: theme 'light' or 'dark'."""
    colors = THEMES[theme]
    s = SCALE
    canvas = Image.new("RGBA", (WIDTH * s, HEIGHT * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Row 1: the red flash, the caption, and the LISTEN cue on the right.
    flash_font = mono(round(9 * s), medium=True)
    flash_text, flash_track = "LATEST", 0.12 * 9 * s
    pad_x, pad_y = 6 * s, 2 * s
    flash_w = _tracked_width(flash_font, flash_text, flash_track) + 2 * pad_x
    flash_h = 15 * s
    draw.rectangle([0, 0, flash_w - 1, flash_h - 1], fill=RED + (255,))
    baseline1 = round(10.9 * s)
    _draw_tracked(canvas, pad_x, baseline1, flash_text, flash_font, flash_track, WHITE)

    cap_font = mono(round(9.5 * s), medium=False)
    _draw_tracked(canvas, flash_w + 8 * s, baseline1, caption(episode_date, seconds), cap_font, 0.1 * 9.5 * s, colors["muted"])

    listen_font = mono(round(9.5 * s), medium=False)
    listen_track = 0.12 * 9.5 * s
    listen_w = _tracked_width(listen_font, "LISTEN", listen_track)
    tri_w, tri_h, gap = 6 * s, 7 * s, 5 * s
    right = WIDTH * s
    lx = right - listen_w
    _draw_tracked(canvas, lx, baseline1, "LISTEN", listen_font, listen_track, colors["link"])
    ty = baseline1 - 0.35 * 9.5 * s            # triangle centred on the capital letters of the caption text
    tx = lx - gap - tri_w
    draw.polygon([(tx, ty - tri_h / 2), (tx, ty + tri_h / 2), (tx + tri_w, ty)], fill=colors["link"] + (255,))
    underline_y = baseline1 + round(2.2 * s)
    draw.rectangle([tx, underline_y, right - 1, underline_y + max(1, round(0.8 * s)) - 1], fill=colors["link"] + (255,))

    # Row 2: the headline, one or two lines.
    lines, font = _fit_headline((title or "").replace("‑", "-").strip(), WIDTH * s)
    mask = Image.new("L", canvas.size, 0)
    mdraw = ImageDraw.Draw(mask)
    for i, line in enumerate(lines):
        mdraw.text((0, round((31.5 + 16.5 * i) * s)), line, font=font, fill=255, anchor="ls")
    canvas.paste(colors["ink"] + (255,), (0, 0), mask)

    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue()


def render_both(title, episode_date, seconds):
    return {theme: render_strip(title, episode_date, seconds, theme) for theme in THEMES}


def refresh_signature_strip(wp, show, episode_id, episode=None):
    """
    Renders both colourways for a just-published episode and hands them to WordPress, which stores them at fixed
    URLs. Never raises: the signature is a nicety, and a failure here must not fail or retry an episode publish.
    Returns True when the images were stored.
    """
    try:
        episode = episode or wp.get_episode(episode_id)
        meta = episode.get("meta", {})
        title = meta.get("ng_meta_aioseo_title") or episode.get("title", {}).get("rendered", "")
        episode_date = meta.get("ng_episode_date")
        if not title or not episode_date:
            logger.warning("Signature strip skipped for episode %s: missing title or date.", episode_id)
            return False
        images = render_both(title, episode_date, meta.get("ng_audio_seconds"))
        result = wp.store_signature_strip(
            show["id"],
            {
                "episode_date": str(episode_date)[:10],
                "light_png": base64.b64encode(images["light"]).decode("ascii"),
                "dark_png": base64.b64encode(images["dark"]).decode("ascii"),
            },
        )
        logger.info("Signature strip for %s: %s", episode_date, (result or {}).get("status", "stored"))
        return True
    except Exception:
        logger.exception("Signature strip refresh failed for episode %s (ignored).", episode_id)
        return False


def _main(argv):
    """Manual refresh:  python signature_strip.py <show_id> [episode_id]   (default: the show's newest episode)."""
    from config import load_config
    from wp_client import WPClient

    config = load_config()
    wp = WPClient(config["WP_BASE_URL"], config["WP_SERVICE_USERNAME"], config["WP_SERVICE_APP_PASSWORD"])
    show_id = int(argv[1])
    if len(argv) > 2:
        episode = wp.get_episode(int(argv[2]))
    else:
        published = [e for e in wp.list_episodes_for_show(show_id) if e.get("meta", {}).get("ng_url_website")]
        episode = max(published, key=lambda e: e["meta"].get("ng_episode_date") or "")
    ok = refresh_signature_strip(wp, {"id": show_id}, episode["id"], episode)
    print("stored" if ok else "not stored (see log)", episode["id"], episode.get("meta", {}).get("ng_episode_date"))
    return 0 if ok else 1


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    raise SystemExit(_main(sys.argv))
