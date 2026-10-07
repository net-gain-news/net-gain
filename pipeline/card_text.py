"""
Text for the code-built episode cards: one plain-language headline for the lead story
and one topic word (or two) per story, written from the finalized script.

Story order is the operator's absolute rule (2026-10-06): everything generated from an
episode inherits the script's story order. Here that means the headline is about
story 1, and the topic words are for stories 1, 2, 3 in that order. Like the metadata
step (metadata_generation.py), a rule in the prompt is not trusted by itself: a
separate audit call reads the generated text back against the script and reports which
story each piece is about, and any mismatch is regenerated, then rejected.

The headline is written from the story itself - never copied from the show-notes link
captions, which are not reliable headlines (operator, 2026-10-06).
"""

import json
import logging

from text_rules import K12_PROMPT_RULE

from metadata_generation import StoryOrderError

logger = logging.getLogger("net_gain.card_text")

MAX_ATTEMPTS = 3
HEADLINE_MIN_CHARS = 12
HEADLINE_MAX_CHARS = 70
WORD_MAX_CHARS = 16
WORD_MAX_WORDS = 2
MAX_STORIES = 3

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "words": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"story": {"type": "integer"}, "word": {"type": "string"}},
                "required": ["story", "word"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["headline", "words"],
    "additionalProperties": False,
}

AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {"type": "array", "items": {"type": "string"}},
        "headline_story": {"type": "integer"},
        "word_stories": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["stories", "headline_story", "word_stories"],
    "additionalProperties": False,
}


def build_system_prompt(show_name):
    return (
        f'You write the text printed on the episode graphic for "{show_name}", a daily audio '
        "newscast, from that day's finished script. You are not editing the episode.\n\n"
        "STORY ORDER - NO EXCEPTIONS. The script tells its news stories in a fixed order the "
        "human producer chose. Number them in the order the script tells them: story 1 is the "
        "first news story after the opening preview line, story 2 the next, and so on (ignore the "
        "opening preview line, the market-index segment, the sign-off and the links section). "
        "Never promote or reorder a story for any reason.\n\n"
        "Produce:\n"
        f"- headline: one plain-language headline, at most {HEADLINE_MAX_CHARS} characters, about STORY 1 "
        "only. Write it from the story's own substance as told in the script - do NOT copy a caption "
        "from the links section, and do not mention other stories. Sentence case (capitalize only "
        "the first word and proper nouns), no trailing period, no quotation marks, no clickbait.\n"
        f"- words: one entry for each of the first {MAX_STORIES} stories (fewer if the script has fewer), "
        "in story order. Each is {\"story\": the story's number, \"word\": a topic label} where the label "
        f"is one or two words (at most {WORD_MAX_CHARS} characters in total) naming what that story is about, "
        "such as \"Cyberattack\", \"AI detectors\" or \"Acquisition\". Sentence case: capitalize only the first "
        "word and proper nouns or acronyms; never all capitals except an acronym of up to four letters. "
        "No punctuation. Name the topic, not the company.\n\n"
        + K12_PROMPT_RULE
    )


def build_user_message(episode_date, final_script):
    return f"Episode date: {episode_date}\n\nFinal script:\n\n{final_script}"


def shape_problems(text):
    """Cheap, deterministic checks of the generated text before any audit call."""
    problems = []
    headline = (text.get("headline") or "").strip()
    if not (HEADLINE_MIN_CHARS <= len(headline) <= HEADLINE_MAX_CHARS):
        problems.append(f"the headline must be {HEADLINE_MIN_CHARS}-{HEADLINE_MAX_CHARS} characters (it was {len(headline)})")
    if headline.endswith("."):
        problems.append("the headline must not end with a period")
    words = text.get("words") or []
    if not words:
        problems.append("there are no topic words")
    for item in words:
        word = (item.get("word") or "").strip()
        if not word or len(word) > WORD_MAX_CHARS or len(word.split()) > WORD_MAX_WORDS:
            problems.append(f"topic word {word!r} must be 1-{WORD_MAX_WORDS} words and at most {WORD_MAX_CHARS} characters")
        for part in word.split():
            if part.isupper() and len(part) > 4:
                problems.append(f"topic word {word!r} is in capitals; use sentence case")
    stories = [item.get("story") for item in words]
    if stories != list(range(1, len(stories) + 1)):
        problems.append(f"the topic words must be for stories 1, 2, 3... in order (they were for {stories})")
    if len(words) > MAX_STORIES:
        problems.append(f"at most {MAX_STORIES} topic words")
    return problems


