"""
Metadata generation (SPEC.md Section 6.1): one call produces Captivate
title/notes, AIOSEO fields, a website excerpt, and YouTube fields together -
generating all of them in one pass avoids a second, near-identical call per
platform.

No web search tool here (unlike script_generation.py) - this repackages an
already-written final script, it doesn't need to research anything new.
Runs synchronously, immediately before whichever publish attempt needs it
first (Captivate, website, or YouTube - see tick.py) - not on its own
schedule - per the Phase 4 amendment to Section 8.1: generation work is
deferred until the closest possible point to actual publication, to avoid
wasting it on episodes later aborted and replaced.

captivate_notes formatting (added 2026-09-14, after a live episode's notes
came back as one unbroken paragraph): real HTML, not plain-text paragraph
breaks - confirmed directly by the human operator that Captivate's own
show-notes editor is a styled-text (rich text) editor, not plain text.
"""

import json
import logging

from text_rules import K12_PROMPT_RULE, machine_safe

logger = logging.getLogger("net_gain.metadata_generation")

# Revised 2026-10-02 at the human operator's request: three-story titles of
# 65-90 characters were hard to read and got cut off in podcast apps (which
# truncate around 40-60) and in Google (~580px, about 60 characters). Set at
# 65 rather than 60 after the operator reviewed real two-story headlines
# (61 was fine; "up to 65 is okay"). Applies
# to the Captivate and website titles; the YouTube title keeps its own
# separate rules (under 100, aim under 70) and is deliberately unchanged.
TITLE_MAX_CHARS = 65
TITLE_FIELDS = ("captivate_title", "aioseo_title")
MAX_METADATA_ATTEMPTS = 4

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "captivate_title": {"type": "string"},
        "captivate_notes": {"type": "string"},
        "aioseo_title": {"type": "string"},
        "aioseo_description": {"type": "string"},
        "website_excerpt": {"type": "string"},
        "youtube_title": {"type": "string"},
        "youtube_description": {"type": "string"},
        "youtube_tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "captivate_title",
        "captivate_notes",
        "aioseo_title",
        "aioseo_description",
        "website_excerpt",
        "youtube_title",
        "youtube_description",
        "youtube_tags",
    ],
    "additionalProperties": False,
}


