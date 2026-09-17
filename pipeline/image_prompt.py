"""
Image-prompt generation (SPEC.md Section 7): turns an episode's already-
written final script into a single text-to-image prompt for the base art.

Deliberately its own independent Claude call, not a reuse of
metadata_generation.py's output - images_rendered and metadata_generated are
siblings (Section 8.3: both depend only on audio_received, neither on the
other), so they must not be coupled to each other's timing even though both
happen to derive from the same source text.

No web search tool here (unlike script_generation.py) - like metadata
generation, this repackages an already-written final script, it doesn't need
to research anything new.

Rewritten 2026-09-16 after the first three live episodes all produced the
same failure mode: generic conceptual imagery (anonymous people shaking
hands around a table, a vague chart glowing on a screen behind them) instead
of anything tied to the lead story's actual specifics. Root cause: the prior
prompt only asked for abstract categories (subject, setting, mood) and never
asked the model to find something concrete in the story first - which is
exactly the condition under which a text-to-image model reaches for stock-
photo cliches. The rewrite forces a concrete-detail search before
composition and bans the observed clichés by name. Also, per explicit
human-operator decisions (2026-09-16): company logos are disallowed
outright, full stop - AI-drawn logos are known to render inaccurately, and
building a real-logo-asset pipeline (to composite genuine logos instead of
generating them) was judged not worth the time investment right now.
Financial iconography is allowed for money-related stories, but must not
default to the US dollar sign - the show's stories are not all
US-market-specific, and hardcoding $ would be an unwarranted assumption.
"""

import json

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"image_prompt": {"type": "string"}},
    "required": ["image_prompt"],
    "additionalProperties": False,
}


def build_system_prompt(show_name):
    return (
        f'You write a single text-to-image generation prompt for "{show_name}", a '
        "daily audio newscast, based on that day's already-finished script. You are "
        "not writing or editing the episode itself - only describing one image for "
        "its lead story.\n\n"
        "Rules:\n"
        "- Base the image entirely on the lead story - the first substantive story "
        "covered in the script, right after any opening preview line. Ignore every "
        "other story in the episode for purposes of this image; do not attempt to "
        "represent or synthesize the whole episode.\n"
        "- Before describing anything, find ONE specific, concrete, filmable detail "
        "that is actually present in the lead story - a named technology, object, "
        "place, document, or action - and build the entire image around that one "
        "detail. Illustrate the one real, specific thing happening in the story, not "
        "the general category or topic it belongs to.\n"
        "- Purely visual and compositional: subject, setting, mood, palette, and "
        "style, as if briefing a photo/illustration editor for a news thumbnail. Let "
        "the lead story's own actual nature dictate the mood - do not impose an "
        "artificial tone. Never default to generic stock-photo scenes - anonymous "
        "people shaking hands, a group seated around a conference table, a vague "
        "chart or dashboard glowing on a screen behind them - unless the story is "
        "literally, specifically about that exact moment.\n"
        "- Prefer a photorealistic style wherever the concrete detail you found "
        "supports it (a real-world scene, object, setting, or product). Fall back to "
        "a stylized or illustrative treatment only when that detail is genuinely "
        "abstract with no sensible photorealistic depiction - but a stylized image "
        "still has to visualize that same specific detail as a real symbol or "
        "metaphor, not fall back to generic iconography either.\n"
        "- Do not depict real, identifiable people (public figures or specific "
        "individuals) - describe generic, stylized figures instead, and only include "
        "a person at all when one is genuinely part of the concrete detail you found "
        "(e.g. a student holding a tablet, a technician at a server rack) - never as "
        "an anonymous professional populating a meeting or handshake scene.\n"
        "- If the lead story is genuinely about money - funding, valuation, revenue, "
        "a financial deal - general financial iconography is welcome: a currency "
        "symbol, a rising or falling arrow, a stock ticker strip, coins or "
        "banknotes. Infer whichever currency actually fits the story's real context "
        "(the company's home market, a currency the script itself mentions); do not "
        "default to the US dollar sign as a generic stand-in for \"money\" - this "
        "show's stories are not all US-market-specific.\n"
        "- Do not include any company logo, brand mark, readable text, or numerals - "
        "text-to-image models cannot reproduce real logos accurately, and this "
        "show's own branding is composited on top afterward regardless.\n"
        "- One paragraph, no preamble, no notes about your process."
    )


def build_user_message(episode_date, final_script):
    return f"Episode date: {episode_date}\n\nFinal script:\n\n{final_script}"


def generate_image_prompt_for_episode(anthropic_generate, show_name, episode_date, final_script):
    text = anthropic_generate(
        system=build_system_prompt(show_name),
        user_content=build_user_message(episode_date, final_script),
        tools=[],
        response_schema=RESPONSE_SCHEMA,
    )
    return json.loads(text)["image_prompt"]
