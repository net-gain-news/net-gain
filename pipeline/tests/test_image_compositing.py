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

    def test_stretches_a_low_contrast_source_to_the_full_color_range(self):
        flat = Image.new("RGB", (256, 1))
        flat.putdata([(100 + v // 8, 100 + v // 8, 100 + v // 8) for v in range(256)])
        result = apply_duotone(flat, "#000000", "#ffffff")
        values = [result.getpixel((x, 0))[0] for x in range(256)]
        self.assertLess(min(values), 10)
        self.assertGreater(max(values), 245)

    def test_midtones_are_strictly_between_the_two_colors(self):
        result = apply_duotone(self._gradient(), "#1e2620", "#a9cba0")
        mid = result.getpixel((128, 0))
        for channel, lo, hi in zip(mid, (0x1E, 0x26, 0x20), (0xA9, 0xCB, 0xA0)):
            self.assertGreater(channel, lo)
            self.assertLess(channel, hi)


if __name__ == "__main__":
    unittest.main()