def build_system_prompt(show_name):
    return (
        f'You write publishing metadata for "{show_name}", a daily audio newscast, '
        "based on that day's already-finished script. You are not writing or "
        "editing the episode itself - only describing it for each platform. The "
        "script itself reflects this show's actual subject matter and tone; don't "
        "assume any particular genre beyond what the script itself shows you.\n\n"
        "STORY ORDER - NO EXCEPTIONS. The script tells its news stories in a fixed "
        "order that the human producer chose. Number them in the order the script tells "
        "them: story 1 is the first news story after the opening preview line, story 2 "
        "the next, and so on (ignore the opening preview line itself, the Net Gain "
        "Edtech Index / market segment, the sign-off, and the links section). In EVERY "
        "field below - titles, notes, excerpt, descriptions - story 1 is the lead, and "
        "any stories you mention must appear in that same order, earlier stories before "
        "later ones. Never promote or reorder a story because it seems more "
        "newsworthy, more searchable, or because it involves a public company or "
        "ticker symbol; that is the producer's call, not yours. A title names story 1 "
        "first and, only if it fits, ONE later story after it (in script order) - never "
        "a later story ahead of an earlier one, and never more than two stories.\n\n"
        "Field-specific rules:\n"
        f"- captivate_title: a concise, compelling episode title of at most {TITLE_MAX_CHARS} "
        "characters - a hard limit, so count them (podcast apps cut titles off around "
        "40-60 characters). Name at most TWO of the episode's stories: story 1 first "
        "and, only if it fits, one later story second - never try to fit all of the "
        "day's stories into the title. Put story 1's key name or term first, since cutoffs "
        "remove the end. Join two stories with a comma, a semicolon, or \"as\" where one "
        "reads naturally as the other's backdrop (e.g. \"X Hits Y as Z Pushes Back\") - "
        "whichever reads most clearly. Not just the show name repeated.\n"
        "- captivate_notes: written as real HTML - Captivate's own show-notes editor "
        "is a styled-text editor, not plain text. Keep this concise, not a second "
        "version of the script: 1-2 sentences per story, enough to say what happened "
        "and why it matters without retelling it in full. These notes are also reused "
        "as-is for the website's show notes, where they sit above the full transcript "
        "as the primary visible content of the page - they need to read as a quick, "
        "scannable summary a visitor will actually read, not a wall of text as long as "
        "the episode itself. Still write it to be rich in the specific names, terms, "
        "and phrases a search engine or an AI answer engine would match against - dense "
        "rather than long, not padded prose. One <p>...</p> per story - never one "
        "unbroken block of text. Never include the day's Net Gain Edtech Index/market-"
        "data recap here, even though the script itself covers it - show notes are for "
        "the day's actual news stories, not the market-index segment. After the story "
        "paragraphs, if the script below ends with its own \"story names and links\" section (and, if "
        "present, a \"stories considered but not used\" section), add a short "
        "'<p><strong>Stories &amp; links:</strong></p>' header, then reproduce that "
        "section with each URL wrapped in a real '<a href=\"...\" rel=\"nofollow\">' "
        "tag - the href must be the exact, unaltered URL from the script; never "
        "invent, paraphrase, or modify a URL. If the script has no such section, omit "
        "it rather than inventing one.\n"
        "- aioseo_title / aioseo_description: written for search engines and social "
        "link previews, not duplicates of the Captivate fields. aioseo_title becomes "
        f"the website page's own title and must be at most {TITLE_MAX_CHARS} characters "
        "(a hard limit; Google starts cutting titles off around 60, so shorter is better), naming at most TWO stories, "
        "story 1 first and then, only if it fits, one later story, joined the same ways as captivate_title - do not append the show name or any show/site "
        f"name suffix to it (e.g. no \"... - {show_name}\" or \"... | {show_name}\"), even "
        "though that's a common general SEO convention - the site's own branding already "
        "establishes the show name elsewhere on the page.\n"
        "- website_excerpt: a genuine excerpt, not a teaser at any length - under 160 "
        "characters (roughly a search-result meta-description length; WordPress does "
        "not truncate a manually-set excerpt on its own, so this field is the actual "
        "hard ceiling, not a suggestion), 1-2 sentences. Draw on whatever the script's "
        "own opening lines set up as that day's preview/summary (a natural newscast "
        "convention, not guaranteed to be a single clean sentence) - written to make "
        "someone want to click through and listen, not a compressed table of contents "
        "of every story.\n"
        "- youtube_title: under 100 characters (aim for under 70 so it isn't truncated "
        "in search results and suggested-video rows). Lead with story 1's real subject "
        "(the story order is fixed - see the story-order rule) and front-load its most "
        "search-relevant keyword or phrase, rather than a generic show-name-first "
        "framing. Written "
        "for genuine discovery, not clickbait.\n"
        "- youtube_description: the first ~125 characters are what's visible before "
        "truncation on YouTube, so lead with the most important, keyword-rich summary "
        "sentence. Keep the rest dense with the real topics, names, and terms a viewer "
        "or YouTube's own matching algorithm would search for - do not pad with "
        "generic filler to reach a target length; a shorter, denser description beats "
        "a longer, diluted one. Stay well under YouTube's 5000-character hard limit. "
        "Same as captivate_notes above: never include the day's Net Gain Edtech "
        "Index/market-data recap here.\n"
        "- youtube_tags: 5-15 relevant single words or short phrases, no '#' symbols, "
        "drawn from the episode's actual specific content (company, person, product, "
        "and topic names) rather than generic show-level tags repeated every episode - "
        "specific per-episode tags are what actually help one video surface in search "
        "and suggested videos.\n"
        "- Ticker symbols: whenever the episode discusses a publicly-traded company, "
        "include its stock ticker symbol (e.g. $AAPL) at least once in "
        "captivate_notes, aioseo_description, youtube_description, and as its own "
        "entry in youtube_tags - investors commonly search by ticker in a way plain "
        "company names don't capture. Omit this entirely when no public company is "
        "genuinely discussed; never invent or guess a ticker. A ticker symbol or "
        "company never changes the story order.\n\n"
        f"{K12_PROMPT_RULE} (youtube_tags are the one exception: write K-12 there with an ordinary hyphen.)"
    )


