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
        "daily audio newscast, based on that day's already-finished script. You are "
        "not writing or editing the episode itself - only describing one image for "
        "its lead story.\n\n"
        "Rules:\n"
        "- Base the image entirely on the lead story - the first substantive story "
        "covered in the script, right after any opening preview line. Ignore every "
        "other story in the episode for purposes of this image; do not attempt to "
        "represent or synthesize the whole episode.\n"
        "- Purely visual and compositional: subject, setting, mood, palette, and "
        "style, as if briefing a photo/illustration editor for a news thumbnail. Let "
        "the lead story's own actual nature dictate the mood - do not impose an "
        "artificial tone.\n"
        "- Prefer a photorealistic style wherever the lead story's subject matter "
        "reasonably supports it (a real-world scene, object, setting, or product). "
        "Fall back to a stylized or illustrative treatment only when the subject is "
        "abstract or purely conceptual and has no sensible photorealistic depiction.\n"
        "- Do not depict real, identifiable people (public figures or specific "
        "individuals) - describe generic, stylized human figures instead.\n"
        "- A company's logo is acceptable, and encouraged, specifically when the "
        "lead story is about that company. Otherwise, do not include readable text, "
        "logos, or numerals - text-to-image models render these poorly, and this "
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
