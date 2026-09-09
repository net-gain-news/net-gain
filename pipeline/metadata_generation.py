"""
Metadata generation (SPEC.md Section 6.1): one call produces Captivate
title/notes, AIOSEO fields, and YouTube fields together - only Captivate's
share is consumed until Phases 6 and 9 exist, but generating all of them
now avoids a second, near-identical call per platform later.

No web search tool here (unlike script_generation.py) - this repackages an
already-written final script, it doesn't need to research anything new.
Runs synchronously, immediately before a Captivate publish attempt (see
tick.py) - not on its own schedule - per the Phase 4 amendment to Section
8.1: generation work is deferred until the closest possible point to actual
publication, to avoid wasting it on episodes later aborted and replaced.
"""

import json

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "captivate_title": {"type": "string"},
        "captivate_notes": {"type": "string"},
        "aioseo_title": {"type": "string"},
        "aioseo_description": {"type": "string"},
        "youtube_title": {"type": "string"},
        "youtube_description": {"type": "string"},
        "youtube_tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "captivate_title",
        "captivate_notes",
        "aioseo_title",
        "aioseo_description",
        "youtube_title",
        "youtube_description",
        "youtube_tags",
    ],
    "additionalProperties": False,
}


def build_system_prompt(show_name):
    return (
        f'You write publishing metadata for "{show_name}", a daily good-news audio '
        "newscast, based on that day's already-finished script. You are not writing "
        "or editing the episode itself - only describing it for each platform.\n\n"
        "Field-specific rules:\n"
        "- captivate_title: a concise, compelling episode title (not just the show "
        "name repeated).\n"
        "- captivate_notes: show notes - a few sentences to a short paragraph "
        "summarizing what this episode covers.\n"
        "- aioseo_title / aioseo_description: written for search engines and social "
        "link previews, not duplicates of the Captivate fields.\n"
        "- youtube_title: under 100 characters.\n"
        "- youtube_description: the first ~125 characters are what's visible before "
        "truncation on YouTube, so lead with the most important part.\n"
        "- youtube_tags: 5-15 relevant single words or short phrases, no '#' symbols."
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