def build_user_message(episode_date, final_script):
    return f"Episode date: {episode_date}\n\nFinal script:\n\n{final_script}"


def overlong_titles(metadata):
    """{field: length} for each constrained title over TITLE_MAX_CHARS."""
    return {
        field: len(metadata.get(field) or "")
        for field in TITLE_FIELDS
        if len(metadata.get(field) or "") > TITLE_MAX_CHARS
    }


# --- story-order audit ---------------------------------------------------------
# Added 2026-10-06: a published episode led its title with the script's THIRD
# story (the one with a public-company ticker); the instructions had said to lead
# with the most search-relevant story. The operator's rule: every headline, note
# and abstract inherits the finalized script's story order, no exceptions. A rule
# in the prompt alone drifts, so every generated set of fields is read back
# against the script by an independent call, and a violation is regenerated or,
# if it cannot be fixed, fails the step loudly rather than publishing wrong.

AUDIT_FIELDS = (
    "captivate_title", "captivate_notes", "aioseo_title", "aioseo_description",
    "website_excerpt", "youtube_title", "youtube_description",
)
# Fields that must name story 1 (a title or abstract that skips the lead is wrong).
MUST_START_WITH_STORY_1 = ("captivate_title", "aioseo_title", "youtube_title")
# Titles that may name at most two stories: story 1 plus, optionally, one later story.
TWO_STORY_TITLES = ("captivate_title", "aioseo_title")

AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {"type": "array", "items": {"type": "string"}},
        "order": {
            "type": "object",
            "properties": {f: {"type": "array", "items": {"type": "integer"}} for f in AUDIT_FIELDS},
            "required": list(AUDIT_FIELDS),
            "additionalProperties": False,
        },
    },
    "required": ["stories", "order"],
    "additionalProperties": False,
}


class StoryOrderError(RuntimeError):
    pass


def build_audit_system_prompt():
    return (
        "You audit publishing metadata against the script it was written from. You do "
        "not write or fix anything.\n\n"
        "Step 1 - stories: read the script and list its news stories in the exact order "
        "the script tells them, as short labels (about 6 words each). Include only news "
        "stories. Exclude the opening preview line, the Net Gain Edtech Index / market "
        "segment, 'what to watch' items, the sign-off, and the show-notes links "
        "section. The first label is story 1.\n\n"
        "Step 2 - order: for each field in the metadata, list the numbers of the stories "
        "it mentions, in the order they appear in that field's text (reading it from "
        "start to finish). Use the story numbers from Step 1. Mention a story only if "
        "the field actually refers to it (by its subject, company or event). A field "
        "that mentions no story gets an empty list. If a field mentions the same story "
        "twice, list it twice. For captivate_notes, list the stories in the order its "
        "story paragraphs appear, ignoring the 'Stories & links' section at the end.\n\n"
        "Be literal and careful: your only job is to report the true order."
    )


def build_audit_user_message(final_script, metadata):
    fields = {f: metadata.get(f, "") for f in AUDIT_FIELDS}
    return f"Script:\n\n{final_script}\n\n---\n\nMetadata fields to audit (JSON):\n\n{json.dumps(fields, ensure_ascii=False, indent=1)}"


def audit_story_order(anthropic_generate, final_script, metadata):
    text = anthropic_generate(
        system=build_audit_system_prompt(),
        user_content=build_audit_user_message(final_script, metadata),
        tools=[],
        response_schema=AUDIT_SCHEMA,
    )
    return json.loads(text)


