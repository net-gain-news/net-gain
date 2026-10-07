import os
import sys
import unittest
from datetime import date, timedelta
from io import BytesIO

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cards
from cards import CardContent, CardLayoutError, Canvas

MOVES = [{"t": f"T{i}", "co": f"Company {i}", "mv": (i - 25) / 5} for i in range(50)]
CONTENT = CardContent(
    episode_date=date(2026, 10, 6),   # a Tuesday
    headline="South Carolina school-choice payments hit by another cyberattack",
    keywords=["Cyberattack", "AI detectors", "Acquisition"],
    index={"pct": 0.23, "ytd": -8.1, "moves": MOVES},
)
WINDOWS = {"wide": (8, 584), "square": (0, 2600)}


def frame_png(size, window_top, window_bottom):
    frame = Image.new("RGBA", size, (30, 38, 32, 255))
    frame.paste(Image.new("RGBA", (size[0], window_bottom - window_top), (0, 0, 0, 0)), (0, window_top))
    buf = BytesIO()
    frame.save(buf, format="PNG")
    return buf.getvalue()


class RotationTests(unittest.TestCase):
    FAMILIES = {
        "A": "headline", "E": "headline", "B1": "keyword", "D3": "keyword",
        "C": "index", "F": "index", "D5": "date", "D6": "date", "D8": "date",
    }

    def test_nine_templates_and_the_first_is_A(self):
        self.assertEqual(len(cards.TEMPLATE_ORDER), 9)
        self.assertEqual(cards.TEMPLATE_ORDER[0], "A")
        self.assertEqual(set(cards.TEMPLATE_ORDER), set(cards.TEMPLATES))

    def test_no_two_similar_treatments_are_adjacent_including_across_the_wrap(self):
        order = cards.TEMPLATE_ORDER
        for i, template in enumerate(order):
            neighbour = order[(i + 1) % len(order)]
            self.assertNotEqual(self.FAMILIES[template], self.FAMILIES[neighbour], f"{template} then {neighbour}")

    def test_the_three_waveform_cards_are_never_adjacent(self):
        order = cards.TEMPLATE_ORDER
        waveform = {"A", "D6", "D8"}
        for i, template in enumerate(order):
            self.assertFalse(template in waveform and order[(i + 1) % len(order)] in waveform)

    def test_next_template_follows_the_previous_one(self):
        self.assertEqual(cards.candidate_templates("A", CONTENT)[0], "B1")
        self.assertEqual(cards.candidate_templates("D5", CONTENT)[0], "A")     # wraps
        self.assertEqual(cards.candidate_templates("", CONTENT)[0], "A")
        self.assertEqual(cards.candidate_templates("nonsense", CONTENT)[0], "A")

    def test_index_cards_are_skipped_without_same_day_index_data(self):
        no_index = CardContent(episode_date=CONTENT.episode_date, headline=CONTENT.headline, keywords=CONTENT.keywords)
        candidates = cards.candidate_templates("B1", no_index)
        self.assertNotIn("C", candidates)
        self.assertNotIn("F", candidates)
        self.assertEqual(candidates[0], "D6")

    def test_date_cards_are_skipped_on_weekends_and_text_cards_without_text(self):
        saturday = CardContent(episode_date=date(2026, 10, 3), headline="x" * 20, keywords=CONTENT.keywords, index=CONTENT.index)
        self.assertFalse({"D5", "D6", "D8"} & set(cards.candidate_templates("", saturday)))
        bare = CardContent(episode_date=CONTENT.episode_date, index=CONTENT.index)
        self.assertEqual(set(cards.candidate_templates("", bare)), {"C", "F", "D5", "D6", "D8"})
        two_words = CardContent(episode_date=CONTENT.episode_date, headline="A headline here", keywords=["One", "Two"])
        self.assertNotIn("B1", cards.candidate_templates("", two_words))
        self.assertNotIn("D3", cards.candidate_templates("", two_words))


