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

Tightened 2026-09-17 after reviewing the first real episode generated under
the rewritten prompt (live on netgain.news): the concrete-detail fix worked
- the image showed a tablet with an AI-tutoring chat interface, a genuine
match for the lead story's "AI tutoring" detail - but the word "BILLION"
rendered as garbled text on a background whiteboard, next to a financial
growth-chart motif, for a story about a "$400 million" pledge. The general
no-readable-text rule apparently lost to the newer financial-iconography
rule sitting right next to it, which permitted graphical money symbols but
never explicitly excluded spelling the amount out as a word or numeral -
tightened to close that gap directly at the point of conflict, rather than
trusting the general rule to win on its own.

Revised 2026-10-02 after the three most recent graphics (including a story
led by Google and one led by Frontline Education) were all generic computer
monitors in generic classroom/office settings. Human-operator decisions:
the 2026-09-16 outright logo ban is reversed - real logos are now requested,
large and prominent, whenever the organization's official logo is unambiguous
from its prevalence on the internet; no approved-logo whitelist will be
maintained, so the model itself judges ambiguity and omits the logo when
unsure. The 2026-09-29 "a generic, unbranded version of the same kind of
setting is fine" allowance was removed (it licensed exactly the generic
fallbacks), and screens are barred as the default subject. Previous
episodes' images are deliberately NOT fed back to the model, and no
code-rendered company-name tag is added. The duotone treatment is retained.

Same day, after previewing it on the 10/1 Google story: the model built a
classroom scene and relegated a loosely drawn Google-colored star to a
glowing corner detail (and the duotone then erased its colors). Revised so
a recognizable-logo story yields a logo-ONLY image - the logo alone, large,
centered, flat, on a plain white or near-black background - and so every
image is high-contrast by brightness, since the duotone discards hue.

Guard added the same day (find_prompt_problems): generated prompts are
validated and regenerated, up to MAX_PROMPT_ATTEMPTS, because about a third
of them ended with stray model output appended inside the JSON string.

