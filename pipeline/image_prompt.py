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

2026-10-05, after YouTube auto-labeled photorealistic episode art as
AI-generated despite an explicit "not synthetic" declaration (the operator
asserts the content is not AI to listeners): the "prefer photorealistic"
preference is REMOVED. The model now writes only a subject description and the
code appends one hardcoded house art style (ART_STYLE: handmade cut-paper
collage) for every show - shows differ only by duotone palette. Logo-only
images get the same style (logo cut from paper), not a flat exemption. The logo-only
background became mid-dark charcoal rather than near-black (a black ground
rendered the same colour as the overlay bar), and the high-contrast rule was
replaced by a tone rule since the art style now owns the background tone.
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
    "properties": {"image_prompt": {"type": "string"}, "logo_only": {"type": "boolean"}},
    "required": ["image_prompt", "logo_only"],
    "additionalProperties": False,
}

# The house art style, hardcoded for every show and vertical on purpose
# (operator decision 2026-10-05): shows differ only by their duotone palette,
# so every graphic is uniform. Appended in code to the subject description
# the model writes - never left to the model to restate. Applied to logo-only
# images too (operator decision 2026-10-05) so every graphic is uniform; the logo
# variant only changes the no-text sentence to permit the real logo.
#
# Why each part is there: "cut paper" (not photographic) because YouTube
# auto-labels photorealistic AI imagery as AI-generated, which the show's
# human-recorded, human-edited content must not carry; a dark charcoal
# ground (about a quarter brightness, never black) because the duotone maps black to the shadow color,
# which is also the overlay bar's color, so a black ground merges into the bar;
# and the safe-area sentence because the bottom fifth is covered by the
# overlay (best-effort only - minor intrusion there is accepted, no retry).
_ART_STYLE_CORE = (
    "Handmade cut-paper collage, photographed flat from directly above (orthographic "
    "view, no perspective). Every shape is visibly cut from paper: fibre grain and "
    "slight tooth on each sheet, crisp knife-cut edges showing a thin paper "
    "thickness, tiny hand-cut imperfections, the occasional lifted corner or curl. "
    "Three to five stacked layers with soft contact shadows only directly beneath "
    "each layer's edge, each layer a different paper tone from light to dark, with "
    "subtle colour variation within each sheet; lit softly from above and slightly "
    "left, like a craft table. Simplified iconic forms, one focal subject. The "
    "background layer is a single sheet of dark charcoal-grey paper filling the entire "
    "frame, about one-quarter brightness: clearly dark and noticeably darker than "
    "mid-grey, but not black; the subject is built from noticeably lighter paper tones "
    "so it stands out clearly from the ground. No gradients, glow, lens blur, depth of "
    "field, realistic lighting, reflections, 3D rendering, or smooth plastic or metal "
    "surfaces."
)
_ART_STYLE_NO_TEXT = " Absolutely no text, letters, numerals or logos."
_ART_STYLE_LOGO_TEXT = (
    " The only text or marks anywhere in the image are the organisation's real logo "
    "itself, reproduced exactly in its real shapes, proportions and wordmark but cut "
    "from paper; no other text, letters or numerals."
)
_ART_STYLE_SAFE_AREA = (
    " Composition: the whole picture is the visible area, so balance it. Center the "
    "subject, keep it compact (roughly the middle 40 percent of the width and no more "
    "than 70 percent of the height), and leave generous empty background paper on all "
    "four sides, because the picture is cropped differently for different formats."
)
ART_STYLE = _ART_STYLE_CORE + _ART_STYLE_NO_TEXT + _ART_STYLE_SAFE_AREA
ART_STYLE_LOGO = _ART_STYLE_CORE + _ART_STYLE_LOGO_TEXT + _ART_STYLE_SAFE_AREA


