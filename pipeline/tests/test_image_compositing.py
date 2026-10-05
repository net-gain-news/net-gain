import os
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from image_compositing import apply_duotone


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


if __name__ == "__main__":
    unittest.main()
