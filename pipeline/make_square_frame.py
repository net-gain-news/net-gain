"""
Builds the 3000x3000 podcast-art frame template (a PNG with a fully transparent window and the footer band).

Reworked 2026-10-07 for the code-built cards: a shorter footer (400 px, window 0-2600) carrying the HORIZONTAL logo,
left-aligned on the content margin (200 px) and 1400 px wide, with no top stripe, so nothing sits in the corners that
podcast apps round off. The logo wordmark is the site's own (Familjen Grotesk 700, mark = two bars) rendered once to
templates/logo_horizontal.png.

    python make_square_frame.py [out.png]

Upload the result as the show's square frame (Edit Show > frames); cards.py measures the window from the frame itself.
For all three frames in either palette (sage or denim) use make_frames.py instead.
"""

import sys
from pathlib import Path

from PIL import Image

SIZE = 3000
BAR_TOP = 2600
BAR_COLOR = (30, 38, 32, 255)    # the site's #1e2620
LOGO_WIDTH = 1400
LEFT_MARGIN = 200
HERE = Path(__file__).resolve().parent


def build():
    frame = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    frame.paste(Image.new("RGBA", (SIZE, SIZE - BAR_TOP), BAR_COLOR), (0, BAR_TOP))
    logo = Image.open(HERE / "templates" / "logo_horizontal.png").convert("RGBA")
    logo = logo.resize((LOGO_WIDTH, round(logo.height * LOGO_WIDTH / logo.width)), Image.LANCZOS)
    frame.alpha_composite(logo, (LEFT_MARGIN, BAR_TOP + (SIZE - BAR_TOP - logo.height) // 2))
    return frame


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "templates" / "frame_square_3000.png"
    build().save(out, optimize=True)
    print("wrote", out)