def compose_image_prompt(subject, logo_only):
    """The text actually sent to the image model: the model-written subject plus
    the house style. Logo-only images get the same style, with the one change
    that the logo itself is the permitted mark."""
    return f"{subject.strip()} {ART_STYLE_LOGO if logo_only else ART_STYLE}"


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
        "wordmark or symbol), flat, front-on and centered, large but compact - no wider "
        "than about 40 percent of the frame's width, so it is never clipped when the "
        "picture is cropped to a square - on its plain ground with nothing else in the image - no scene, no "
        "people, no devices, no props, no effects, no glow. Describe it as the real, "
        "official logo, reproduced exactly - its real shapes, proportions and "
        "wordmark - never an invented, stylized, simplified or approximate version, "
        "and do not describe it in your own words beyond naming it (a description "
        "invites a derivative). Say nothing about the background or the material: the "
        "house art style supplies a dark charcoal ground and renders the logo as cut "
        "paper. ""When the story is about a product, feature or service made by a famous "
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
        "concrete details, and the house art style is applied to it just as to any "
        "other image.\n"
        "- If it is not a logo-only story, then before describing anything, find ONE "
        "specific, concrete, depictable detail "
        "that is actually present in the lead story - a named technology, object, "
        "place, document, or action - and build the entire image around that one "
        "detail. Illustrate the one real, specific thing happening in the story, not "
        "the general category or topic it belongs to.\n"
        "- Describe ONLY the subject and its composition: what the one focal object "
        "or symbol is, what it is doing, and how it is arranged - an editorial "
        "illustrator's brief for one iconic, simplified, instantly readable image, not "
        "a detailed scene. Do NOT specify any art style, medium, material, lighting, "
        "camera, lens, color palette or mood: a fixed house art style (handmade "
        "cut-paper illustration) is added to your description automatically, and "
        "anything you say about style would fight it. Never default to generic "
        "stock-photo scenes - anonymous people shaking hands, a group seated around a "
        "conference table, a vague chart or dashboard glowing on a screen behind them "
        "- unless the story is literally, specifically about that exact moment.\n"
        "- Do not depict real, identifiable people (public figures or specific "
        "individuals) - describe faceless, simplified figures instead, and only include "
        "a person at all when one is genuinely part of the concrete detail you found "
        "(e.g. a student holding a tablet, a technician at a server rack) - never as "
        "an anonymous professional populating a meeting or handshake scene.\n"
        "- The same goes for real, specific, named places (a particular school "
        "district's building, a company's headquarters, a city street): do not try to "
        "reproduce the actual place - use a simple iconic building, or pick a "
        "different concrete detail from the story. Avoid generic stock settings (a "
        "generic classroom, a generic office); a specific object is better.\n"
        "- Avoid subjects that invite lettering. The image model renders any word it is "
        "told about - an \"off\" label beside a switch, a sign, a banner, a labeled "
        "button, a screen showing words, a calendar, a price tag - and the image must "
        "contain no text at all. Convey meaning through shape and arrangement (a "
        "crossed-out icon, a cracked padlock, an arrow) and never describe an on/off "
        "toggle or any labeled control; use an icon or symbol instead.\n"
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
        "- TONE. The finished image is converted to a two-colour palette, so the "
        "subject must stand apart from its background by brightness, not hue. The "
        "house art style already sets the background tone (mid-dark) - do not ask "
        "for a black or very light background, glow, fog or lighting effects.\n"
        "- Apart from a logo's own wordmark in a logo-only image, include no "
        "readable text or numerals anywhere in the image - this show's own "
        "branding is composited on top afterward regardless.\n"
        "- Return image_prompt as one paragraph with no preamble and no notes about your "
        "process, and set logo_only to true only if this is a logo-only image."
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
    """Returns the FINAL prompt for the image model: the model-written subject
    description with the house art style appended (or the logo-only description
    unchanged)."""
    last_problems = []
    for attempt in range(1, MAX_PROMPT_ATTEMPTS + 1):
        text = anthropic_generate(
            system=build_system_prompt(show_name),
            user_content=build_user_message(episode_date, final_script),
            tools=[],
            response_schema=RESPONSE_SCHEMA,
        )
        try:
            data = json.loads(text)
            prompt = data["image_prompt"]
            logo_only = bool(data.get("logo_only"))
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            last_problems = [f"response was not the expected JSON ({exc})"]
            prompt = None
        else:
            last_problems = find_prompt_problems(prompt)
            if not last_problems:
                return compose_image_prompt(prompt, logo_only)

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
