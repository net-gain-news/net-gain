"""
Pre-publish checklist (SPEC.md Section 6.3): "no literal optimization score
exists to check against... instead, build an internal pre-publish checklist
validating known, public best-practice criteria (title length and keyword
presence, description length, tag count, thumbnail spec compliance) - the
pipeline does not publish to YouTube until every criterion in this checklist
passes." This module is exactly that checklist - pure logic, no network, so
it's fully unit-testable like the rest of pipeline/tests/.

Ticker-symbol inclusion (SPEC Section 6.1/6.3's algorithmic-SEO amendment) is
deliberately NOT a criterion here - there is no way for this checklist to
independently know whether a given episode actually discussed a publicly-
traded company, so enforcing it would either false-fail every episode that
didn't, or require re-deriving that judgment from the script, which belongs
in metadata_generation.py's own prompt, not a mechanical gate.
"""

import io

from PIL import Image

TITLE_MAX_CHARS = 100
DESCRIPTION_MIN_CHARS = 200
DESCRIPTION_MAX_CHARS = 5000
DESCRIPTION_PREVIEW_CHARS = 125
TAG_MIN_COUNT = 5
TAG_MAX_COUNT = 15
TAG_MAX_TOTAL_CHARS = 500  # YouTube's documented aggregate tag limit - FLAG: verify live.
THUMBNAIL_MIN_WIDTH = 1280
THUMBNAIL_MIN_HEIGHT = 720
THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024  # YouTube's documented limit - FLAG: verify live.
THUMBNAIL_ASPECT_RATIO = 16 / 9
THUMBNAIL_ASPECT_TOLERANCE = 0.05
THUMBNAIL_ALLOWED_FORMATS = {"JPEG", "PNG", "GIF"}

# Words too generic to count as a meaningful keyword match against the show
# name (Section 10's own "fail loudly and specifically" applies here too -
# matching on "the" or "and" would make the keyword-presence check worthless).
_STOPWORDS = {"the", "a", "an", "and", "of", "for", "show", "news", "daily"}


def evaluate(title, description, tags, thumbnail_bytes, show_name):
    """
    Returns a list of failed-criterion descriptions (empty list = pass).
    Never raises on malformed input - a malformed thumbnail, for instance, is
    itself a failed criterion, not an exception to propagate.
    """
    failures = []

    failures.extend(_check_title(title, tags, show_name))
    failures.extend(_check_description(description))
    failures.extend(_check_tags(tags))
    failures.extend(_check_thumbnail(thumbnail_bytes))

    return failures


def _check_title(title, tags, show_name):
    failures = []
    title = title or ""

    if not title.strip():
        failures.append("Title is empty.")
        return failures  # no point checking length/keywords against nothing

    if len(title) > TITLE_MAX_CHARS:
        failures.append(f"Title is {len(title)} characters, over YouTube's {TITLE_MAX_CHARS}-character limit.")

    if not _title_contains_keyword(title, tags, show_name):
        failures.append(
            "Title contains no recognizable keyword from the generated tags or the show name - "
            "unlikely to match real searches for this episode's actual content."
        )

    return failures


def _title_contains_keyword(title, tags, show_name):
    title_lower = title.lower()

    for tag in tags or []:
        if tag and str(tag).strip().lower() in title_lower:
            return True

    for word in (show_name or "").split():
        word = word.strip().lower().strip(",.:;!?'\"")
        if len(word) > 2 and word not in _STOPWORDS and word in title_lower:
            return True

    return False


def _check_description(description):
    failures = []
    description = description or ""
    length = len(description)

    if length < DESCRIPTION_MIN_CHARS:
        failures.append(f"Description is only {length} characters - too short to be substantive (minimum {DESCRIPTION_MIN_CHARS}).")
    if length > DESCRIPTION_MAX_CHARS:
        failures.append(f"Description is {length} characters, over YouTube's {DESCRIPTION_MAX_CHARS}-character limit.")

    preview = description[:DESCRIPTION_PREVIEW_CHARS].strip()
    if not preview:
        failures.append(f"The first ~{DESCRIPTION_PREVIEW_CHARS} characters of the description (what's visible before truncation) are empty.")

    return failures


def _check_tags(tags):
    failures = []
    tags = [str(t).strip() for t in (tags or []) if str(t).strip()]

    if len(tags) < TAG_MIN_COUNT or len(tags) > TAG_MAX_COUNT:
        failures.append(f"{len(tags)} tags generated - expected between {TAG_MIN_COUNT} and {TAG_MAX_COUNT}.")

    hashtag_style = [t for t in tags if t.startswith("#")]
    if hashtag_style:
        failures.append(f"{len(hashtag_style)} tag(s) start with '#', which YouTube tags should not ({hashtag_style}).")

    total_chars = sum(len(t) for t in tags)
    if total_chars > TAG_MAX_TOTAL_CHARS:
        failures.append(f"Combined tag length is {total_chars} characters, over the {TAG_MAX_TOTAL_CHARS}-character aggregate limit.")

    return failures


def _check_thumbnail(thumbnail_bytes):
    if not thumbnail_bytes:
        return ["No thumbnail image available."]

    failures = []

    if len(thumbnail_bytes) > THUMBNAIL_MAX_BYTES:
        failures.append(
            f"Thumbnail is {len(thumbnail_bytes)} bytes, over the {THUMBNAIL_MAX_BYTES}-byte limit."
        )

    try:
        image = Image.open(io.BytesIO(thumbnail_bytes))
        image.load()
    except Exception as exc:  # noqa: BLE001 - any decode failure is itself the finding
        failures.append(f"Thumbnail could not be read as an image: {exc}")
        return failures

    if (image.format or "").upper() not in THUMBNAIL_ALLOWED_FORMATS:
        failures.append(f"Thumbnail format is {image.format!r} - expected one of {sorted(THUMBNAIL_ALLOWED_FORMATS)}.")

    width, height = image.size
    if width < THUMBNAIL_MIN_WIDTH or height < THUMBNAIL_MIN_HEIGHT:
        failures.append(
            f"Thumbnail is {width}x{height}, smaller than the required minimum "
            f"{THUMBNAIL_MIN_WIDTH}x{THUMBNAIL_MIN_HEIGHT}."
        )
    elif height:
        ratio = width / height
        if abs(ratio - THUMBNAIL_ASPECT_RATIO) > THUMBNAIL_ASPECT_TOLERANCE:
            failures.append(
                f"Thumbnail aspect ratio is {ratio:.3f}, not close enough to the required "
                f"16:9 (~{THUMBNAIL_ASPECT_RATIO:.3f})."
            )

    return failures