class RenderTests(unittest.TestCase):
    def test_every_template_renders_in_both_geometries(self):
        for template in cards.TEMPLATE_ORDER:
            for kind in ("wide", "square"):
                image = cards.render_card(template, CONTENT, kind, WINDOWS[kind])
                self.assertEqual(image.size, cards.WIDE_SIZE if kind == "wide" else cards.SQUARE_SIZE, f"{template} {kind}")
                self.assertEqual(image.mode, "RGB")

    def test_space_above_and_below_is_equal_for_every_template(self):
        """Operator requirement: equal padding above and below, measured to the frame window edges."""
        for template in cards.TEMPLATE_ORDER:
            for kind in ("wide", "square"):
                canvas = Canvas(kind, WINDOWS[kind])
                cards.TEMPLATES[template](canvas, CONTENT)
                bbox = canvas.layer.getchannel("A").getbbox()
                dy = round((canvas.top + canvas.bottom - bbox[1] - bbox[3]) / 2)
                above = bbox[1] + dy - canvas.top
                below = canvas.bottom - (bbox[3] + dy)
                self.assertLessEqual(abs(above - below), 2, f"{template} {kind}: {above} above, {below} below")

    def test_content_never_touches_the_websites_latest_badge_corner(self):
        """The site draws a red LATEST badge over the top-left of the hero image (about 160x85 of the 1280x720 art)."""
        for template in cards.TEMPLATE_ORDER:
            canvas = Canvas("wide", WINDOWS["wide"])
            cards.TEMPLATES[template](canvas, CONTENT)
            bbox = canvas.layer.getchannel("A").getbbox()
            dy = round((canvas.top + canvas.bottom - bbox[1] - bbox[3]) / 2)
            corner = canvas.layer.crop((0, 0, 170, 84 - dy)) if 84 - dy > 0 else None
            if corner is not None:
                self.assertIsNone(corner.getchannel("A").getbbox(), f"{template} has content under the badge")

    def test_block_templates_use_no_large_light_green_fills(self):
        """Operator, 2026-10-07: large swaths of light green are alarming; tiles are the dark green."""
        for template in ("B1", "D3", "D5", "D6", "D8"):
            for kind in ("wide", "square"):
                image = cards.render_card(template, CONTENT, kind, WINDOWS[kind])
                small = image.resize((200, 200))
                share = sum(1 for p in small.getdata() if p == cards.ACC) / (200 * 200)
                self.assertLess(share, 0.08, f"{template} {kind} is {share:.0%} light green")

    def test_text_that_cannot_fit_raises_instead_of_clipping(self):
        long = CardContent(episode_date=CONTENT.episode_date, keywords=["Internationalization " * 6, "Extraordinarily", "Incomprehensibly"])
        for kind in ("wide", "square"):
            with self.assertRaises(CardLayoutError):
                cards.render_card("B1", long, kind, WINDOWS[kind])
        no_room = CardContent(episode_date=CONTENT.episode_date, headline="word " * 80)
        with self.assertRaises(CardLayoutError):
            cards.render_card("A", no_room, "wide", WINDOWS["wide"])

    def test_descenders_stay_inside_their_blocks(self):
        """Words with descenders (y, q, g, p) were biting block edges before; the check must pass for them."""
        content = CardContent(episode_date=date(2026, 10, 7), headline="Quick query pays big", keywords=["Query", "Gypsy pigs", "Equity"])
        for template in ("B1", "D3", "D5", "D6", "D8"):
            for kind in ("wide", "square"):
                cards.render_card(template, content, kind, WINDOWS[kind])   # raises CardLayoutError on any breach

    def test_weekday_cards_work_for_every_weekday(self):
        for offset in range(5):
            content = CardContent(episode_date=date(2026, 10, 5) + timedelta(days=offset), keywords=CONTENT.keywords, headline=CONTENT.headline)
            for template in ("D5", "D6", "D8"):
                cards.render_card(template, content, "wide", WINDOWS["wide"])

    def test_index_cards_cope_with_a_down_day_and_a_missing_ytd(self):
        down = CardContent(episode_date=CONTENT.episode_date, index={"pct": -1.12, "ytd": None, "moves": [dict(m, mv=-m["mv"]) for m in MOVES]})
        for template in ("C", "F"):
            for kind in ("wide", "square"):
                cards.render_card(template, down, kind, WINDOWS[kind])

    def test_index_heatmap_copes_with_more_and_fewer_constituents(self):
        for n in (8, 30, 60):
            content = CardContent(episode_date=CONTENT.episode_date, index={"pct": 0.5, "ytd": 1.0, "moves": MOVES[:1] * n and [dict(MOVES[i % 50]) for i in range(n)]})
            cards.render_card("C", content, "wide", WINDOWS["wide"])
            cards.render_card("C", content, "square", WINDOWS["square"])

    def test_render_formats_returns_the_three_finished_sizes(self):
        frames = {"16x9": frame_png((1280, 720), 8, 584), "1200x630": frame_png((1200, 630), 8, 510), "square": frame_png((3000, 3000), 0, 2600)}
        for template in ("A", "C", "D6"):
            out = cards.render_formats(template, CONTENT, frames)
            self.assertEqual(out["16x9"].size, (1280, 720))
            self.assertEqual(out["1200x630"].size, (1200, 630))
            self.assertEqual(out["square"].size, (3000, 3000))
            self.assertEqual(out["square"].getpixel((10, 2990)), (30, 38, 32))   # the footer band is painted by the frame

    def test_the_real_square_footer_template_has_the_expected_window(self):
        from image_compositing import visible_window
        template = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "frame_square_3000.png")
        self.assertEqual(visible_window(open(template, "rb").read(), 3000, 3000), (0, 0, 3000, 2600))


class NumeralTests(unittest.TestCase):
    """Operator, 2026-10-07: the giant day numeral must never run off the graphic, even the widest date."""

    def _ink(self, text, kind):
        size = cards.WIDE_SIZE if kind == "wide" else cards.SQUARE_SIZE
        window = WINDOWS[kind]
        right, cy, wmax, hmax = (1198, (window[0] + window[1]) / 2, 640, 400) if kind == "wide" else (2800, (window[0] + window[1]) / 2, 2300, 1500)
        layer = Image.new("RGB", size, (0, 0, 0))
        cards.draw_numeral(ImageDraw.Draw(layer), text, right, cy, wmax, hmax)
        return layer.getbbox(), right, window

    def test_every_two_digit_value_stays_inside_the_graphic(self):
        for kind in ("wide", "square"):
            for n in range(0, 100):
                bbox, right, window = self._ink(f"{n:02d}", kind)
                self.assertGreaterEqual(bbox[0], 0, f"{n:02d} {kind}")
                self.assertLessEqual(bbox[2], right + 2, f"{n:02d} {kind} runs past the right margin")
                self.assertGreaterEqual(bbox[1], window[0], f"{n:02d} {kind} above the window")
                self.assertLessEqual(bbox[3], window[1], f"{n:02d} {kind} below the window")

    def test_the_numeral_is_drawn_by_template_e_for_every_day_of_a_month(self):
        for day in range(1, 32):
            content = CardContent(episode_date=date(2026, 12, day), headline=CONTENT.headline)
            for kind in ("wide", "square"):
                cards.render_card("E", content, kind, WINDOWS[kind])


if __name__ == "__main__":
    unittest.main()
