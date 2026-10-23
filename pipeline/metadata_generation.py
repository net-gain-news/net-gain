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
import re
import logging

from text_rules import K12_PROMPT_RULE, machine_safe
from title_width import (
    DESC_CHARS_TARGET_MAX,
    DESC_CHARS_TARGET_MIN,
    TITLE_PX_TARGET_MAX,
    TITLE_PX_TARGET_MIN,
    search_field_distance,
    search_field_problems,
)

logger = logging.getLogger("net_gain.metadata_generation")

# Revised 2026-10-02 at the human operator's request: three-story titles of
# 65-90 characters were hard to read and got cut off in podcast apps (which
# truncate around 40-60) and in Google (~580px, about 60 characters). Set at
# 65 rather than 60 after the operator reviewed real two-story headlines
# (61 was fine; "up to 65 is okay"). Applies
# to the Captivate and website titles; the YouTube title keeps its own
# separate rules (under 100, aim under 70) and is deliberately unchanged.
TITLE_MAX_CHARS = 65
TITLE_FIELDS = ("captivate_title",)  # character-limited; aioseo_title is limited by rendered width (title_width.py)
SEARCH_RESULT_FIELDS = ("aioseo_title", "aioseo_description")
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
        "HEADLINES REPORT THE NEWS, NOT THE TOPIC. This is a daily newscast: a headline must tell the "
        "listener what HAPPENED in story 1 TODAY - the new development, the new fact, the outcome - not just "
        "name the subject. Many stories continue ones the audience already knows (a breach reported weeks "
        "ago, a lawsuit, a bankruptcy); for those the new development is the whole point of the story and "
        "the headline MUST carry it. The script itself usually tells you what is new: look for \"new "
        "reporting\", \"today\", \"latest\", \"now\", \"newly\", \"confirmed\", \"found\", \"filed\". A bare "
        "label such as \"ETS Student Data Breach\" or \"Character.AI Bankruptcy\" is NOT a headline: it could "
        "have run unchanged weeks ago and reads as old news. State the development in plain, active "
        "language instead, e.g. \"ETS Breach Traced to a Single Stolen Login\" or \"Wisconsin Joins 38 States "
        "Fighting Character.AI Sale\". Use the full length available to tell ONE story well, including its "
        "new angle - do not shrink it to a label to make room for a second story. Add a second story only "
        "when it fits without cutting the first story's development; a headline that fully reports story 1 "
        "and names nothing else is better than one that names two stories as bare labels. Searchability "
        "still matters - keep the real names (company, agency, place) in the headline - but it never "
        "outranks stating what is new. When the user message lists \"Headlines already published\", that is "
        "what the audience has already been told: use it to recognise follow-ups and make sure today's "
        "headline adds the new information instead of repeating an earlier headline.\n\n"
        "Field-specific rules:\n"
        f"- captivate_title: a concise, compelling episode title of at most {TITLE_MAX_CHARS} "
        "characters - a hard limit, so count them (podcast apps cut titles off around "
        "40-60 characters). Tell story 1's new development (see HEADLINES REPORT THE NEWS); "
        "name at most TWO of the episode's stories - a second one, in script order, only if it "
        "fits without cutting story 1's development - never try to fit all of the "
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
        "unbroken block of text. Plain text inside the story paragraphs: NO bold, italics, "
        "underline or any other emphasis - names of districts, companies, people and places are "
        "ordinary text, however important they are. The only emphasised text in the whole field is "
        "the 'Stories &amp; links:' header described below. Never include the day's Net Gain Edtech Index/market-"
        "data recap here, even though the script itself covers it - show notes are for "
        "the day's actual news stories, not the market-index segment. After the story "
        "paragraphs, if the script below ends with its own \"story names and links\" section (and, if "
        "present, a \"stories considered but not used\" section), add a short "
        "'<p><strong>Stories &amp; links:</strong></p>' header, then reproduce that "
        "section with each URL wrapped in a real '<a href=\"...\" rel=\"nofollow\">' "
        "tag - the href must be the exact, unaltered URL from the script; never "
        "invent, paraphrase, or modify a URL. If the script has no such section, omit "
        "it rather than inventing one.\n"
        "- aioseo_title: written for search engines and social link previews, not a duplicate of the "
        "Captivate title. It becomes the website page's own title and the search-result title, and "
        "AIOSEO's page analysis scores it by RENDERED WIDTH, not character count: it must measure between "
        f"{TITLE_PX_TARGET_MIN} and {TITLE_PX_TARGET_MAX} pixels at 20px Arial (roughly 46-58 characters of "
        "ordinary mixed-case text; wide letters like W and M and capitals cost more, narrow ones like i, l, t "
        "and punctuation cost less). Aim for the middle of that range. It is checked after you write it and "
        "rewritten if it is outside. Tell story 1's new development (see HEADLINES REPORT THE NEWS), keeping "
        "its real searchable names in it; name a second story (at most TWO in all, in script order) only if "
        "it fits without cutting that development. Do not append the show name or any show/site name suffix (e.g. no "
        f"\"... - {show_name}\" or \"... | {show_name}\"): the site's own branding establishes it elsewhere on "
        "the page.\n"
        "- aioseo_description: the page's meta description and the text under the title in search results. "
        f"It must be between {DESC_CHARS_TARGET_MIN} and {DESC_CHARS_TARGET_MAX} CHARACTERS including spaces "
        "(AIOSEO scores 121-160 as good; Google cuts off around 155-160) - count them, and aim for 140-155. "
        "It is checked after you write it and rewritten if it is outside. Open with what happened in story 1 today "
        "(its new development), then plain, keyword-rich sentences "
        "naming the real companies, places, products, agencies and events in the stories, in script order; "
        "no ticker symbols unless the rule below allows one.\n"
        "- website_excerpt: a genuine excerpt, not a teaser at any length - under 160 "
        "characters (roughly a search-result meta-description length; WordPress does "
        "not truncate a manually-set excerpt on its own, so this field is the actual "
        "hard ceiling, not a suggestion), 1-2 sentences. Open with what is new in story 1 today. Draw on whatever the script's "
        "own opening lines set up as that day's preview/summary (a natural newscast "
        "convention, not guaranteed to be a single clean sentence) - written to make "
        "someone want to click through and listen, not a compressed table of contents "
        "of every story.\n"
        "- youtube_title: under 100 characters (aim for under 70 so it isn't truncated "
        "in search results and suggested-video rows). Lead with story 1 and what happened in it "
        "(the story order is fixed - see the story-order rule; see HEADLINES REPORT THE NEWS), "
        "front-loading its real names and the key fact, rather than a generic show-name-first "
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
        "captivate_notes, youtube_description, and as its own "
        "entry in youtube_tags - investors commonly search by ticker in a way plain "
        "company names don't capture. Omit this entirely when no public company is "
        "genuinely discussed; never invent or guess a ticker. A ticker symbol or "
        "company never changes the story order. In aioseo_title never use a ticker, and in "
        "aioseo_description use at most ONE, and only when a public company's stock or deal is "
        "itself one of the lead stories - never a list of tickers, never a ticker tacked on as an aside "
        "(\"Plus market moves for $X and $Y\"); a description reads as a sentence about the news, "
        "not a string of keywords.\n\n"
        f"{K12_PROMPT_RULE} (youtube_tags, aioseo_title and aioseo_description are the exceptions: search-result fields, "
        "so write K-12 there with an ordinary hyphen.)"
    )


