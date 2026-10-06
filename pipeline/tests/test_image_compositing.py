import os
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from io import BytesIO

from image_compositing import apply_duotone, composite_and_encode, fit_to_visible_window, visible_window


class ApplyDuotoneTests(unittest.TestCase):
    def _gradient(self):
        image = Image.new("RGB", (256, 1))
        image.putdata([(v, v, v) for v in range(256)])
        return image

    def test_black_maps_to_shadow_and_white_to_highlight(self):
        """The old multiply/screen blend stack compressed a 0-255 image into a
        ~25-level band (measured live, 2026-10-02), so graphics read as flat.
        The gradient map must reach both configured colors exactly."""
        result = apply_duotone(self._gradient(), "#1e2620", "#a9cba0")
        self.assertEqual(result.getpixel((0, 0)), (0x1E, 0x26, 0x20))
        self.assertEqual(result.getpixel((255, 0)), (0xA9, 0xCB, 0xA0))

    def test_the_bright_end_is_scaled_up_to_the_highlight_color(self):
        dim = Image.new("RGB", (256, 1))
        dim.putdata([(v // 2, v // 2, v // 2) for v in range(256)])  # brightest pixel is only 127
        result = apply_duotone(dim, "#000000", "#ffffff")
        self.assertGreater(max(result.getpixel((x, 0))[0] for x in range(256)), 245)

    def test_the_black_end_is_not_stretched_so_a_mid_dark_ground_stays_above_the_shadow_color(self):
        """Live finding (2026-10-05): autocontrast pulled a dark background to exactly the shadow color,
        which is also the overlay bar's color, so the two merged. A ground that is mid-dark in the source
        (about one third brightness) must stay visibly lighter than the bar."""
        image = Image.new("RGB", (100, 2), (85, 85, 85))      # the ground, ~1/3 brightness
        image.paste((235, 235, 235), (0, 0, 100, 1))          # a bright subject row
        result = apply_duotone(image, "#1e2620", "#3d6b4a")
        ground, shadow = result.getpixel((50, 1)), (0x1E, 0x26, 0x20)
        self.assertGreater(ground[1], shadow[1] + 15)         # clearly distinct from the bar colour
        self.assertGreater(result.getpixel((50, 0))[1], ground[1])  # subject still lighter than ground

    def test_midtones_are_strictly_between_the_two_colors(self):
        result = apply_duotone(self._gradient(), "#1e2620", "#a9cba0")
        mid = result.getpixel((128, 0))
        for channel, lo, hi in zip(mid, (0x1E, 0x26, 0x20), (0xA9, 0xCB, 0xA0)):
            self.assertGreater(channel, lo)
            self.assertLess(channel, hi)


def make_frame(width, height, window_top, window_bottom):
    """An opaque frame with a fully transparent horizontal window, like the real ones (a bar covers the bottom)."""
    frame = Image.new("RGBA", (width, height), (30, 38, 32, 255))
    frame.paste((0, 0, 0, 0), (0, window_top, width, window_bottom))
    buf = BytesIO()
    frame.save(buf, format="PNG")
    return buf.getvalue()


class VisibleWindowTests(unittest.TestCase):
    def test_measures_the_transparent_window_in_output_coordinates(self):
        frame = make_frame(1280, 720, 8, 584)  # the real 16:9 frame
        self.assertEqual(visible_window(frame, 1280, 720), (0, 8, 1280, 584))

    def test_scales_the_window_when_the_frame_is_smaller_than_the_output(self):
        """The real square frame is 2560 px but the output is 3000 px."""
        frame = make_frame(2560, 2560, 21, 2232)
        left, top, right, bottom = visible_window(frame, 3000, 3000)
        self.assertEqual((left, right), (0, 3000))
        self.assertEqual(top, round(21 * 3000 / 2560))
        self.assertEqual(bottom, round(2232 * 3000 / 2560))

    def test_a_frame_with_no_transparent_area_falls_back_to_the_whole_output(self):
        opaque = Image.new("RGBA", (100, 50), (1, 2, 3, 255))
        buf = BytesIO()
        opaque.save(buf, format="PNG")
        self.assertEqual(visible_window(buf.getvalue(), 100, 50), (0, 0, 100, 50))


class FitToVisibleWindowTests(unittest.TestCase):
    def test_the_whole_base_image_lands_inside_the_visible_window(self):
        """2026-10-05: the base used to be fitted to the full output and the frame painted over its bottom, so
        a third of a subject could be hidden. Now the base's top and bottom edges are the window's edges."""
        frame = make_frame(1280, 720, 8, 584)
        base = Image.new("RGB", (2100, 900), (0, 0, 255))
        base.paste((255, 0, 0), (0, 0, 2100, 40))          # red band along the TOP edge of the base
        base.paste((0, 255, 0), (0, 860, 2100, 900))       # green band along the BOTTOM edge
        out = fit_to_visible_window(base, frame, 1280, 720)
        self.assertEqual(out.getpixel((640, 9)), (255, 0, 0))       # base top = first visible row
        self.assertEqual(out.getpixel((640, 582)), (0, 255, 0))     # base bottom = last visible row

    def test_the_subject_is_centered_in_the_visible_window_not_the_whole_output(self):
        frame = make_frame(1280, 720, 8, 584)
        base = Image.new("RGB", (2100, 900), (10, 10, 10))
        base.paste((250, 250, 250), (1000, 400, 1100, 500))   # a small bright subject at the base's centre
        out = fit_to_visible_window(base, frame, 1280, 720)
        bright = [(x, y) for y in range(8, 584, 2) for x in range(0, 1280, 2) if out.getpixel((x, y))[0] > 200]
        ys = [y for _, y in bright]
        self.assertAlmostEqual((min(ys) + max(ys)) / 2, (8 + 584) / 2, delta=12)   # centre of the window, not of 720

    def test_composite_and_encode_uses_the_window(self):
        frame = make_frame(1200, 630, 8, 510)
        spec = {"width": 1200, "height": 630, "format": "WEBP", "mime": "image/webp", "max_bytes": None}
        data, name = composite_and_encode(Image.new("RGB", (2100, 900), (200, 50, 50)), frame, spec, "show", "2026-10-05", "1200x630")
        self.assertTrue(name.endswith(".webp"))
        self.assertGreater(len(data), 100)


if __name__ == "__main__":
    unittest.main()
