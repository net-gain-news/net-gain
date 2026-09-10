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
        "daily good-news audio newscast, based on that day's already-finished script. "
        "You are not writing or editing the episode itself - only describing one "
        "image that captures it.\n\n"
        "Rules:\n"
        "- Purely visual and compositional: subject, setting, mood, palette, and "
        "style, as if briefing a photo/illustration editor for a news thumbnail.\n"
        "- Do not depict real, identifiable people (public figures or specific "
        "individuals) - describe generic, stylized human figures or abstract/"
        "symbolic visuals instead.\n"
        "- Do not include readable text, logos, or numerals in the image - "
        "text-to-image models render these poorly, and this show's own branding "
        "is composited on top afterward.\n"
        "- Upbeat, optimistic tone matching a good-news show - never somber or "
        "alarming, even if the underlying story has serious stakes.\n"
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
