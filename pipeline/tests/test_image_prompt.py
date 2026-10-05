import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from image_prompt import (
    ART_STYLE,
    ART_STYLE_LOGO,
    MAX_PROMPT_ATTEMPTS,
    RESPONSE_SCHEMA,
    ImagePromptError,
    build_system_prompt,
    compose_image_prompt,
    find_prompt_problems,
    generate_image_prompt_for_episode,
)


def resp(prompt, logo_only=False):
    return json.dumps({"image_prompt": prompt, "logo_only": logo_only})


CLEAN = "A close-up of a teacher's hands holding an ID card beside a laptop camera, bright directional light, near-black background."
# Real examples captured from live generations (2026-10-02).
JUNK_TAIL_1 = CLEAN + "\u201d}  -- 1 valid JSON object only per instructions, correcting format below.  {"
JUNK_TAIL_2 = CLEAN + "\u201d}on Hold the quotation marks; cleaner version needed without stray punctuation.}}',}) \uc774iderman);..{"


class BuildSystemPromptTests(unittest.TestCase):
    def test_includes_show_name(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("Net Gain Edtech", prompt)

    def test_requires_a_concrete_detail_not_just_a_category(self):
        """Rewritten 2026-09-16 after three live episodes all produced generic
        conceptual imagery (anonymous people, vague screens) instead of
        anything tied to the lead story's actual specifics."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("concrete", prompt.lower())

    def test_bans_the_observed_stock_photo_cliches_by_name(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("shaking hands", prompt)
        self.assertIn("conference table", prompt)

    def test_requests_prominent_official_logos_only_when_unambiguous(self):
        """Human-operator decision (2026-10-02), reversing 2026-09-16: no
        whitelist, so the model must judge ambiguity itself and omit the logo
        when unsure."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("the image IS that logo", prompt)
        self.assertIn("nothing else in the image", prompt)
        self.assertIn("unambiguous", prompt)
        self.assertIn("use no logo at all", prompt)
        self.assertNotIn("Do not include any company logo", prompt)

    def test_product_stories_use_the_famous_parents_logo(self):
        """Live finding (2026-10-02): a Gemini-in-Google-Classroom story had
        three candidate marks (Google, Gemini, Classroom), so the model judged
        it ambiguous and skipped the logo. Resolved upward to the parent."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("logo of the famous parent organization", prompt)

    def test_logo_decision_comes_before_the_concrete_detail_search(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertLess(prompt.index("LOGO-ONLY IMAGE"), prompt.index("find ONE"))

    def test_logo_images_take_their_ground_and_material_from_the_house_style(self):
        """2026-10-02: a logo on white clashed with the dark graphics. 2026-10-05: the logo now gets the same
        house style as every other image (a dark charcoal ground, cut paper), so the prompt-writer says nothing
        about background or material."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("Say nothing about the background or the material", prompt)
        self.assertIn("renders the logo as cut paper", prompt)
        self.assertIn("applied to it just as to any other image", prompt)
        self.assertNotIn("solid white", prompt)

    def test_generic_setting_allowance_is_gone(self):
        """Removed 2026-10-02: it licensed the generic classroom/office
        fallbacks the human operator was unhappy with."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertNotIn("is fine, as is", prompt)
        self.assertIn("Avoid generic stock settings", prompt)

    def test_the_model_describes_only_the_subject_and_the_photorealism_preference_is_gone(self):
        """2026-10-05: YouTube auto-labels photorealistic AI imagery, so style is no longer the model's call."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertNotIn("Prefer a photorealistic", prompt)
        self.assertNotIn("photo/illustration editor", prompt)
        self.assertIn("Describe ONLY the subject and its composition", prompt)
        self.assertIn("Do NOT specify any art style", prompt)

    def test_tone_rule_replaces_the_old_high_contrast_rule(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertNotIn("HIGH CONTRAST ONLY", prompt)
        self.assertIn("TONE.", prompt)
        self.assertIn("do not ask for a black or very light background", prompt)

    def test_avoids_subjects_that_invite_lettering(self):
        """Live finding (2026-10-05): a prompt describing a toggle switched 'off' produced two rendered 'off'
        labels despite the style's no-text rule."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("Avoid subjects that invite lettering", prompt)
        self.assertIn("never describe an on/off toggle", prompt)

    def test_screens_are_not_the_default_subject(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("default subject", prompt)

    def test_allows_financial_iconography_without_hardcoding_dollar_sign(self):
        """Human-operator decision (2026-09-16): money symbols are fine for
        financial stories, but must not default to the US dollar sign - not
        every show's stories are US-market-specific."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("currency", prompt.lower())
        self.assertIn("do not default to the us dollar sign", prompt.lower())

    def test_financial_iconography_may_not_spell_out_the_amount(self):
        """Live incident (2026-09-17): the first real episode under the
        rewritten prompt showed a genuine, on-topic tablet/AI-tutoring scene
        (the concrete-detail fix working) but also rendered the word
        "BILLION" as garbled background text for a $400M-pledge story - the
        financial-iconography rule permitted graphical money symbols but
        never explicitly excluded spelling the amount out, so it won out
        over the general no-readable-text rule on this exact overlap."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("never spell out the actual amount", prompt.lower())


class GenerateImagePromptForEpisodeTests(unittest.TestCase):
    def test_wires_schema_and_no_web_search_into_the_generate_call(self):
        captured = {}

        def fake_generate(system, user_content, tools, response_schema):
            captured["system"] = system
            captured["user_content"] = user_content
            captured["tools"] = tools
            captured["response_schema"] = response_schema
            return resp(CLEAN)

        result = generate_image_prompt_for_episode(
            fake_generate, "Net Gain Edtech", "2026-09-16", "Today's script text."
        )

        self.assertEqual(result, f"{CLEAN} {ART_STYLE}")
        self.assertEqual(captured["tools"], [])
        self.assertIs(captured["response_schema"], RESPONSE_SCHEMA)
        self.assertIn("Today's script text.", captured["user_content"])
        self.assertIn("2026-09-16", captured["user_content"])


class ArtStyleTests(unittest.TestCase):
    def test_is_cut_paper_on_a_dark_charcoal_ground_about_a_quarter_brightness_but_not_black(self):
        """Operator, 2026-10-05: ground darkened to 25-30% (the model overshoots a request for one third)."""
        self.assertIn("cut-paper collage", ART_STYLE)
        self.assertIn("dark charcoal-grey paper", ART_STYLE)
        self.assertIn("about one-quarter brightness", ART_STYLE)
        self.assertIn("but not black", ART_STYLE)

    def test_avoids_every_photographic_cue_and_all_text(self):
        for phrase in ("No gradients", "lens blur", "depth of field", "3D rendering", "Absolutely no text"):
            self.assertIn(phrase, ART_STYLE)

    def test_keeps_the_subject_out_of_the_overlay_zone(self):
        for style in (ART_STYLE, ART_STYLE_LOGO):
            self.assertIn("top 65 percent", style)
            self.assertIn("overlay covers the bottom fifth", style)

    def test_is_appended_to_an_ordinary_subject(self):
        self.assertEqual(compose_image_prompt(CLEAN, logo_only=False), f"{CLEAN} {ART_STYLE}")

    def test_is_applied_to_logo_only_images_too_with_the_logo_permitted(self):
        """Operator decision 2026-10-05: uniform look, so logos are cut paper on the same ground."""
        composed = compose_image_prompt("Official Google logo.", logo_only=True)
        self.assertEqual(composed, f"Official Google logo. {ART_STYLE_LOGO}")
        self.assertIn("cut-paper collage", composed)
        self.assertIn("real logo itself", composed)
        self.assertNotIn("no text, letters, numerals or logos", composed)

    def test_ordinary_images_still_forbid_logos_and_text(self):
        self.assertIn("Absolutely no text, letters, numerals or logos", ART_STYLE)


class FindPromptProblemsTests(unittest.TestCase):
    def test_a_clean_prompt_has_no_problems(self):
        self.assertEqual(find_prompt_problems(CLEAN), [])

    def test_accents_curly_quotes_dashes_and_currency_symbols_are_fine(self):
        self.assertEqual(find_prompt_problems(CLEAN + " A caf\u00e9 sign \u2014 \u201cOpen\u201d, priced in \u20ac and \u00a3."), [])

    def test_rejects_both_real_junk_tails(self):
        self.assertTrue(find_prompt_problems(JUNK_TAIL_1))
        problems = find_prompt_problems(JUNK_TAIL_2)
        self.assertIn("contains braces", problems)
        self.assertIn("contains characters outside Latin text", problems)

    def test_rejects_other_scripts_on_their_own(self):
        self.assertIn("contains characters outside Latin text", find_prompt_problems(CLEAN + " \uc774"))

    def test_rejects_json_talk_backticks_and_empty(self):
        self.assertIn("mentions JSON", find_prompt_problems(CLEAN + " Return valid json."))
        self.assertIn("contains a backtick", find_prompt_problems(CLEAN + " ```"))
        self.assertIn("empty or too short", find_prompt_problems(""))
        self.assertIn("empty or too short", find_prompt_problems(None))


class GenerationGuardTests(unittest.TestCase):
    def run_with(self, responses):
        calls = []

        def fake(system, user_content, tools, response_schema):
            calls.append(1)
            return responses[min(len(calls), len(responses)) - 1]

        return calls, lambda: generate_image_prompt_for_episode(fake, "Net Gain Edtech", "2026-10-02", "script")

    def test_a_clean_first_response_is_one_call(self):
        calls, run = self.run_with([resp(CLEAN)])
        self.assertEqual(run(), f"{CLEAN} {ART_STYLE}")
        self.assertEqual(len(calls), 1)

    def test_junk_is_regenerated_and_the_clean_retry_is_returned(self):
        calls, run = self.run_with([resp(JUNK_TAIL_1), resp(CLEAN)])
        self.assertEqual(run(), f"{CLEAN} {ART_STYLE}")
        self.assertEqual(len(calls), 2)

    def test_a_malformed_response_is_retried_too(self):
        calls, run = self.run_with(["not json at all", resp(CLEAN)])
        self.assertEqual(run(), f"{CLEAN} {ART_STYLE}")
        self.assertEqual(len(calls), 2)

    def test_a_logo_only_response_gets_the_logo_variant_of_the_house_style(self):
        calls, run = self.run_with([resp("The official Google logo, flat and centered.", logo_only=True)])
        self.assertEqual(run(), f"The official Google logo, flat and centered. {ART_STYLE_LOGO}")

    def test_gives_up_loudly_after_the_attempt_limit(self):
        calls, run = self.run_with([resp(JUNK_TAIL_2)])
        with self.assertRaises(ImagePromptError) as ctx:
            run()
        self.assertEqual(len(calls), MAX_PROMPT_ATTEMPTS)
        self.assertIn("braces", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
