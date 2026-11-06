"""
The slim "latest newscast" module for the founder's email signature.

A transparent PNG (drawn at 3x so it is sharp on retina and phone screens): an outlined play button, a small label
("LATEST FROM NET GAIN EDTECH · NOV 5") and the headline in up to two lines. The play button is the click cue; there is
no duration and no coloured flash, so the module stays light next to the name and contact lines. It is always
340 x 52 display pixels so the signature's layout never shifts from one day to the next, and 340 wide so it fits a phone
screen at its real size (a wider image is shrunk by mail apps, which made the headline unreadably small on an iPhone,
2026-10-20). It is drawn in two colourways, one for light mail canvases and one for dark, because the text is baked into
the image; the signature swaps between them with a dark-mode style rule.

The module names the show the episode belongs to, so a recipient of a pitch for another show can see that the episode is
a sample from this one. After every website publish the pipeline renders both colourways and the plugin stores them at
fixed URLs: once per show ({show-slug}-strip-*) and once for the network ("latest-strip-*", replaced only when the new
episode is newer than the one it already shows, whichever show it belongs to). The signature points at the network
files, so any show's newest episode updates it.

Colours are the corporate palette from the live site (cream / warm greys). Sizes below are in display pixels;
everything is multiplied by SCALE when drawn.
"""

import base64
import io
import logging
from datetime import date as _date

from PIL import Image, ImageDraw

from cards import archivo, mono

logger = logging.getLogger("net_gain.signature_strip")

SCALE = 3
WIDTH, HEIGHT = 340, 52      # display pixels; the signature shows the image at exactly this size
TEXT_X = 44                  # the text column starts right of the 30 px play button
LABEL_SIZE, HEADLINE_SIZES = 9, (13.5, 13, 12.5, 12)

THEMES = {
    "light": {"ink": (0x12, 0x11, 0x0E), "muted": (0x6C, 0x6A, 0x64), "link": (0x4A, 0x47, 0x3F)},
    "dark": {"ink": (0xED, 0xE9, 0xE2), "muted": (0xA2, 0x9F, 0x98), "link": (0xC8, 0xC4, 0xBC)},
}


def short_date(episode_date):
    """'2026-11-05' -> 'NOV 5'."""
    d = _date.fromisoformat(str(episode_date)[:10])
    return f"{d:%b} {d.day}".upper()


def label_font():
    return mono(round(LABEL_SIZE * SCALE), medium=False)


def label_track():
    return 0.1 * LABEL_SIZE * SCALE


def fit_label(show_name, episode_date, max_width):
    """
    'LATEST FROM NET GAIN EDTECH · NOV 5', in tracked IBM Plex Mono. When it would not fit the text column the date goes
    first, then the end of a very long show name (ellipsis), so the show is always named. Widths are in drawn pixels.
    """
    name = " ".join(str(show_name or "").replace("\u2011", "-").split()).upper()
    font, track = label_font(), label_track()
    candidates = [f"LATEST FROM {name} · {short_date(episode_date)}", f"LATEST FROM {name}"]
    for text in candidates:
        if _tracked_width(font, text, track) <= max_width:
            return text
    while name and _tracked_width(font, f"LATEST FROM {name}…", track) > max_width:
        name = name[:-1].rstrip()
    return f"LATEST FROM {name}…"


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
    Archivo SemiBold at 13.5 display px, wrapped to at most two balanced lines; shrunk step by step to 12 before giving
    up, and only then ellipsised on the last line. max_width is in drawn pixels. Returns (lines, font).
    """
    words = text.split()
    for size in HEADLINE_SIZES:
        font = archivo(round(size * SCALE), 600, 100)
        lines = _balance(words, font, _wrap_lines(words, font, max_width))
        if len(lines) <= max_lines and all(font.getlength(l) <= max_width for l in lines):
            return lines, font
    font = archivo(round(HEADLINE_SIZES[-1] * SCALE), 600, 100)
    lines = _wrap_lines(words, font, max_width)[:max_lines]
    last = lines[-1] if lines else ""
    while last and font.getlength(last + "…") > max_width:
        last = last[:-1].rstrip()
    if lines:
        lines[-1] = last + "…"
    return lines, font


def render_strip(title, show_name, episode_date, theme):
    """PNG bytes (RGBA, WIDTH*SCALE x HEIGHT*SCALE) for one colourway: theme 'light' or 'dark'."""
    colors = THEMES[theme]
    s = SCALE
    canvas = Image.new("RGBA", (WIDTH * s, HEIGHT * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    text_w = (WIDTH - TEXT_X) * s

    lines, font = _fit_headline((title or "").replace("\u2011", "-").strip(), text_w)
    drop = 0 if len(lines) >= 2 else 9          # one line of headline: centre the text beside the button

    # The play button: an outlined circle with a triangle, vertically centred.
    cy, r = HEIGHT / 2, 15
    draw.ellipse([0, (cy - r) * s, 2 * r * s, (cy + r) * s], outline=colors["link"] + (255,), width=round(1.3 * s))
    tri_h, tri_w = 11 * s, 11 * s * 0.86
    cx = (r + 1) * s
    draw.polygon([(cx - tri_w * 0.38, cy * s - tri_h / 2), (cx - tri_w * 0.38, cy * s + tri_h / 2), (cx + tri_w * 0.62, cy * s)],
                 fill=colors["link"] + (255,))

    # The label, then the headline.
    _draw_tracked(canvas, TEXT_X * s, round((9.6 + drop) * s), fit_label(show_name, episode_date, text_w),
                  label_font(), label_track(), colors["muted"])
    mask = Image.new("L", canvas.size, 0)
    mdraw = ImageDraw.Draw(mask)
    for i, line in enumerate(lines):
        mdraw.text((TEXT_X * s, round((28 + drop + 17 * i) * s)), line, font=font, fill=255, anchor="ls")
    canvas.paste(colors["ink"] + (255,), (0, 0), mask)

    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue()


def render_both(title, show_name, episode_date):
    return {theme: render_strip(title, show_name, episode_date, theme) for theme in THEMES}


def _show_name(wp, show):
    """The show's name as the signature should print it ('Net Gain Edtech'); the tick context carries it, otherwise read the show."""
    name = (show or {}).get("name")
    if not name:
        name = ((wp.get_show(show["id"]) or {}).get("title") or {}).get("rendered", "")
    return name


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
        show_name = _show_name(wp, show)
        if not show_name:
            logger.warning("Signature strip skipped for episode %s: the show has no name.", episode_id)
            return False
        images = render_both(title, show_name, episode_date)
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
    show = next((x for x in wp.get_tick_context() if x["id"] == show_id), {"id": show_id})
    if len(argv) > 2:
        episode = wp.get_episode(int(argv[2]))
    else:
        published = [e for e in wp.list_episodes_for_show(show_id) if e.get("meta", {}).get("ng_url_website")]
        episode = max(published, key=lambda e: e["meta"].get("ng_episode_date") or "")
    ok = refresh_signature_strip(wp, show, episode["id"], episode)
    print("stored" if ok else "not stored (see log)", episode["id"], episode.get("meta", {}).get("ng_episode_date"))
    return 0 if ok else 1


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    raise SystemExit(_main(sys.argv))
