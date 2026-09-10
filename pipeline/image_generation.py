"""
Image rendering orchestration (SPEC.md Section 7): one AI-generated base
image per episode, an optional per-show duotone treatment, then cropped and
composited into each of the show's three frames and uploaded.

The Vertex AI call shape (build_vertex_client / generate_base_image) is
isolated in its own small pair of functions deliberately - as of this
build's research, Google's current recommended unified SDK is `google-genai`
used against the Vertex AI backend, but this surface should be verified
against live, current documentation before first real use (SPEC.md Section
1's carried-forward lesson: API surfaces shift, don't build on recall alone).
A corrected call shape only needs to touch this one place.
"""

import json
import logging
from io import BytesIO

from PIL import Image

from image_compositing import apply_duotone, composite_and_encode
from image_prompt import generate_image_prompt_for_episode
from retry import call_with_retries

logger = logging.getLogger("net_gain.image_generation")

# Imagen's own aspect-ratio presets don't include an exact match for
# website art's 1200x630 (~1.91:1) - "16:9" is the widest available preset,
# so the base image is generated at that ratio (minimizing how much gets
# cropped away for every output) and cover_resize handles the exact final
# pixel dimensions per spec regardless of the small remaining mismatch.
BASE_IMAGE_ASPECT_RATIO = "16:9"

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
    One Imagen call -> raw base image bytes. VERIFY AGAINST LIVE DOCUMENTATION
    AT BUILD TIME - model id and config field names are this build's best
    understanding, not a confirmed-live call shape.
    """
    from google.genai import types

    def do_request():
        return client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(aspect_ratio=BASE_IMAGE_ASPECT_RATIO, number_of_images=1),
        )

    response = call_with_retries(do_request, RETRYABLE_EXCEPTIONS) if RETRYABLE_EXCEPTIONS else do_request()
    images = getattr(response, "generated_images", None)
    if not images:
        raise RuntimeError(f"Imagen returned no generated images: {response}")
    return images[0].image.image_bytes


def render_images_for_episode(wp, vertex_client, anthropic_generate, show, episode_id):
    episode = wp.get_episode(episode_id)
    meta = episode.get("meta", {})
    episode_date = meta.get("ng_episode_date", "")

    image_prompt = generate_image_prompt_for_episode(
        anthropic_generate, show["name"], episode_date, meta.get("ng_script_final", "")
    )

    show_details = wp.get_show(show["id"])
    show_meta = show_details.get("meta", {})

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
