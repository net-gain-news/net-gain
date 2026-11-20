"""
Topics and entities per episode (internal linking, 2026-11-19; rebuilt the same day after an audit of the first version).

Each published newscast is tagged with the named things it covers - companies, organizations, places and a short, fixed list
of recurring topics - so the website can link related newscasts to each other and build one page per topic (plugin:
class-entities.php, class-topic-pages.php). Tags are stored on the internal episode record as `ng_entities`: a list of
{name, slug, kind, note, parent, level, evidence}. `note` is one factual sentence on what the newscast said about the tag (a line
in the topic page's timeline); `parent` is the slug of the containing place (district -> province or state -> country); `evidence`
is the sentence of the script that justifies the tag.

Why the first version failed (audit of all 42 scripts): one unconstrained judgment call per episode, capped at six tags, told
to tag only "main subjects". It dropped organizations that appeared in the closing "what to watch" line (OASBO), skipped
provinces and states in favour of districts (British Columbia: 8 episodes, 0 tags), and let a topic tag stand with no
supporting story (M&A on a day with no deal). This version fixes that in code, not only in the prompt:

  1. The model walks the script story by story (and the closing calendar) and tags each one; the places of a story are a
     chain - local place, then province or state, then country.
  2. Every tag must carry a VERBATIM sentence from the script. Code checks the sentence is really in the script and that the
     tag's name is supported by it; a tag that fails is dropped. This is what stops a topic tag with no story behind it.
  3. Topics come from a fixed list with written criteria (TOPICS); anything else is dropped.
  4. A name scan (gazetteer.py plus every name tagged on earlier episodes) finds places and organizations the model skipped.
     Each hit is only a candidate until a second, cheap model call confirms the sentence is really about that place or
     organization ("Washington", "Georgia", "New York Times").
  5. The cap is 32 tags (the site shows the best few as chips; the rest feed the topic pages). The first run capped at 16 and the
     cap bound on 35 of 42 episodes, silently dropping the places that sort last.

Standing rules kept in code: the model reads the SPOKEN script only (the numbered "Stories & links" captions can carry a name an
editor deliberately cut from the narration); individual people and criminal groups are never tags; the home country and the
show's sponsor are never tags; extraction is enrichment, so ensure_entities() never raises.
"""

import json
import logging
import re
import unicodedata

import gazetteer
from text_rules import K12_PROMPT_RULE, apply_text_rules

logger = logging.getLogger("net_gain.entities")

KINDS = ("company", "organization", "place", "topic")
LEVELS = ("local", "region", "country")
MAX_ENTITIES = 32
MAX_NAME_CHARS = 60
MAX_NOTE_CHARS = 240
MAX_CANDIDATES = 40

# The fixed topic list. Slugs are the page addresses (/edtech/topics/{slug}/), so a name is never changed once published.
# A new topic is added here (and its blurb in the plugin's Net_Gain_Entities::topic_blurbs()) on purpose, never by the model.
TOPICS = {
    "K-12 AI policy": "Rules, policies, guidance, legislation or official positions on how AI may be used in or around schools: board policies, state frameworks, bans, safety standards, lawsuits over AI. A vendor's AI feature launch alone is NOT policy.",
    "Ransomware attacks on schools": "A cyberattack, ransomware incident, data-theft claim or breach at a school, district, college or education technology vendor, including its follow-ups, arrests, lawsuits and notifications.",
    "Student data privacy": "Laws, privacy statements, lawsuits or investigations about how student or staff personal data is collected, shared or protected. A report of a breach alone belongs under cyberattacks, not here.",
    "E-Rate program": "The FCC's E-Rate school and library connectivity funding program: its rules, proceedings, comment deadlines and funding.",
    "Edtech mergers and acquisitions": "An announced, completed or progressing acquisition, merger, takeover bid or sale of an education or education technology company. Share-price moves, earnings or financing alone do NOT count.",
    "Edtech stocks and earnings": "Share-price moves, earnings reports, guidance and market commentary on publicly traded education companies, including the Net Gain Edtech Index.",
    "Edtech funding and investment": "Venture rounds, grants and other investment in education technology companies or programs. Acquisitions belong under mergers.",
    "Student online safety": "Rules, studies or incidents about children's safety online: social media, screen time, chatbots and companion apps, cellphone bans.",
    "Edtech product launches": "A company launching or materially updating a product or feature for schools, colleges or learners.",
}


