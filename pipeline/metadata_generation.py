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
        "Field-specific rules:\n"
        "- captivate_title: a concise, compelling episode title (not just the show "
        "name repeated).\n"
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
        "link previews, not duplicates of the Captivate fields.\n"
        "- website_excerpt: a genuine excerpt, not a teaser at any length - under 160 "
        "characters (roughly a search-result meta-description length; WordPress does "
        "not truncate a manually-set excerpt on its own, so this field is the actual "
        "hard ceiling, not a suggestion), 1-2 sentences. Draw on whatever the script's "
        "own opening lines set up as that day's preview/summary (a natural newscast "
        "convention, not guaranteed to be a single clean sentence) - written to make "
        "someone want to click through and listen, not a compressed table of contents "
        "of every story.\n"
        "- youtube_title: under 100 characters (aim for under 70 so it isn't truncated "
        "in search results and suggested-video rows). Lead with the episode's single "
        "most search- and recommendation-relevant keyword or phrase - usually the lead "
        "story's real subject - rather than a generic show-name-first framing. Written "
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
        "genuinely discussed; never invent or guess a ticker."
    )


def build_user_message(episode_date, final_script):
    return f"Episode date: {episode_date}\n\nFinal script:\n\n{final_script}"


def generate_metadata_for_episode(anthropic_generate, show_name, episode_date, final_script):
    system_prompt = build_system_prompt(show_name)
    user_message = build_user_message(episode_date, final_script)

    text = anthropic_generate(
        system=system_prompt,
        user_content=user_message,
        tools=[],
        response_schema=RESPONSE_SCHEMA,
    )

    return json.loads(text)
