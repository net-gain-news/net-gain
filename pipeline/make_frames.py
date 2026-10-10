"""
Builds the three frame templates (16:9 YouTube, 1200x630 website, 3000x3000 podcast square) for a colour palette.

A frame is a PNG with a fully transparent window (where the graphic shows) and an opaque footer band carrying the
horizontal logo; image_compositing.composite_frame lays it over the finished picture and visible_window() reads the
window from it, so a frame's own geometry is all the renderers need.

Geometry (matches the production frames):
  16:9      1280x720   8 px top stripe, window y 8-584, footer 584-720, logo 303 px wide at x=44
  1200x630  1200x630   8 px top stripe, window y 8-510, footer 510-630, logo 303 px wide at x=44
  square    3000x3000  no stripe,       window y 0-2600, footer 2600-3000, logo 1400 px wide at x=200
            (no stripe and a left-aligned logo well clear of the rounded corners podcast apps apply)

Palettes: "sage" (the original green scheme, archived in design/palettes/sage) and "denim" (the light Edtech scheme
adopted 2026-10-09: dark navy footer, cream "Net Gain", light-blue mark and "Edtech", matching the site header).
The logo artwork is the site's own wordmark rendered once per palette (templates/logo_horizontal*.png).

    python make_frames.py denim [out_dir]       # writes frame_16x9_denim.png, frame_1200x630_denim.png, frame_square_denim.png
"""

import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"

PALETTES = {
    "sage": {"bar": (30, 38, 32), "stripe": (61, 107, 74), "logo": "logo_horizontal.png"},
    "denim": {"bar": (31, 42, 58), "stripe": (47, 83, 121), "logo": "logo_horizontal_denim.png"},
}

WIDE = {
    "16x9": {"size": (1280, 720), "window_bottom": 584},
    "1200x630": {"size": (1200, 630), "window_bottom": 510},
}
STRIPE = 8
WIDE_LOGO_W, WIDE_LOGO_X, WIDE_LOGO_TOP_IN_BAR = 303, 44, 49
SQUARE = {"size": (3000, 3000), "window_bottom": 2600, "logo_w": 1400, "logo_x": 200}


def _logo(palette, width):
    logo = Image.open(TEMPLATES / PALETTES[palette]["logo"]).convert("RGBA")
    return logo.resize((width, round(logo.height * width / logo.width)), Image.LANCZOS)


def build_wide(spec, palette):
    cfg, p = WIDE[spec], PALETTES[palette]
    w, h = cfg["size"]
    bottom = cfg["window_bottom"]
    frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    frame.paste(Image.new("RGBA", (w, STRIPE), p["stripe"] + (255,)), (0, 0))
    frame.paste(Image.new("RGBA", (w, h - bottom), p["bar"] + (255,)), (0, bottom))
    frame.alpha_composite(_logo(palette, WIDE_LOGO_W), (WIDE_LOGO_X, bottom + WIDE_LOGO_TOP_IN_BAR))
    return frame


def build_square(palette):
    cfg, p = SQUARE, PALETTES[palette]
    w, h = cfg["size"]
    bottom = cfg["window_bottom"]
    frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    frame.paste(Image.new("RGBA", (w, h - bottom), p["bar"] + (255,)), (0, bottom))
    logo = _logo(palette, cfg["logo_w"])
    frame.alpha_composite(logo, (cfg["logo_x"], bottom + (h - bottom - logo.height) // 2))
    return frame


def build_all(palette):
    return {"16x9": build_wide("16x9", palette), "1200x630": build_wide("1200x630", palette), "square": build_square(palette)}


if __name__ == "__main__":
    palette = sys.argv[1] if len(sys.argv) > 1 else "denim"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else TEMPLATES
    for name, frame in build_all(palette).items():
        path = out / f"frame_{name}_{palette}.png"
        frame.save(path, optimize=True)
        print("wrote", path)
