"""
Pillow-only image processing for the image pipeline (SPEC.md Section 7): the
optional per-show duotone treatment, cropping one shared base image to each
output's exact aspect ratio, compositing the show's frame on top, and
encoding to each output's required format/size constraints.

Deliberately no network calls anywhere in this module - the base image and
frame bytes are handed in already fetched, and the result is handed back as
plain bytes for the caller to upload. Makes this the one piece of the image
pipeline testable with zero external dependencies.
"""

import logging
from io import BytesIO

from PIL import Image, ImageOps

logger = logging.getLogger("net_gain.image_compositing")

# Duotone is a gradient map: the image's brightness range is stretched to
# full (autocontrast, clipping this fraction of the darkest and lightest
# pixels), then each brightness level is mapped onto a straight line between
# the show's shadow color (black point) and highlight color (white point).
# Replaced 2026-10-02: the earlier multiply/screen blend stack (ported from
# the design reference's CSS) compressed a 0-255 image into a ~25-level band
# (measured 62-83), so every graphic read as flat and murky regardless of how
# contrasty the source was. The two colors are still the only per-show
# parameters; the highlight color must therefore be a genuinely light tone.
DUOTONE_AUTOCONTRAST_CUTOFF = 1

# WebP has no hard cap (SPEC.md Section 7's table), but is still worth
# optimizing for page-load performance/SEO - a soft, non-fatal target.
WEBP_SOFT_TARGET_BYTES = 200 * 1024


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def apply_duotone(image, shadow_hex, highlight_hex):
    """
    Grayscale -> autocontrast -> map brightness 0..255 linearly onto the
    shadow color..highlight color gradient. Black becomes exactly the shadow
    color and white exactly the highlight color.
    """
    grey = ImageOps.autocontrast(ImageOps.grayscale(image), cutoff=DUOTONE_AUTOCONTRAST_CUTOFF)
    shadow = _hex_to_rgb(shadow_hex)
    highlight = _hex_to_rgb(highlight_hex)
    channel_luts = [
        [round(shadow[c] + (highlight[c] - shadow[c]) * v / 255) for v in range(256)] for c in range(3)
    ]
    return Image.merge("RGB", [grey.point(lut) for lut in channel_luts])


def cover_resize(image, target_w, target_h):
    """
    Standard 'object-fit: cover' - scale to fully cover (target_w, target_h)
    preserving aspect ratio, then center-crop the overflow. The base image is
    generated at the widest of the three target ratios (SPEC.md Section 7),
    so this is always an inward crop, never a pad/outpaint.
    """
    src_w, src_h = image.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    resized = image.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def composite_frame(image, frame_png_bytes):
    """
    Alpha-composites the show's frame PNG over an already-correctly-sized
    image: the frame's opaque branding paints over the image, its transparent
    cutout reveals the image beneath. Drops the alpha channel on output - the
    result is a finished flat image, not a template.
    """
    frame = Image.open(BytesIO(frame_png_bytes)).convert("RGBA")
    if frame.size != image.size:
        frame = frame.resize(image.size)  # defensive; frame should already match
    base = image.convert("RGBA")
    return Image.alpha_composite(base, frame).convert("RGB")


def encode_with_size_cap(image, fmt, max_bytes):
    """
    JPEG (hard cap, SPEC.md Section 7): iterative quality-stepping, bounded -
    quality 90 down to 40 in steps of 5, then dimension downscaling 90% down
    to 50% at floor quality as a last resort. A size-cap miss that survives
    all of that logs a warning and returns the smallest result achieved
    rather than aborting the whole images_rendered step over a cosmetic-asset
    size miss - that's what image-generation *failure* handling (the
    fallback path) is for, a distinct, narrower safety net.

    WebP (website art): same stepping loop, but toward WEBP_SOFT_TARGET_BYTES
    as a non-fatal performance/SEO target, not a spec-mandated cap.
    """
    target_bytes = max_bytes if max_bytes is not None else WEBP_SOFT_TARGET_BYTES
    pil_format = "WEBP" if fmt == "WEBP" else "JPEG"

    buf = BytesIO()
    for quality in range(90, 39, -5):
        buf = BytesIO()
        image.save(buf, format=pil_format, quality=quality, optimize=True)
        if buf.tell() <= target_bytes:
            return buf.getvalue()

    for scale in (0.9, 0.8, 0.7, 0.6, 0.5):
        resized = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
        buf = BytesIO()
        resized.save(buf, format=pil_format, quality=40, optimize=True)
        if buf.tell() <= target_bytes:
            return buf.getvalue()

    logger.warning(
        "Could not get %s under %d bytes even at floor quality/scale - using smallest achieved (%d bytes).",
        pil_format, target_bytes, buf.tell(),
    )
    return buf.getvalue()


def composite_and_encode(base_image, frame_png_bytes, output_spec, show_slug, episode_date, spec_name):
    cropped = cover_resize(base_image, output_spec["width"], output_spec["height"])
    composited = composite_frame(cropped, frame_png_bytes)
    encoded = encode_with_size_cap(composited, output_spec["format"], output_spec["max_bytes"])
    ext = "jpg" if output_spec["format"] == "JPEG" else "webp"
    filename = f"{show_slug}-{episode_date}-{spec_name}.{ext}"
    return encoded, filename
