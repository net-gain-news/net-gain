"""
Topics and entities per episode (internal linking, 2026-11-19).

Each published newscast is tagged with the named things it covers - companies, organizations, places and
recurring topics - so the website can link related newscasts to each other and build one page per topic
(plugin: class-entities.php, class-topic-pages.php). The tags are stored on the internal episode record as
`ng_entities`: a list of {name, slug, kind, note}, where note is one factual sentence on what the newscast
said about that entity (it becomes a line in the topic page's timeline).

Rules this module enforces in code, not only in the prompt:
  * the model reads the SPOKEN script only - never the numbered "Stories & links" lines. Those captions can
    carry a name an editor deliberately cut from the narration (the 2026-11-10 leak), so they are removed
    before the model sees anything;
  * individual people and criminal groups are never tags (an editor decides if and how those are named);
  * names already used on earlier episodes are shown to the model and reused exactly, so "Frontline Education"
    does not split into three pages;
  * extraction is enrichment, not a publishing step: ensure_entities() never raises. A failure is logged and
    the episode simply has no tags yet (the backfill script fills it in later).
"""

import json
import logging
import re
import unicodedata

from text_rules import K12_PROMPT_RULE

logger = logging.getLogger("net_gain.entities")

KINDS = ("company", "organization", "place", "topic")
MAX_ENTITIES = 6
MAX_NAME_CHARS = 60
MAX_NOTE_CHARS = 240

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "note": {"type": "string"},
                },
                "required": ["name", "kind", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["entities"],
    "additionalProperties": False,
}

_HEADING_LINE = re.compile(r"^\W*(?:show notes|stories\s*(?:&(?:amp;)?|and)?\s*(?:names\s*(?:and|&)\s*)?links)\b.*$", re.I)


def slugify(name):
    """URL-safe key for an entity name. The plugin trusts this stored value, so a name keeps the same page address
    for as long as it is spelled the same way (K-12's non-breaking hyphen becomes an ordinary one)."""
    text = re.sub("[\u2010-\u2015\u2212]", "-", name or "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("&", " and ")).strip("-")


def spoken_script(final_script):
    """The narration only: everything before the numbered link lines, and without the heading that introduces them."""
    lines = (final_script or "").splitlines()
    cut = len(lines)
    for index, line in enumerate(lines):
        if re.match(r"^\s*\d+\.\s*.+?\s*—\s*https?://\S", line):
            cut = index
            break
    body = lines[:cut]
    while body and (not body[-1].strip() or _HEADING_LINE.match(body[-1].strip().strip("*_ ")) or set(body[-1].strip()) <= set("-*–—_ ")):
        body.pop()
    return "\n".join(body).strip()


def build_system_prompt(show_name):
    return (
        f'You tag each episode of "{show_name}", a daily audio newscast, with the named things it covers, so listeners '
        "and search engines can find every newscast about the same company, organization, place or topic. Read the script "
        "and return between 2 and 6 tags.\n\n"
        "KINDS\n"
        "- company: a business or vendor (software, services, publishers, edtech companies, investors).\n"
        "- organization: a non-profit, association, union, agency, court, regulator or legislature.\n"
        "- place: a school district, school board, school, college, state, province or country.\n"
        "- topic: a recurring issue area, written as a short noun phrase of 2 to 5 words, in sentence case "
        "(for example: K-12 AI policy; Ransomware attacks on schools; Student data privacy; Edtech mergers and acquisitions).\n\n"
        "RULES\n"
        "- NEVER tag an individual person, and never a criminal group, ransomware gang or threat actor. Those names are "
        "an editorial decision and are not tags.\n"
        "- Tag the main subject of a story, not every name mentioned in passing. Prefer the organization or place a story "
        "is about over a topic, and add at most two topics.\n"
        "- Use the common full name (Frontline Education, not Frontline; PowerSchool, not PowerSchool Group LLC). "
        "Do not tag the show itself or its sponsor.\n"
        "- The user message lists names already in use on earlier episodes. When a tag is the same thing as one of them, "
        "copy that spelling exactly. Only invent a new name when nothing in the list fits.\n"
        "- note: ONE factual sentence, at most 35 words, saying what this episode reported about the tag. Use only "
        "what the script says. No opinion, no names of individuals, no hype, no URLs.\n"
        f"- {K12_PROMPT_RULE}"
    )


def build_user_message(episode_date, script, known_names):
    known = "\n".join(f"- {name}" for name in known_names) if known_names else "(none yet)"
    return (
        f"Episode date: {episode_date}\n\nNAMES ALREADY IN USE (reuse exactly when they fit):\n{known}\n\n"
        f"SCRIPT:\n{script}"
    )


def clean_entities(raw, known_names=()):
    """Validates the model's tags: known kinds, sane lengths, known spellings restored, duplicates and extras dropped."""
    by_slug = {slugify(name): name for name in known_names}
    seen, cleaned = set(), []
    for item in (raw or {}).get("entities") or []:
        name = re.sub(r"\s+", " ", str(item.get("name") or "")).strip()
        kind = item.get("kind")
        note = re.sub(r"\s+", " ", str(item.get("note") or "")).strip()
        slug = slugify(name)
        if not name or not slug or kind not in KINDS or len(name) > MAX_NAME_CHARS or slug in seen:
            continue
        if re.search(r"https?://", note):
            note = ""
        if len(note) > MAX_NOTE_CHARS:
            note = note[: MAX_NOTE_CHARS - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        name = by_slug.get(slug, name)
        seen.add(slug)
        cleaned.append({"name": name, "slug": slug, "kind": kind, "note": note})
    return cleaned[:MAX_ENTITIES]


def extract_entities(anthropic_generate, show_name, episode_date, final_script, known_names=()):
    script = spoken_script(final_script)
    if not script:
        raise ValueError("the script has no spoken text to tag")
    text = anthropic_generate(
        system=build_system_prompt(show_name),
        user_content=build_user_message(episode_date, script, sorted(known_names)),
        tools=[],
        response_schema=RESPONSE_SCHEMA,
    )
    entities = clean_entities(json.loads(text), known_names)
    if len(entities) < 1:
        raise ValueError("the model returned no usable tags")
    return entities


def known_entity_names(episodes, exclude_id=None):
    """Every distinct tag name already stored on the show's episodes (most-used first), for the model to reuse."""
    counts = {}
    for episode in episodes or []:
        if exclude_id and episode.get("id") == exclude_id:
            continue
        for entity in (episode.get("meta") or {}).get("ng_entities") or []:
            if isinstance(entity, dict) and entity.get("name"):
                counts[entity["name"]] = counts.get(entity["name"], 0) + 1
    return [name for name, _n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def ensure_entities(wp, anthropic_generate, show, episode_id, force=False):
    """Tags the episode if it has no tags yet (or force). Never raises; returns the stored tags or None."""
    try:
        episode = wp.get_episode(episode_id)
        meta = episode.get("meta", {}) or {}
        if meta.get("ng_entities") and not force:
            return meta["ng_entities"]
        if not meta.get("ng_script_final"):
            return None
        known = known_entity_names(wp.list_episodes_for_show(show["id"]), exclude_id=episode_id)
        entities = extract_entities(anthropic_generate, show["name"], meta.get("ng_episode_date", ""), meta["ng_script_final"], known)
        wp.update_episode_meta(episode_id, {"ng_entities": entities})
        logger.info("Tagged episode %s: %s", episode_id, ", ".join(e["name"] for e in entities))
        return entities
    except Exception:    # enrichment only: a failure must never hold up a publish
        logger.warning("Could not tag episode %s with topics; it publishes without them.", episode_id, exc_info=True)
        return None
