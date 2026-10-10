"""
Real-photo episode graphics (show image mode "photos"): the logic that is not drawing - what a story is about,
what a photo shows, which photo to use, and which crop to give it this time.

Context: the code-built cards read as "too techy" for the edtech audience (2026-10-09). The operator now supplies real
photographs (from Envato Elements) through the plugin's Photos screen. The pipeline never generates imagery; it only
chooses among those photos, crops them differently each time they are used, applies the show's duotone and frames them.

Rules baked in:
  * A photo is used again only after the show's cooldown (the plugin computes `eligible`); if every photo is resting,
    the least recently used is reused rather than blocking publication, and the operator is warned.
  * Sensitive stories (breaches, safety, lawsuits...) never get a photo with identifiable people.
  * The photo suits story 1 - the script's first news story - never a later one (the story-order rule).
  * Selection and crops are deterministic for a given photo and use count, so a re-render reproduces the same graphic.
"""

import base64
import hashlib
import json
import logging
import random
from io import BytesIO

from PIL import Image, ImageOps

logger = logging.getLogger("net_gain.photo_library")

TOPICS = ["security", "ai", "policy", "funding", "business", "product", "higher_ed", "k12", "general"]
PEOPLE = ["none", "anonymous", "identifiable"]
SETTINGS = [
    "classroom", "students", "teacher", "school_exterior", "campus", "hallway", "laptop", "tablet", "computer_lab",
    "library", "city", "skyline", "books", "whiteboard", "code", "network", "hands", "meeting", "graduation",
    "desk", "lock", "data_center",
]
MAX_STORY_TOPICS = 3

# --- what is the story about -----------------------------------------------------------------------

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {"type": "array", "items": {"type": "string", "enum": TOPICS}},
        "settings": {"type": "array", "items": {"type": "string", "enum": SETTINGS}},
        "sensitive": {"type": "boolean"},
    },
    "required": ["topics", "settings", "sensitive"],
    "additionalProperties": False,
}


def build_brief_system_prompt(show_name):
    return (
        f'You help choose a photograph for the episode graphic of "{show_name}", a daily audio newscast. You are given '
        "that day's finished script.\n\n"
        "Look ONLY at story 1: the first news story after the opening preview line (ignore the preview line, the "
        "market-index segment, the sign-off and the links section). Never base the choice on a later story.\n\n"
        f"- topics: one to {MAX_STORY_TOPICS} from the list that best describe story 1.\n"
        "- settings: up to four visual settings from the list that a photograph illustrating story 1 could show. "
        "Prefer generic, not literal (a laptop and a lock for a breach; a classroom for a policy story).\n"
        "- sensitive: true if story 1 involves a data breach, ransomware or cyberattack, a threat to student safety or "
        "privacy, abuse, a lawsuit, discipline, a death, or anything where showing an identifiable person (especially a "
        "child) would be inappropriate or imply they were involved. Otherwise false."
    )


def describe_story(anthropic_generate, show_name, episode_date, final_script):
    """Story 1's topics, visual settings and sensitivity: {"topics": [...], "settings": [...], "sensitive": bool}."""
    text = anthropic_generate(
        system=build_brief_system_prompt(show_name),
        user_content=f"Episode date: {episode_date}\n\nFinal script:\n\n{final_script}",
        tools=[],
        response_schema=BRIEF_SCHEMA,
    )
    brief = json.loads(text)
    brief["topics"] = [t for t in brief.get("topics", []) if t in TOPICS][:MAX_STORY_TOPICS] or ["general"]
    brief["settings"] = [s for s in brief.get("settings", []) if s in SETTINGS][:4]
    brief["sensitive"] = bool(brief.get("sensitive"))
    return brief


# --- what does a photo show (vision) --------------------------------------------------------------

TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "is_photograph": {"type": "boolean"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "topics": {"type": "array", "items": {"type": "string", "enum": TOPICS}},
        "people": {"type": "string", "enum": PEOPLE},
        "focal_x": {"type": "number"},
        "focal_y": {"type": "number"},
        "description": {"type": "string"},
        "logo_or_text_visible": {"type": "boolean"},
    },
    "required": ["is_photograph", "tags", "topics", "people", "focal_x", "focal_y", "description", "logo_or_text_visible"],
    "additionalProperties": False,
}

TAG_SYSTEM_PROMPT = (
    "You catalogue photographs for a newsroom's image library (an education-technology news show). For the photo you "
    "are shown, return:\n"
    f"- is_photograph: true for a real camera photograph; false for an illustration, vector, 3D render, collage or "
    "anything that does not look like a genuine photograph.\n"
    f"- tags: three to eight lowercase tags, preferring this vocabulary: {', '.join(SETTINGS)}; add other short tags "
    "(for example 'sunlight', 'blue', 'wide shot') if useful.\n"
    f"- topics: which story topics the photo suits, from: {', '.join(TOPICS)} ('general' if it suits almost any story).\n"
    "- people: 'none' if no people are visible; 'anonymous' if people appear but cannot be identified (seen from behind, "
    "silhouettes, hands only, heavily blurred, tiny in the frame); 'identifiable' if any face is clearly recognisable.\n"
    "- focal_x, focal_y: the centre of the main subject as fractions of the image width and height (0 = left/top, "
    "1 = right/bottom). Every crop will keep this point in frame.\n"
    "- description: one factual sentence of what is shown. Do not guess places or names.\n"
    "- logo_or_text_visible: true if a readable brand logo, signage or text is prominent."
)


def prepare_for_vision(image_bytes, max_side=1024):
    """(jpeg_bytes, true_width, true_height) after applying the file's EXIF orientation."""
    image = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert("RGB")
    width, height = image.size
    image.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), width, height