def build_user_message(episode_date, final_script, recent_titles=None):
    recent = ""
    if recent_titles:
        lines = "\n".join(f"- {t}" for t in recent_titles)
        recent = (
            "Headlines already published in the last two weeks (context only - the audience has been told "
            f"these; do not copy them):\n{lines}\n\n"
        )
    return f"Episode date: {episode_date}\n\n{recent}Final script:\n\n{final_script}"


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

# Titles that must state story 1's NEW development, not just name its subject (operator rule, 2026-10-19).
DEVELOPMENT_FIELDS = ("captivate_title", "aioseo_title", "youtube_title")

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
        "lead_development": {"type": "string"},
        "states_development": {
            "type": "object",
            "properties": {f: {"type": "boolean"} for f in DEVELOPMENT_FIELDS},
            "required": list(DEVELOPMENT_FIELDS),
            "additionalProperties": False,
        },
    },
    "required": ["stories", "order", "lead_development", "states_development"],
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
        "Step 3 - development: in at most 15 words, say what is NEW in story 1 today according to the "
        "script's own wording (the latest development, finding, outcome or step - not the background "
        "subject), as lead_development. Then, for each of captivate_title, aioseo_title and youtube_title, "
        "answer states_development: true only if the title tells the listener that new development (or its "
        "clear equivalent); false if it merely names the subject or the ongoing story. Test: a title that "
        "could have run unchanged weeks ago (for example a bare label such as \"X Data Breach\") is false.\n\n"
        "Be literal and careful: your only job is to report the true order and the true state of the titles."
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