def find_order_violations(audit):
    """Human-readable violations of the story-order rule, or [] if there are none."""
    stories = audit.get("stories") or []
    order = audit.get("order") or {}
    problems = []
    for field in AUDIT_FIELDS:
        seq = order.get(field)
        if seq is None:
            problems.append(f"{field}: the audit returned nothing for it")
            continue
        if any((n < 1 or n > len(stories)) for n in seq):
            problems.append(f"{field}: refers to a story number outside the script's {len(stories)} stories")
            continue
        if any(b <= a for a, b in zip(seq, seq[1:])):
            problems.append(f"{field}: mentions stories in the order {seq}, which is not the script's order")
            continue
        if field in MUST_START_WITH_STORY_1 and (not seq or seq[0] != 1):
            problems.append(f"{field}: does not lead with story 1 (it mentions {seq})")
            continue
        if seq and seq[0] != 1:
            problems.append(f"{field}: skips the lead story (it mentions {seq})")
            continue
        if field in TWO_STORY_TITLES and len(seq) > 2:
            problems.append(f"{field}: names more than two stories ({seq})")
    return problems


def _retry_feedback(audit, problems):
    labels = "; ".join(f"{i}. {s}" for i, s in enumerate(audit.get("stories") or [], 1))
    return (
        "\n\nYOUR PREVIOUS ATTEMPT BROKE THE STORY-ORDER RULE. The script tells its stories in this "
        f"order: {labels}.\nProblems found:\n- " + "\n- ".join(problems) +
        "\nRewrite ALL fields so every one inherits that order exactly (story 1 is always the lead)."
    )


def _finalize(metadata):
    """YouTube tags are search keys, not read text: keep ordinary hyphens there (text_rules.machine_safe)."""
    metadata = dict(metadata)
    metadata["youtube_tags"] = [machine_safe(tag) for tag in metadata.get("youtube_tags") or []]
    return metadata


def generate_metadata_for_episode(anthropic_generate, show_name, episode_date, final_script):
    """
    Two independent guards, both regenerating on failure:
    - story order (never relaxed): every field must inherit the script's story order,
      checked by a separate audit call; if no attempt passes, StoryOrderError is raised
      so the step fails loudly instead of publishing a wrongly ordered headline.
    - title length: over-limit titles are regenerated; if no order-valid attempt is within
      the limit, each title field takes the SHORTEST value seen across the order-valid
      attempts (operator's choice, 2026-10-02) rather than failing the publish.
    """
    system_prompt = build_system_prompt(show_name)
    base_user_message = build_user_message(episode_date, final_script)

    valid_attempts = []   # order-correct attempts (possibly with over-limit titles)
    feedback = ""
    last_problems = []
    for attempt in range(1, MAX_METADATA_ATTEMPTS + 1):
        text = anthropic_generate(
            system=system_prompt,
            user_content=base_user_message + feedback,
            tools=[],
            response_schema=RESPONSE_SCHEMA,
        )
        metadata = json.loads(text)

        try:
            audit = audit_story_order(anthropic_generate, final_script, metadata)
            problems = find_order_violations(audit)
        except (ValueError, KeyError, TypeError) as exc:
            audit, problems = {"stories": []}, [f"the story-order audit could not be read ({exc})"]

        if problems:
            last_problems = problems
            logger.warning("Story-order violation (attempt %d of %d): %s", attempt, MAX_METADATA_ATTEMPTS, problems)
            feedback = _retry_feedback(audit, problems)
            continue

        over = overlong_titles(metadata)
        if not over:
            return _finalize(metadata)
        valid_attempts.append(metadata)
        logger.warning("Title over %d characters (attempt %d of %d): %s", TITLE_MAX_CHARS, attempt, MAX_METADATA_ATTEMPTS, over)
        feedback = ""

    if not valid_attempts:
        raise StoryOrderError(
            f"No metadata attempt kept the script's story order after {MAX_METADATA_ATTEMPTS} tries: "
            + "; ".join(last_problems)
        )

    result = dict(valid_attempts[-1])
    for field in TITLE_FIELDS:
        result[field] = min((a.get(field) or "" for a in valid_attempts), key=len)
    logger.warning(
        "No attempt had every title within %d characters; using the shortest of each: %s",
        TITLE_MAX_CHARS, {f: len(result[f]) for f in TITLE_FIELDS},
    )
    return _finalize(result)