Later the same day, after seeing the Google logo rendered on a light
background beside seven dark, subdued graphics: logo-only images must always
be on a solid near-black background, never white or light.
"""

import json
import logging
import re

logger = logging.getLogger("net_gain.image_prompt")

# Total tries (first call plus retries) before giving up. The glitch this
# guards against is intermittent, so a retry almost always clears it.
MAX_PROMPT_ATTEMPTS = 5
MIN_PROMPT_CHARS = 40
MAX_PROMPT_CHARS = 3000

# Latin text (including accents) and general punctuation/currency symbols are
# normal in an image prompt; any other script (Korean, Chinese, Cyrillic...)
# is the model's own output going wrong, not a description of a picture.
_ALLOWED_CHARS = re.compile(r"[\u0000-\u024f\u2000-\u20cf]")


class ImagePromptError(RuntimeError):
    pass


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
        "- FIRST, decide whether this is a LOGO-ONLY IMAGE. When the lead story is about a specific, named company "
        "or organization and its official logo is unambiguous - the one mark that "
        "overwhelmingly comes to mind for that name, from its sheer prevalence across "
        "the internet (e.g. Google, Microsoft, Apple, Amazon, Meta, OpenAI) - the "
        "image IS that logo: the organization's primary, best-known logo (its main "
        "wordmark or symbol), flat, front-on and centered, filling most of the frame, "
        "on a plain solid near-black background with nothing else in the image - no scene, no "
        "people, no devices, no props, no effects, no glow. Describe it as the real, "
        "official logo, reproduced exactly - its real shapes, proportions and "
        "wordmark - never an invented, stylized, simplified or approximate version, "
        "and do not describe it in your own words beyond naming it (a description "
        "invites a derivative). Always place the logo on a solid near-black "
        "background - never on white or any light background, whatever the logo's "
        "own colors. This show's graphics are all dark and subdued, and a light "
        "logo card would clash with them. "
        "When the story is about a product, feature or service made by a famous "
        "organization (Gemini or Classroom inside Google, Copilot inside Microsoft, "
        "iPad at Apple), use the logo of the famous parent organization, not the "
        "product's - the parent's mark is the unambiguous one. Use a product's own "
        "logo only when the product is itself the one famous mark (ChatGPT, YouTube, "
        "Zoom). Where the correct logo is not unambiguous - a lesser-known company, a name "
        "shared by several organizations, a recent rebrand you are unsure of, a "
        "subsidiary versus its parent - use no logo at all rather than risk the wrong "
        "one, and build an ordinary image around the story's concrete detail "
        "instead. Never put a logo on a company other than the one it belongs to. A "
        "logo-only image overrides every rule below about scenes, people and "
        "concrete details; only the high-contrast rule still applies to it.\n"
        "- If it is not a logo-only story, then before describing anything, find ONE "
        "specific, concrete, filmable detail "
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
        "- The same rule applies to real, specific, named places (a particular "
        "school district's actual building, a named company's actual headquarters, "
        "a specific city street): never render it photorealistically as though it "
        "were genuine documentary photography of that real place - this risks "
        "reading as an authentic photo of something that never happened there. "
        "Either use an explicitly stylized/illustrative treatment of the real "
        "place, or pick a different concrete detail from the story to build the "
        "image around. Do not substitute an anonymous, generic version of the "
        "setting (a generic classroom, a generic office) - that is the same "
        "stock-photo failure by another route.\n"
        "- Do not make a computer monitor, laptop or tablet screen the default "
        "subject. A screen is acceptable only when the story is specifically about "
        "what appears on one; otherwise show the real-world consequence, object, "
        "place or action the story is about.\n"
        "- If the lead story is genuinely about money - funding, valuation, revenue, "
        "a financial deal - general financial iconography is welcome: a currency "
        "symbol, a rising or falling arrow, a stock ticker strip, coins or "
        "banknotes. Infer whichever currency actually fits the story's real context "
        "(the company's home market, a currency the script itself mentions); do not "
        "default to the US dollar sign as a generic stand-in for \"money\" - this "
        "show's stories are not all US-market-specific. This is a graphical symbol "
        "only - never spell out the actual amount as a word or numeral (not \"$400 "
        "million\", not \"BILLION\", not any digit) anywhere in the image, including "
        "as background signage, on-screen text, or a whiteboard/poster detail - the "
        "no-readable-text rule below still fully applies to financial imagery too.\n"
        "- HIGH CONTRAST ONLY. The finished image is converted to a two-tone "
        "monochrome, so it must read by brightness alone: one clear, bright, "
        "well-lit subject against a clearly darker background (or a dark subject "
        "against a clearly lighter one), a full tonal range from near-black to "
        "near-white, strong directional lighting, and a simple, uncluttered "
        "composition. Never dark-on-dark, pale-on-pale, low-key moody lighting, "
        "murky shadows, fog, haze, or subjects distinguished only by hue. This "
        "takes priority over any mood the story might suggest.\n"
        "- Apart from a logo's own wordmark in a logo-only image, include no "
        "readable text or numerals anywhere in the image - this show's own "
        "branding is composited on top afterward regardless.\n"
        "- One paragraph, no preamble, no notes about your process."
    )


def build_user_message(episode_date, final_script):
    return f"Episode date: {episode_date}\n\nFinal script:\n\n{final_script}"


def find_prompt_problems(prompt):
    """
    Reasons a generated prompt is not a clean one-paragraph picture
    description, or [] if it is. Added 2026-10-02 after a live scan: roughly a
    third of generated prompts ended with the model's own stray output
    appended inside the JSON string - things like `no logos.\u201d}  -- 1 valid
    JSON object only per instructions, correcting format below.  {` or a
    run of unrelated Korean text. The image model mostly ignored it, but
    nothing should be sending that to an image model. (The same scan found
    none in the stored metadata fields, which are what gets published.)
    """
    problems = []
    text = prompt if isinstance(prompt, str) else ""
    if len(text.strip()) < MIN_PROMPT_CHARS:
        problems.append("empty or too short")
    if len(text) > MAX_PROMPT_CHARS:
        problems.append("too long")
    if "{" in text or "}" in text:
        problems.append("contains braces")
    if "`" in text:
        problems.append("contains a backtick")
    if re.search(r"json", text, re.IGNORECASE):
        problems.append("mentions JSON")
    if any(not _ALLOWED_CHARS.match(ch) for ch in text):
        problems.append("contains characters outside Latin text")
    return problems


def generate_image_prompt_for_episode(anthropic_generate, show_name, episode_date, final_script):
    last_problems = []
    for attempt in range(1, MAX_PROMPT_ATTEMPTS + 1):
        text = anthropic_generate(
            system=build_system_prompt(show_name),
            user_content=build_user_message(episode_date, final_script),
            tools=[],
            response_schema=RESPONSE_SCHEMA,
        )
        try:
            prompt = json.loads(text)["image_prompt"]
        except (ValueError, KeyError, TypeError) as exc:
            last_problems = [f"response was not the expected JSON ({exc})"]
            prompt = None
        else:
            last_problems = find_prompt_problems(prompt)
            if not last_problems:
                return prompt

        logger.warning(
            "Image prompt rejected (attempt %d of %d): %s | text: %.200r",
            attempt, MAX_PROMPT_ATTEMPTS, "; ".join(last_problems), prompt if prompt is not None else text,
        )

    # Failing loudly sends the episode down the existing fallback-image path
    # (degraded, with this message as the note) rather than rendering from a
    # prompt known to be corrupted.
    raise ImagePromptError(
        f"No clean image prompt after {MAX_PROMPT_ATTEMPTS} attempts: {'; '.join(last_problems)}"
    )
