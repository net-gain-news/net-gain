import os
import sys
import unittest
from io import BytesIO

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import make_frames
from image_compositing import composite_frame, visible_window


def png(frame):
    buf = BytesIO()
    frame.save(buf, format="PNG")
    return buf.getvalue()


class FrameGeometryTests(unittest.TestCase):
    def test_windows_match_the_production_geometry_for_both_palettes(self):
        for palette in make_frames.PALETTES:
            frames = make_frames.build_all(palette)
            self.assertEqual(visible_window(png(frames["16x9"]), 1280, 720), (0, 8, 1280, 584), palette)
            self.assertEqual(visible_window(png(frames["1200x630"]), 1200, 630), (0, 8, 1200, 510), palette)
            self.assertEqual(visible_window(png(frames["square"]), 3000, 3000), (0, 0, 3000, 2600), palette)

    def test_footer_band_and_stripe_use_the_palette_colours(self):
        for palette, p in make_frames.PALETTES.items():
            frames = make_frames.build_all(palette)
            self.assertEqual(frames["16x9"].getpixel((1270, 700))[:3], p["bar"])
            self.assertEqual(frames["16x9"].getpixel((600, 3))[:3], p["stripe"])
            self.assertEqual(frames["square"].getpixel((2900, 2900))[:3], p["bar"])
            self.assertEqual(frames["square"].getpixel((600, 1))[3], 0)       # no stripe on the square

    def test_the_logo_sits_left_aligned_inside_the_footer_and_never_touches_the_window(self):
        frames = make_frames.build_all("denim")
        for name, (w, h, bottom) in {"16x9": (1280, 720, 584), "1200x630": (1200, 630, 510), "square": (3000, 3000, 2600)}.items():
            frame = frames[name]
            bar = make_frames.PALETTES["denim"]["bar"]
            xs, ys = [], []
            for y in range(bottom, h, 2 if name != "square" else 8):
                for x in range(0, w // 2, 2 if name != "square" else 8):
                    p = frame.getpixel((x, y))
                    if p[3] and sum(abs(a - b) for a, b in zip(p[:3], bar)) > 60:
                        xs.append(x); ys.append(y)
            self.assertTrue(xs, name)
            self.assertGreater(min(ys), bottom + (h - bottom) * 0.1, name)
            self.assertLess(max(ys), h - (h - bottom) * 0.1, name)
            self.assertLess(min(xs), w * 0.1, name)                            # left-aligned

    def test_denim_logo_uses_the_header_colours(self):
        logo = Image.open(os.path.join(make_frames.TEMPLATES, "logo_horizontal_denim.png")).convert("RGBA")
        colours = {p[:3] for p in logo.getdata() if p[3] == 255}
        self.assertIn((0xf3, 0xed, 0xe3), colours)       # "Net Gain"
        self.assertIn((0x9f, 0xbb, 0xdb), colours)       # mark and "Edtech"

    def test_a_frame_composites_over_a_picture_of_the_right_size(self):
        frame = make_frames.build_wide("16x9", "denim")
        out = composite_frame(Image.new("RGB", (1280, 720), (200, 100, 50)), png(frame))
        self.assertEqual(out.getpixel((640, 300)), (200, 100, 50))
        self.assertEqual(out.getpixel((1270, 700)), make_frames.PALETTES["denim"]["bar"])


if __name__ == "__main__":
    unittest.main()
