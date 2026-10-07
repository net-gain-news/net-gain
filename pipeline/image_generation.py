"""
Image rendering orchestration (SPEC.md Section 7): one AI-generated base
image per episode, an optional per-show duotone treatment, then cropped and
composited into each of the show's three frames and uploaded.

Provider: Gemini 2.5 Flash Image ("Nano Banana"), not Imagen - changed
2026-09-10 after live discovery that Imagen requires a Google-approved
allowlist request with no confirmed timeline, while this model resolved
immediately with no such gate, on the same Vertex AI project/billing
relationship. Still a first-party Google model, still a plain serverless API
call - the spec's original intent, just a different specific model.

The Vertex AI call shape (build_vertex_client / generate_base_image) is
isolated in its own small pair of functions deliberately - this is a
multimodal generateContent call (Gemini's own chat-style interface returning
content parts, one of which may hold inline image bytes), not a dedicated
image-generation endpoint like Imagen's, so it should be verified against a
real response the first time it actually runs (SPEC.md Section 1's
carried-forward lesson: API surfaces shift, don't build on recall alone). A
corrected call shape only needs to touch this one place.
"""

import json
import logging
from datetime import date
from io import BytesIO

from PIL import Image

import cards
from card_text import generate_card_text
from image_compositing import apply_duotone, composite_and_encode, encode_with_size_cap
from image_prompt import generate_image_prompt_for_episode
from retry import call_with_retries

logger = logging.getLogger("net_gain.image_generation")

# The base image is generated to match the VISIBLE window of the frames, not the
# whole output (2026-10-05): the overlay covers the bottom of each output, so the
# 16:9 frame shows a 1280x576 window (2.22:1) and the 1200x630 frame a 1200x502
# one (2.39:1). Google's image models only offer preset aspect ratios; "21:9"
# (2.33:1) is the closest to both. image_compositing.fit_to_visible_window then
# cover-fits the base into each frame's real window (the square's is 1.16:1, so
# its sides are cropped - which is why the house style asks for a compact,
# centered subject).
BASE_IMAGE_ASPECT_RATIO = "21:9"

OUTPUT_SPECS = {
    "square":   {"width": 3000, "height": 3000, "format": "JPEG", "mime": "image/jpeg", "max_bytes": 500 * 1024},
    "16x9":     {"width": 1280, "height": 720,  "format": "JPEG", "mime": "image/jpeg", "max_bytes": 1024 * 1024},
    "1200x630": {"width": 1200, "height": 630,  "format": "WEBP", "mime": "image/webp", "max_bytes": None},
}
FRAME_META_KEYS = {"square": "ng_frame_square_id", "16x9": "ng_frame_16x9_id", "1200x630": "ng_frame_1200x630_id"}
FALLBACK_META_KEYS = {
    "square": "ng_fallback_square_id",
    "16x9": "ng_fallback_16x9_id",
    "1200x630": "ng_fallback_1200x630_id",
}
CARD_TEMPLATE_META_KEY = "ng_card_template"        # episode meta: which card the episode was drawn with
CARD_LAST_META_KEY = "ng_card_last_template"       # show meta: the template the rotation used most recently
IMAGE_MODE_META_KEY = "ng_image_mode"              # show meta: "ai" (default) or "cards"
IMAGE_META_KEYS = {"square": "ng_image_square_id", "16x9": "ng_image_16x9_id", "1200x630": "ng_image_1200x630_id"}

RETRYABLE_EXCEPTIONS = ()
try:
    from google.api_core.exceptions import DeadlineExceeded, ResourceExhausted, ServiceUnavailable

    RETRYABLE_EXCEPTIONS = (ResourceExhausted, ServiceUnavailable, DeadlineExceeded)
except ImportError:
    pass  # Verify the actual exception types for whichever SDK is installed at build time.


def build_vertex_client(config):
    """Isolated so a corrected SDK/call shape touches one place, not every caller."""
    from google import genai
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(config["GOOGLE_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return genai.Client(
        vertexai=True,
        project=config["GOOGLE_CLOUD_PROJECT"],
        location=config.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        credentials=credentials,
    )


def generate_base_image(client, prompt):
    """
    One Gemini 2.5 Flash Image ("Nano Banana") call -> raw base image bytes.
    VERIFY AGAINST A LIVE RESPONSE THE FIRST TIME THIS ACTUALLY RUNS - the
    model id, the image_config field name/shape, and exactly where inline
    image bytes land in the response are this build's best understanding
    from the model's Vertex AI Model Garden card, not a confirmed-live call.
    Unlike a dedicated image-generation endpoint, generateContent returns a
    list of content parts (text and/or image) - the image is whichever part
    carries inline_data.
    """
    from google.genai import types

    def do_request():
        return client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio=BASE_IMAGE_ASPECT_RATIO),
            ),
        )

    response = call_with_retries(do_request, RETRYABLE_EXCEPTIONS) if RETRYABLE_EXCEPTIONS else do_request()
    candidates = getattr(response, "candidates", None)
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {response}")

    for part in candidates[0].content.parts:
        inline_data = getattr(part, "inline_data", None)
        if inline_data and inline_data.data:
            return inline_data.data

    raise RuntimeError(f"Gemini response contained no image data: {response}")


