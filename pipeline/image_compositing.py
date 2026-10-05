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

# Duotone is a gradient map: brightness is scaled so the image's near-brightest
# pixels (this percentile) reach the show's highlight color, then every
# brightness level is mapped linearly between the shadow color and highlight
# color. The BLACK end is deliberately NOT stretched (2026-10-05): an earlier
# full autocontrast pulled an image's darkest pixels to exactly the shadow
# color, which is also the overlay bar's color - so a dark background merged
# into the bar no matter how the image was prompted. Now a background that is
# mid-dark in the source stays visibly lighter than the bar. (History: the
# original multiply/screen blend stack, replaced 2026-10-02, compressed images
# into a ~25-level band and read as flat.)
DUOTONE_WHITE_POINT_PERCENTILE = 99

# WebP has no hard cap (SPEC.md Section 7's table), but is still worth
# optimizing for page-load performance/SEO - a soft, non-fatal target.
WEBP_SOFT_TARGET_BYTES = 200 * 1024


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def apply_duotone(image, shadow_hex, highlight_hex):
    """
    Grayscale -> scale so the bright end reaches full -> map brightness 0..255
    linearly onto the shadow color..highlight color gradient. Pure black stays
    exactly the shadow color; mid-darks stay proportionally above it.
    """
    grey = ImageOps.grayscale(image)
    histogram = grey.histogram()
    total = sum(histogram)
    white_point, seen = 255, 0
    for level in range(255, -1, -1):
        seen += histogram[level]
        if seen >= total * (100 - DUOTONE_WHITE_POINT_PERCENTILE) / 100:
            white_point = level
            break
    # A nearly-black image has no meaningful white point to scale up to.
    white_point = max(white_point, 32)
    scaled = grey.point([min(255, round(v * 255 / white_point)) for v in range(256)])

    shadow = _hex_to_rgb(shadow_hex)
    highlight = _hex_to_rgb(highlight_hex)
    channel_luts = [
        [round(shadow[c] + (highlight[c] - shadow[c]) * v / 255) for v in range(256)] for c in range(3)
    ]
    return Image.merge("RGB", [scaled.point(lut) for lut in channel_luts])


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