def find_development_problems(audit):
    """Titles the audit says only name the subject instead of stating story 1's new development ([] when none).
    A missing answer counts as a pass, so an audit that predates this check never blocks a publish."""
    verdicts = audit.get("states_development") or {}
    return [f for f in DEVELOPMENT_FIELDS if verdicts.get(f) is False]


def _development_feedback(fields, audit):
    new = (audit.get("lead_development") or "").strip()
    return (
        "\n\nYOUR PREVIOUS ATTEMPT NAMED THE TOPIC BUT NOT THE NEWS. These titles read like old news because they "
        f"only name the subject: {', '.join(fields)}. What is new in story 1 today: {new or '(see the script)'}. "
        "Rewrite ALL fields so every title tells the listener that new development in plain, active language "
        "(keep the real names), using the full length available for that one story."
    )


def _retry_feedback(audit, problems):
    labels = "; ".join(f"{i}. {s}" for i, s in enumerate(audit.get("stories") or [], 1))
    return (
        "\n\nYOUR PREVIOUS ATTEMPT BROKE THE STORY-ORDER RULE. The script tells its stories in this "
        f"order: {labels}.\nProblems found:\n- " + "\n- ".join(problems) +
        "\nRewrite ALL fields so every one inherits that order exactly (story 1 is always the lead)."
    )


def _length_feedback(over, search_problems):
    lines = [f"captivate_title is {n} characters; it must be at most {TITLE_MAX_CHARS}" for field, n in over.items()]
    lines += [f"{field} {sentence}" for field, sentence in search_problems.items()]
    return (
        "\n\nYOUR PREVIOUS ATTEMPT BROKE A LENGTH RULE (measured after you wrote it):\n- " + "\n- ".join(lines)
        + "\nRewrite ALL fields, fixing these and keeping everything else, including the story order, exactly as "
        "the rules require."
    )


_EMPHASIS_TAG = re.compile(r"</?(?:strong|b|em|i|u|mark)\b[^>]*>", re.I)
_NOTES_HEADER = re.compile(r"<p>\s*<strong>\s*Stories\s*(?:&amp;|&)\s*links:?\s*</strong>\s*</p>", re.I)


def strip_stray_emphasis(notes):
    """
    Show notes carry exactly one emphasised thing, the "Stories & links:" header. Anything else the model bolded
    or italicised (2026-10-23: the first story's district name, in the Captivate notes and on the website) is
    removed, whatever the prompt said. Returns (cleaned notes, whether anything was removed).
    """
    if not isinstance(notes, str) or not notes:
        return notes, False
    marker = "\x00STORIES-HEADER\x00"
    headers = _NOTES_HEADER.findall(notes)
    protected = _NOTES_HEADER.sub(marker, notes)
    cleaned = _EMPHASIS_TAG.sub("", protected)
    for header in headers:
        cleaned = cleaned.replace(marker, header, 1)
    return cleaned, cleaned != notes