def card_index_from_snapshot(show_meta, episode_date):
    """
    The day's Edtech Index in the shape the cards use, or None. Only a snapshot refreshed on the episode's own
    date counts: yesterday's numbers on today's card would be wrong.
    """
    snapshot = show_meta.get("ng_index_snapshot") or {}
    if not snapshot or show_meta.get("ng_index_last_refresh_date") != episode_date:
        return None
    if snapshot.get("daily_change_percent") is None:
        return None
    moves = [
        {"t": c["ticker"], "co": c.get("company", ""), "mv": c["day_change_percent"]}
        for c in snapshot.get("constituents") or []
        if c.get("ticker") and c.get("day_change_percent") is not None
    ]
    return {"pct": snapshot["daily_change_percent"], "ytd": snapshot.get("ytd_change_percent"), "moves": moves}


def render_cards_for_episode(wp, anthropic_generate, show, episode_id, episode, show_meta):
    """
    Code-built card path (show image mode "cards"): no AI imagery. Text is generated from the script (with the
    story-order audit), the template comes from the show's round-robin rotation, and all three formats are drawn
    and uploaded like the AI path's. If the text cannot be generated safely (story-order audit failure), the card
    is simply drawn from a template that needs no generated text - never with wrong-order text.
    """
    meta = episode.get("meta", {})
    episode_date = meta.get("ng_episode_date", "")
    dt = date.fromisoformat(episode_date)

    frames = {}
    for spec, meta_key in FRAME_META_KEYS.items():
        frame_id = show_meta.get(meta_key, 0)
        if not frame_id:
            raise RuntimeError(f"Show '{show['name']}' has no {spec} frame configured.")
        frames[spec] = wp.download_binary(wp.get_attachment_url(frame_id))

    content = cards.CardContent(episode_date=dt, index=card_index_from_snapshot(show_meta, episode_date))
    try:
        text = generate_card_text(anthropic_generate, show["name"], episode_date, meta.get("ng_script_final", ""))
        content.headline, content.keywords = text["headline"], text["keywords"]
    except Exception as exc:   # includes StoryOrderError - fall back to templates that need no generated text
        logger.warning("Card text unavailable for episode %s (%s); drawing a text-free card: %s", episode_id, show["name"], exc)

    stored = meta.get(CARD_TEMPLATE_META_KEY) or ""
    candidates = cards.candidate_templates(show_meta.get(CARD_LAST_META_KEY) or "", content)
    if stored in candidates:
        candidates = [stored] + [t for t in candidates if t != stored]   # a re-render keeps the episode's own card
    if not candidates:
        raise RuntimeError("No card template can be drawn for this episode.")

    rendered, chosen, last_error = None, None, None
    for template in candidates:
        try:
            rendered, chosen = cards.render_formats(template, content, frames), template
            break
        except cards.CardLayoutError as exc:
            last_error = exc
            logger.warning("Card %s does not fit episode %s (%s): %s", template, episode_id, show["name"], exc)
    if rendered is None:
        raise RuntimeError(f"No card template fit this episode: {last_error}")

    result_meta = {CARD_TEMPLATE_META_KEY: chosen}
    for spec, output_spec in OUTPUT_SPECS.items():
        encoded = encode_with_size_cap(rendered[spec], output_spec["format"], output_spec["max_bytes"])
        ext = "jpg" if output_spec["format"] == "JPEG" else "webp"
        filename = f"{show['slug']}-{episode_date}-{spec}.{ext}"
        result_meta[IMAGE_META_KEYS[spec]] = wp.upload_media(encoded, filename, output_spec["mime"])
    wp.update_episode_meta(episode_id, result_meta)
    if chosen != stored:
        wp.update_show_meta(show["id"], {CARD_LAST_META_KEY: chosen})
    logger.info("Drew card %s for episode %s (%s).", chosen, episode_id, show["name"])


def render_images_for_episode(wp, vertex_client, anthropic_generate, show, episode_id):
    episode = wp.get_episode(episode_id)
    meta = episode.get("meta", {})
    episode_date = meta.get("ng_episode_date", "")

    show_details = wp.get_show(show["id"])
    show_meta = show_details.get("meta", {})

    if show_meta.get(IMAGE_MODE_META_KEY) == "cards":
        return render_cards_for_episode(wp, anthropic_generate, show, episode_id, episode, show_meta)

    image_prompt = generate_image_prompt_for_episode(
        anthropic_generate, show["name"], episode_date, meta.get("ng_script_final", "")
    )

    frame_bytes = {}
    for spec, meta_key in FRAME_META_KEYS.items():
        frame_id = show_meta.get(meta_key, 0)
        if not frame_id:
            raise RuntimeError(f"Show '{show['name']}' has no {spec} frame configured.")
        frame_bytes[spec] = wp.download_binary(wp.get_attachment_url(frame_id))

    base_bytes = generate_base_image(vertex_client, image_prompt)
    base_image = Image.open(BytesIO(base_bytes)).convert("RGB")

    if show_meta.get("ng_image_style") == "duotone":
        shadow = show_meta.get("ng_duotone_shadow_color") or "#000000"
        highlight = show_meta.get("ng_duotone_highlight_color") or "#ffffff"
        base_image = apply_duotone(base_image, shadow, highlight)

    result_meta = {}
    for spec, output_spec in OUTPUT_SPECS.items():
        encoded_bytes, filename = composite_and_encode(
            base_image, frame_bytes[spec], output_spec, show["slug"], episode_date, spec
        )
        result_meta[IMAGE_META_KEYS[spec]] = wp.upload_media(encoded_bytes, filename, output_spec["mime"])

    wp.update_episode_meta(episode_id, result_meta)