def build_audit_system_prompt():
    return (
        "You audit text printed on an episode graphic against the script it was written from. You do not write "
        "or fix anything.\n\n"
        "Step 1 - stories: read the script and list its news stories in the exact order the script tells them, as "
        "short labels (about 6 words each). Include only news stories - exclude the opening preview line, the "
        "market-index segment, 'what to watch' items, the sign-off and the links section. The first label is story 1.\n\n"
        "Step 2 - for the headline, give the number of the single story it is about. Step 3 - for each topic word, in "
        "the order given, give the number of the story it is about. Be literal and careful: your only job is to report "
        "which story each piece of text is about."
    )


def build_audit_user_message(final_script, text):
    payload = {"headline": text.get("headline", ""), "words": [item.get("word", "") for item in text.get("words") or []]}
    return f"Script:\n\n{final_script}\n\n---\n\nGraphic text to audit (JSON):\n\n{json.dumps(payload, ensure_ascii=False, indent=1)}"


def audit_problems(audit, text):
    """Human-readable story-order violations, or [] if the text inherits the script's order."""
    problems = []
    stories = audit.get("stories") or []
    if audit.get("headline_story") != 1:
        problems.append(f"the headline is about story {audit.get('headline_story')}, but it must be about story 1")
    claimed = [item.get("story") for item in text.get("words") or []]
    seen = audit.get("word_stories") or []
    if seen != claimed:
        problems.append(f"the topic words are really about stories {seen}, not {claimed}")
    if any(n < 1 or n > len(stories) for n in seen):
        problems.append(f"a topic word refers to a story outside the script's {len(stories)} stories")
    return problems


def _retry_feedback(audit_stories, problems):
    labels = "; ".join(f"{i}. {s}" for i, s in enumerate(audit_stories or [], 1))
    prefix = f"The script tells its stories in this order: {labels}.\n" if labels else ""
    return (
        "\n\nYOUR PREVIOUS ATTEMPT BROKE A RULE.\n" + prefix + "Problems found:\n- " + "\n- ".join(problems) +
        "\nWrite the headline and topic words again, fixing every problem."
    )


def generate_card_text(anthropic_generate, show_name, episode_date, final_script):
    """
    Returns {"headline": str, "keywords": [str, ...]} with the keywords in script order.
    Raises StoryOrderError if no attempt passes both the shape checks and the story-order audit.
    """
    system_prompt = build_system_prompt(show_name)
    base_user = build_user_message(episode_date, final_script)
    feedback = ""
    last_problems = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        text = json.loads(anthropic_generate(system=system_prompt, user_content=base_user + feedback, tools=[], response_schema=RESPONSE_SCHEMA))
        problems = shape_problems(text)
        audit_stories = []
        if not problems:
            try:
                audit = json.loads(anthropic_generate(
                    system=build_audit_system_prompt(), user_content=build_audit_user_message(final_script, text),
                    tools=[], response_schema=AUDIT_SCHEMA))
                audit_stories = audit.get("stories") or []
                problems = audit_problems(audit, text)
            except (ValueError, KeyError, TypeError) as exc:
                problems = [f"the story-order audit could not be read ({exc})"]
        if not problems:
            return {
                "headline": text["headline"].strip(),
                "keywords": [item["word"].strip() for item in text["words"]],
            }
        last_problems = problems
        logger.warning("Card text rejected (attempt %d of %d): %s", attempt, MAX_ATTEMPTS, problems)
        feedback = _retry_feedback(audit_stories, problems)
    raise StoryOrderError(f"No card text attempt passed after {MAX_ATTEMPTS} tries: " + "; ".join(last_problems))