def _finalize(metadata):
    """YouTube tags and the AIOSEO title/description are search keys or search-result text, where an
    ordinary hyphen matches what people type: keep ordinary hyphens there (text_rules.machine_safe)."""
    metadata = dict(metadata)
    notes, changed = strip_stray_emphasis(metadata.get("captivate_notes"))
    if changed:
        logger.warning("Removed stray bold/italic from the show notes (only the Stories & links header may be emphasised).")
        metadata["captivate_notes"] = notes
    for key in SEARCH_RESULT_FIELDS:
        if isinstance(metadata.get(key), str):
            metadata[key] = machine_safe(metadata[key])
    metadata["youtube_tags"] = [machine_safe(tag) for tag in metadata.get("youtube_tags") or []]
    return metadata


def generate_metadata_for_episode(anthropic_generate, show_name, episode_date, final_script, recent_titles=None):
    """
    Three independent guards, each regenerating on failure:
    - story order (never relaxed): every field must inherit the script's story order,
      checked by a separate audit call; if no attempt passes, StoryOrderError is raised
      so the step fails loudly instead of publishing a wrongly ordered headline.
    - the news, not the topic (2026-10-19): the same audit call says what is NEW in story 1 today and whether
      each title states it. A title that only names the subject ("ETS Student Data Breach") reads as old news
      when the story is a follow-up, so it is regenerated with the new development spelled out. If no attempt
      gets every title right, the attempt with the fewest topic-only titles is used (a weaker headline is
      published with a logged warning; it never blocks the episode).
    - field length: an over-limit Captivate title, or an AIOSEO title/description outside AIOSEO's
      green window (title width in pixels, description in characters - see title_width.py), is regenerated
      with the measured problem fed back; if no attempt is within the limits, the Captivate title takes the
      SHORTEST value seen (operator's choice, 2026-10-02) and the AIOSEO fields the values closest to their
      windows, rather than failing the publish.
    recent_titles: headlines already published in the last two weeks, shown to the model as context so it can
    recognise follow-ups.
    """
    system_prompt = build_system_prompt(show_name)
    base_user_message = build_user_message(episode_date, final_script, recent_titles)

    valid_attempts = []   # (metadata, titles-that-only-name-the-topic) for order-correct attempts
    feedback = ""
    last_problems = []
    for attempt in range(1, MAX_METADATA_ATTEMPTS + 1):
        text = anthropic_generate(
            system=system_prompt,
            user_content=base_user_message + feedback,
            tools=[],
            response_schema=RESPONSE_SCHEMA,
        )
        metadata = _finalize(json.loads(text))   # measure the search-result text as it will be published

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

        topic_only = find_development_problems(audit)
        over = overlong_titles(metadata)
        search_problems = search_field_problems(metadata)
        if not over and not search_problems and not topic_only:
            return _finalize(metadata)
        valid_attempts.append((metadata, topic_only))
        logger.warning(
            "Metadata not ready (attempt %d of %d): titles that only name the topic: %s (lead development: %r); "
            "titles over %d characters: %s; AIOSEO fields: %s",
            attempt, MAX_METADATA_ATTEMPTS, topic_only, audit.get("lead_development"), TITLE_MAX_CHARS, over, search_problems,
        )
        feedback = ""
        if topic_only:
            feedback += _development_feedback(topic_only, audit)
        if over or search_problems:
            feedback += _length_feedback(over, search_problems)

    if not valid_attempts:
        raise StoryOrderError(
            f"No metadata attempt kept the script's story order after {MAX_METADATA_ATTEMPTS} tries: "
            + "; ".join(last_problems)
        )

    fewest = min(len(topic_only) for _, topic_only in valid_attempts)
    candidates = [m for m, topic_only in valid_attempts if len(topic_only) == fewest]
    result = dict(candidates[-1])
    for field in TITLE_FIELDS:
        result[field] = min((a.get(field) or "" for a in candidates), key=len)
    closest = min(candidates, key=search_field_distance)
    for field in ("aioseo_title", "aioseo_description"):
        result[field] = closest.get(field) or ""
    logger.warning(
        "No attempt had every field right; using the shortest Captivate title (%s) and the AIOSEO fields closest "
        "to their windows (%s); %d title(s) still only name the topic.",
        {f: len(result[f]) for f in TITLE_FIELDS}, search_field_problems(result), fewest,
    )
    return _finalize(result)