def tag_photo(anthropic_generate, image_bytes):
    """
    Vision pass over one uploaded original. Returns the fields to store with the photo: tags, topics, people, focal
    point, description, flags, true dimensions, and the status to give it ("ready", or "retired" with a needs_review
    flag if it does not look like a photograph).
    """
    jpeg, width, height = prepare_for_vision(image_bytes)
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}},
        {"type": "text", "text": "Catalogue this photograph."},
    ]
    data = json.loads(anthropic_generate(system=TAG_SYSTEM_PROMPT, user_content=content, tools=[], response_schema=TAG_SCHEMA))

    flags = []
    if min(width, height) < 2200:
        flags.append("low_res")
    if data.get("logo_or_text_visible"):
        flags.append("logo_text")
    if height > width:
        flags.append("portrait")
    status = "ready"
    if not data.get("is_photograph", True):
        flags.append("needs_review")
        status = "retired"

    return {
        "tags": [str(t).lower().strip() for t in data.get("tags", [])][:8],
        "topics": [t for t in data.get("topics", []) if t in TOPICS] or ["general"],
        "people": data.get("people") if data.get("people") in PEOPLE else "identifiable",   # unknown = cautious
        "focal_x": min(1.0, max(0.0, float(data.get("focal_x", 0.5)))),
        "focal_y": min(1.0, max(0.0, float(data.get("focal_y", 0.5)))),
        "description": (data.get("description") or "")[:300],
        "flags": flags,
        "width": width,
        "height": height,
        "status": status,
    }


# --- which photo ------------------------------------------------------------------------------------

def score_photo(photo, brief):
    score = 0.0
    topics = set(photo.get("topics") or [])
    if topics & set(brief.get("topics") or []):
        score += 3
    elif "general" in topics:
        score += 1
    score += 2 * len(set(photo.get("tags") or []) & set(brief.get("settings") or []))
    flags = set(photo.get("flags") or [])
    if "low_res" in flags:
        score -= 2
    if "logo_text" in flags:
        score -= 1
    if not photo.get("use_count"):
        score += 1          # a fresh photo is slightly preferred
    return score


def select_photo(photos, brief, episode_date):
    """
    Choose a photo for a story. Returns (photo, relaxed): `relaxed` is True when every usable photo was resting and the
    least recently used one was reused anyway. Returns (None, False) when there is no usable photo at all.
    """
    usable = [p for p in photos if p.get("status") == "ready"]
    if brief.get("sensitive"):
        usable = [p for p in usable if p.get("people") != "identifiable"]
    if not usable:
        return None, False

    pool = [p for p in usable if p.get("eligible")]
    relaxed = not pool
    if relaxed:      # everything is resting: reuse the one rested longest (the best suited of any ties)
        return min(usable, key=lambda p: (p.get("last_used") or "", -score_photo(p, brief), p["id"])), True

    best = max(score_photo(p, brief) for p in pool)
    top = sorted((p for p in pool if score_photo(p, brief) >= best - 1), key=lambda p: p["id"])
    rng = random.Random(f"{episode_date}:{brief.get('topics')}")
    return rng.choice(top), relaxed


# --- which crop -------------------------------------------------------------------------------------

STRATEGIES = ["center", "left_third", "right_third"]
ZOOMS = [1.0, 1.0, 1.25, 1.5, 1.8]


def choose_variant(photo_id, use_count):
    """A crop recipe that differs each time the same photo is used, but is the same on a re-render."""
    rng = random.Random(f"{photo_id}:{use_count}")
    return {"zoom": rng.choice(ZOOMS), "strategy": rng.choice(STRATEGIES)}


def crop_box(img_w, img_h, focal, variant, win_w, win_h):
    """
    The source rectangle (left, top, right, bottom), in image pixels, that fills a win_w x win_h window.
    zoom 1.0 is the plain cover crop; higher zooms are tighter. The focal point is always inside the box.
    """
    scale = max(win_w / img_w, win_h / img_h) * max(1.0, variant["zoom"])
    crop_w, crop_h = min(img_w, win_w / scale), min(img_h, win_h / scale)
    fx, fy = focal[0] * img_w, focal[1] * img_h

    anchors = {"center": 0.5, "left_third": 1 / 3, "right_third": 2 / 3}
    left = fx - crop_w * anchors.get(variant["strategy"], 0.5)
    top = fy - crop_h * 0.5
    left = min(max(0.0, left), img_w - crop_w)
    top = min(max(0.0, top), img_h - crop_h)

    if not (left <= fx <= left + crop_w and top <= fy <= top + crop_h):    # focal point must stay in frame
        left = min(max(0.0, fx - crop_w / 2), img_w - crop_w)
        top = min(max(0.0, fy - crop_h / 2), img_h - crop_h)
    return (left, top, left + crop_w, top + crop_h)


# --- the weekly note and the low-stock warning ---------------------------------------------------

def library_email(show_name, stats):
    """(subject, body) for the weekly library note."""
    level = {"ok": "healthy", "low": "running low", "urgent": "needs photos now"}.get(stats.get("level"), "")
    lines = [f"Photo library for {show_name}: {level}.", ""]
    lines += [f"  {stats['eligible_now']} ready to use now",
              f"  {stats['cooling_down']} resting ({stats['cooldown_days']}-day cooldown)",
              f"  {stats['never_used']} never used",
              f"  {stats['eligible_no_faces']} usable for sensitive stories (no identifiable people)",
              f"  {stats['retired']} retired", ""]
    lines += [f"- {m}" for m in stats.get("messages", [])]
    lines += ["", "Add photos any time at Net Gain Studio > Photos: drag and drop, and they are tagged automatically."]
    return f"Net Gain Studio: photo library {level} ({show_name})", "\n".join(lines)


def stable_hash(text):
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)