def topic_name(name):
    """The topic list spells K-12 with the house non-breaking hyphen, like every other generated text."""
    return apply_text_rules(name)


def slugify(name):
    """URL-safe key for an entity name. The plugin trusts this stored value, so a name keeps the same page address
    for as long as it is spelled the same way (K-12's non-breaking hyphen becomes an ordinary one)."""
    text = re.sub("[‐-―−]", "-", name or "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("&", " and ")).strip("-")


TOPIC_BY_SLUG = {slugify(name): topic_name(name) for name in TOPICS}

_HEADING_LINE = re.compile(r"^\W*(?:show notes|stories\s*(?:&(?:amp;)?|and)?\s*(?:names\s*(?:and|&)\s*)?links)\b.*$", re.I)


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


def norm(text):
    """Text reduced for matching: quotes and dashes unified (the non-breaking K-12 hyphen included), markdown emphasis
    removed, case folded, whitespace collapsed."""
    text = str(text or "")
    text = re.sub("[‘’ʼ]", "'", text)
    text = re.sub("[“”]", '"', text)
    text = re.sub("[‐-―−]", "-", text)
    text = text.replace("*", "").replace("_", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in_script(quote, script_norm):
    """True when the quoted sentence really is in the script. A quote may skip text with an ellipsis; every piece must appear."""
    pieces = [p.strip(" .,;:!?\"'") for p in re.split(r"\.{3}|…", norm(quote))]
    pieces = [p for p in pieces if len(p) >= 12]
    return bool(pieces) and all(p in script_norm for p in pieces)


_GENERIC = {"school", "schools", "district", "districts", "public", "county", "the", "of", "and", "for", "inc", "corp", "corporation",
            "group", "company", "education", "educational", "board", "city", "state", "united", "department", "national", "international",
            "university", "college", "association", "program", "limited", "plc", "llc", "ltd"}


def name_supported(name, quote):
    """True when the quote actually names the tag: a distinctive word of the name, the name's initials (FCC), or a known short form
    of it (gazetteer aliases) is in it."""
    quote_n = norm(quote)
    words = re.findall(r"[A-Za-z0-9]+", name)
    tokens = [w.lower() for w in words if w.lower() not in _GENERIC and len(w) >= 2]
    initials = "".join(w[0] for w in words if w[0].isupper()).lower()
    if not tokens and len(initials) < 2:
        return True
    if any(re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", quote_n) for t in tokens):
        return True
    for spoken, canonical in list(gazetteer.ORG_ALIASES.items()) + list(gazetteer.PLACE_ALIASES.items()):
        if canonical == name and re.search(r"(?<![A-Za-z0-9])" + re.escape(spoken) + r"(?![A-Za-z0-9])", str(quote)):
            return True
    return len(initials) >= 2 and bool(re.search(r"(?<![a-z0-9])" + re.escape(initials) + r"(?![a-z0-9])", re.sub(r"[.]", "", quote_n)))


_GAZETTEER_PLACES = {name for name, _k, _p, _l in gazetteer.places()}


def inferred_place(name, kind, level):
    """A province, state or country the model added because a local place in the story sits in it. The sentence names the local place,
    not the province, so the name is not checked against the quote - but only gazetteer places may be inferred this way."""
    return kind == "place" and level in ("region", "country") and name in _GAZETTEER_PLACES


# ------------------------------------------------------------------ the model's job


def _topic_lines():
    return "\n".join(f"- {topic_name(name)}: {definition}" for name, definition in TOPICS.items())


def build_system_prompt(show_name):
    return (
        f'You tag each episode of "{show_name}", a daily audio newscast, with the named things it covers, so listeners and search '
        "engines can find every newscast about the same company, organization, place or topic. Go through the script STORY BY STORY, "
        "in order, and then through the closing \"what to watch\" lines, which also name organizations and events. Do not skip a story.\n\n"
        "TAGS (for each story, list every tag that applies)\n"
        "- company: a business or vendor (software, services, publishers, edtech companies, investors).\n"
        "- organization: a non-profit, association, conference host, union, agency, court, regulator, legislature, university or "
        "research body. A conference or event named in the script counts through its host (OASBO, EDUCAUSE, CITE).\n"
        "- place: where a story happens. Give the CHAIN: the local place (district, school, city, college) with level \"local\"; its "
        "province or state with level \"region\"; its country with level \"country\", linking each to the next one up with `parent`. "
        "Always include the province or state of a story's place, even when the script names only the district, and the country when "
        "it is not the United States. Never tag the United States, and never tag \"America\".\n"
        "- topic: ONLY a topic from this fixed list, spelled exactly as written, and ONLY when the story is mainly about it as the "
        "definition says:\n" + _topic_lines() + "\n\n"
        "RULES\n"
        "- Every tag needs `quote`: ONE sentence copied EXACTLY, character for character, from the script that shows why the tag "
        "applies (at most 40 words). If you cannot copy a sentence that supports the tag, do not give the tag.\n"
        "- NEVER tag an individual person, and never a criminal group, ransomware gang or threat actor. Those names are an "
        "editorial decision and are not tags. Do not tag the show or its sponsor.\n"
        "- Use the common full name (Frontline Education, not Frontline; PowerSchool, not PowerSchool Group LLC; Federal "
        "Communications Commission, not FCC). The user message lists names already in use: when a tag is the same thing as one of them, "
        "copy that spelling exactly.\n"
        "- note: ONE factual sentence, at most 35 words, saying what this episode reported about the tag. Use only what the script says. "
        "No opinion, no names of individuals, no hype, no URLs. For a place or organization that is only named in the calendar, say what "
        "is scheduled.\n"
        f"- {K12_PROMPT_RULE}"
    )


def build_user_message(episode_date, script, known):
    names = sorted(known) if known else []
    listing = "\n".join(f"- {name}" for name in names) if names else "(none yet)"
    return f"Episode date: {episode_date}\n\nNAMES ALREADY IN USE (reuse the spelling exactly when they fit):\n{listing}\n\nSCRIPT:\n{script}"


_TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "kind": {"type": "string", "enum": list(KINDS)},
        "level": {"type": "string", "enum": list(LEVELS) + [""]},
        "parent": {"type": "string"},
        "quote": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["name", "kind", "level", "parent", "quote", "note"],
    "additionalProperties": False,
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"summary": {"type": "string"}, "tags": {"type": "array", "items": _TAG_SCHEMA}},
                "required": ["summary", "tags"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["stories"],
    "additionalProperties": False,
}

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "keep": {"type": "boolean"}, "note": {"type": "string"}},
                "required": ["id", "keep", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["decisions"],
    "additionalProperties": False,
}


# ------------------------------------------------------------------ checking what the model returned


def _clean_note(note):
    note = re.sub(r"\s+", " ", str(note or "")).strip()
    if re.search(r"https?://", note):
        return ""
    if len(note) > MAX_NOTE_CHARS:
        note = note[: MAX_NOTE_CHARS - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return note


def _tag(name, kind, note="", parent="", level="", evidence=""):
    return {"name": name, "slug": slugify(name), "kind": kind, "note": note, "parent": parent, "level": level, "evidence": evidence}


def flatten_and_verify(raw, script, known=None, dropped=None):
    """The model's per-story tags as one deduplicated list. Every tag has a verified quote and a supported name, topics are on the
    fixed list, known spellings are restored. Anything that fails is dropped and (when `dropped` is a list) recorded."""
    known = known or {}
    by_slug = {slugify(n): n for n in known}
    script_n = norm(script)
    tags, order = {}, []

    def drop(name, why):
        logger.info("Dropped tag %r: %s", name, why)
        if dropped is not None:
            dropped.append((name, why))

    for story in (raw or {}).get("stories") or []:
        for item in story.get("tags") or []:
            name = re.sub(r"\s+", " ", str(item.get("name") or "")).strip()
            kind = item.get("kind")
            slug = slugify(name)
            quote = str(item.get("quote") or "").strip()
            if not name or not slug or kind not in KINDS or len(name) > MAX_NAME_CHARS:
                drop(name, "malformed")
                continue
            if slug in gazetteer.NEVER_TAG:
                continue
            if kind == "topic":
                if slug not in TOPIC_BY_SLUG:
                    drop(name, "topic is not on the fixed list")
                    continue
                name = TOPIC_BY_SLUG[slug]
            elif slug in by_slug:
                name = by_slug[slug]
            if not quote_in_script(quote, script_n):
                drop(name, "its quote is not in the script")
                continue
            level = item.get("level") if item.get("level") in LEVELS else ""
            if kind != "topic" and not inferred_place(name, kind, level) and not name_supported(name, quote):
                drop(name, "its quote does not name it")
                continue
            parent = slugify(str(item.get("parent") or "")) if kind == "place" else ""
            if kind == "place" and not level:
                level = gazetteer.place_level(name)
            if slug in tags:
                existing = tags[slug]
                note = _clean_note(item.get("note"))
                if note and note not in existing["note"] and len(existing["note"]) + len(note) + 1 <= MAX_NOTE_CHARS:
                    existing["note"] = (existing["note"] + " " + note).strip()
                if not existing["parent"] and parent:
                    existing["parent"] = parent
                continue
            tags[slug] = _tag(name, kind, _clean_note(item.get("note")), parent, level if kind == "place" else "", quote)
            order.append(slug)
    return [tags[s] for s in order]


def apply_place_chain(tags):
    """Gazetteer places get their gazetteer parent and level (British Columbia sits under Canada); a place whose parent is named
    but not tagged gets the parent as a tag too, with the child's sentence as its evidence. The home country is never a parent."""
    gaz = {name: (parent, level) for name, _kind, parent, level in gazetteer.places()}
    gaz_by_slug = {slugify(name): name for name in gaz}
    by_slug = {t["slug"]: t for t in tags}

    def ensure_parent(child):
        parent = child["parent"]
        if not parent:
            return
        if parent in gazetteer.NEVER_TAG or parent == child["slug"]:
            child["parent"] = ""
            return
        if parent in by_slug:
            return
        name = gaz_by_slug.get(parent) or parent.replace("-", " ").title()
        grand, level = gaz.get(name, (None, "region"))
        added = _tag(name, "place", "", slugify(grand) if grand else "", level, child["evidence"])
        tags.append(added)
        by_slug[added["slug"]] = added
        ensure_parent(added)

    for tag in list(tags):
        if tag["kind"] != "place":
            continue
        if tag["name"] in gaz:
            parent_name, level = gaz[tag["name"]]
            tag["level"] = level
            if parent_name:
                tag["parent"] = slugify(parent_name)
        ensure_parent(tag)
    return tags


# ------------------------------------------------------------------ the name scan


def _sentences(script):
    flat = re.sub(r"\s*\n+\s*", " ", script)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'“])", flat) if s.strip()]


def scan_names(known=None):
    """[(spoken form, canonical name, kind, parent_name, level)] to look for in every script."""
    out = []
    for name, kind, parent, level in gazetteer.places():
        out.append((name, name, kind, parent, level))
    for spoken, canonical in gazetteer.PLACE_ALIASES.items():
        out.append((spoken, canonical, "place", gazetteer.place_parent(canonical), gazetteer.place_level(canonical)))
    for spoken, canonical in gazetteer.ORG_ALIASES.items():
        out.append((spoken, canonical, "organization", None, ""))
    for name, kind in (known or {}).items():
        if kind in ("company", "organization", "place") and len(name) >= 4:
            out.append((name, name, kind, None, "local" if kind == "place" else ""))
    return out


def gazetteer_candidates(script, tags, known=None):
    """Names the script says that the model did not tag: [{id, name, kind, parent, level, sentence}], at most MAX_CANDIDATES."""
    have = {t["slug"] for t in tags}
    sentences = _sentences(script)
    candidates, seen = [], set()
    for spoken, canonical, kind, parent, level in scan_names(known):
        slug = slugify(canonical)
        if slug in have or slug in seen or slug in gazetteer.NEVER_TAG:
            continue
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(spoken) + r"(?![A-Za-z0-9])")
        hit = next((s for s in sentences if pattern.search(s)), None)
        if hit is None:
            continue
        seen.add(slug)
        candidates.append({"id": len(candidates), "name": canonical, "kind": kind, "parent": parent or "", "level": level, "sentence": hit})
        if len(candidates) >= MAX_CANDIDATES:
            break
    return candidates


def build_verify_prompt():
    return (
        "You confirm names found by a text search of a news script. Each candidate is a place or organization name and the sentence "
        "where it was found. Say keep=true only when the sentence is really about THAT place or organization, in a news story or in "
        "the schedule of upcoming events. keep=false when the match is a different thing (the state of Washington versus a "
        "Washington-based company's name or the city; the country Georgia versus the state; the New York Times is not New York; a "
        "person's surname; a sponsor message). For each kept candidate give `note`: ONE factual sentence, at most 35 words, saying what "
        "the script reports about it, using only the sentence given. No opinion, no names of individuals, no URLs. "
        f"{K12_PROMPT_RULE}"
    )


def verify_candidates(anthropic_generate, candidates):
    if not candidates:
        return []
    listing = "\n".join(f'{c["id"]} | {c["name"]} ({c["kind"]}) | {c["sentence"]}' for c in candidates)
    text = anthropic_generate(system=build_verify_prompt(), user_content=listing, tools=[], response_schema=VERIFY_SCHEMA)
    decisions = {d["id"]: d for d in json.loads(text).get("decisions") or [] if isinstance(d, dict) and "id" in d}
    kept = []
    for candidate in candidates:
        decision = decisions.get(candidate["id"])
        if decision and decision.get("keep"):
            kept.append(dict(candidate, note=_clean_note(decision.get("note"))))
    return kept


# ------------------------------------------------------------------ putting it together

_PRIORITY = {"topic": 0, "company": 1, "organization": 2, "place": 3}


def _sort_key(tag):
    place_rank = {"country": 0, "region": 1, "local": 2}.get(tag.get("level"), 2) if tag["kind"] == "place" else 0
    return (_PRIORITY[tag["kind"]], place_rank)


def extract_entities(anthropic_generate, show_name, episode_date, final_script, known=None, report=None):
    """The episode's tags. `known` maps names already in use to their kind (a bare list of names also works). `report`, when a dict,
    receives {'dropped': [...], 'scanned': [...], 'model': n} for the audit."""
    known = dict.fromkeys(known, "") if known and not isinstance(known, dict) else (known or {})
    script = spoken_script(final_script)
    if not script:
        raise ValueError("the script has no spoken text to tag")
    text = anthropic_generate(
        system=build_system_prompt(show_name),
        user_content=build_user_message(episode_date, script, list(known)),
        tools=[],
        response_schema=RESPONSE_SCHEMA,
    )
    dropped = []
    tags = flatten_and_verify(json.loads(text), script, known, dropped)
    model_count = len(tags)

    added = []
    try:
        candidates = gazetteer_candidates(script, tags, known)
        for kept in verify_candidates(anthropic_generate, candidates):
            tags.append(_tag(kept["name"], kept["kind"], kept["note"], slugify(kept["parent"]) if kept["parent"] else "",
                             kept["level"] if kept["kind"] == "place" else "", kept["sentence"]))
            added.append(kept["name"])
    except Exception:    # the scan only adds; a failure leaves the model's tags as they are
        logger.warning("The name scan failed; keeping the model's tags only.", exc_info=True)

    tags = apply_place_chain(tags)
    tags.sort(key=_sort_key)
    tags = tags[:MAX_ENTITIES]
    if not tags:
        raise ValueError("no usable tags")
    if isinstance(report, dict):
        report.update({"dropped": dropped, "scanned": added, "model": model_count})
    return tags


def known_entity_kinds(episodes, exclude_id=None):
    """name -> kind for every tag already stored on the show's episodes, most used first."""
    counts, kinds = {}, {}
    for episode in episodes or []:
        if exclude_id and episode.get("id") == exclude_id:
            continue
        for entity in (episode.get("meta") or {}).get("ng_entities") or []:
            if isinstance(entity, dict) and entity.get("name"):
                counts[entity["name"]] = counts.get(entity["name"], 0) + 1
                kinds[entity["name"]] = entity.get("kind") or ""
    return {name: kinds[name] for name, _n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))}


def known_entity_names(episodes, exclude_id=None):
    return list(known_entity_kinds(episodes, exclude_id))


def ensure_entities(wp, anthropic_generate, show, episode_id, force=False):
    """Tags the episode if it has no tags yet (or force). Never raises; returns the stored tags or None."""
    try:
        episode = wp.get_episode(episode_id)
        meta = episode.get("meta", {}) or {}
        if meta.get("ng_entities") and not force:
            return meta["ng_entities"]
        if not meta.get("ng_script_final"):
            return None
        known = known_entity_kinds(wp.list_episodes_for_show(show["id"]), exclude_id=episode_id)
        entities = extract_entities(anthropic_generate, show["name"], meta.get("ng_episode_date", ""), meta["ng_script_final"], known)
        wp.update_episode_meta(episode_id, {"ng_entities": entities})
        logger.info("Tagged episode %s: %s", episode_id, ", ".join(e["name"] for e in entities))
        return entities
    except Exception:    # enrichment only: a failure must never hold up a publish
        logger.warning("Could not tag episode %s with topics; it publishes without them.", episode_id, exc_info=True)
        return None
