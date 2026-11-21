"""
What the pipeline posts to a show's LinkedIn page (2026-11-20). Pure functions only: no network, no WordPress.

The post is the episode's show notes (the same text Captivate gets, without the "Stories & links" section and without the
sponsor footer), opened with "Today in edtech:" on its own line and closed with an invitation to listen and the link to the
episode's page on the website. The link is also attached as an article card (title, summary, picture) because LinkedIn's
API does not build a preview from a bare link in the text.

Hashtags close the post: the show's own tags (a setting on the show, for example education, edtech, K12) always come first, then
tags for the episode's topics, up to five in all. Each is written in LinkedIn's hashtag markup so it is a real, clickable hashtag.

LinkedIn's post text is a "little text format": a handful of characters (| { } @ [ ] ( ) < > # \\ * _ ~) mean mentions,
hashtags and formatting, and an unescaped one can cut the post off at that point. Every one is escaped with a backslash.
"""

import html
import re

INTRO = "Today in edtech:"
INVITATION = "Listen to today's episode:"

# LinkedIn's limit for a post's text is 3,000 characters.
COMMENTARY_LIMIT = 3000

_RESERVED = "\\|{}@[]()<>#*_~"
_STORIES_HEADER = re.compile(r"^\s*stories\s*(?:&|and)\s*links\b", re.IGNORECASE)
_PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


# LinkedIn recommends three to five hashtags; more reads as spam.
MAX_HASHTAGS = 5

# Extra hashtags for the episode's topics (the fixed topic list in entities.TOPICS, keyed by the topic's slug). A topic with no
# entry adds nothing. The show's own tags are never displaced by these.
TOPIC_HASHTAGS = {
    "k-12-ai-policy": ["AI"],
    "ransomware-attacks-on-schools": ["cybersecurity"],
    "student-data-privacy": ["dataprivacy"],
    "e-rate-program": ["ERate"],
    "edtech-mergers-and-acquisitions": ["MergersAndAcquisitions"],
    "edtech-stocks-and-earnings": ["stockmarket"],
    "edtech-funding-and-investment": ["VentureCapital"],
    "student-online-safety": ["onlinesafety"],
}


class LinkedInPostError(RuntimeError):
    pass


def clean_hashtag(raw):
    """A hashtag's word: letters, digits and underscores only (no #, no hyphen: K-12 is K12), or '' when nothing is left."""
    return re.sub(r"[^A-Za-z0-9_]", "", str(raw or "").replace("\u2011", ""))[:30]


def choose_hashtags(base, entities, limit=MAX_HASHTAGS):
    """The show's own tags first (all of them, even past the limit), then tags for the episode's topics until the limit; no repeats (any case)."""
    chosen, seen = [], set()

    def add(word):
        word = clean_hashtag(word)
        if word and word.lower() not in seen:
            seen.add(word.lower())
            chosen.append(word)

    for word in base or []:
        add(word)
    for entity in entities or []:
        if len(chosen) >= limit:
            break
        if isinstance(entity, dict) and entity.get("kind") == "topic":
            for word in TOPIC_HASHTAGS.get(entity.get("slug"), []):
                if len(chosen) < limit:
                    add(word)
    return chosen


def hashtag_markup(word):
    return "{hashtag|\\#|" + word + "}"


def _plain(fragment):
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    text = html.unescape(_TAG.sub("", fragment))
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def notes_paragraphs(notes_html):
    """The show notes' story paragraphs as plain text, in order, stopping at the "Stories & links" header."""
    notes_html = notes_html or ""
    found = _PARAGRAPH.findall(notes_html)
    out = []
    if found:
        for fragment in found:
            text = _plain(fragment)
            if _STORIES_HEADER.match(text):
                break
            if text:
                out.append(text)
        return out
    # Notes without paragraph tags (hand-edited): split on blank lines and cut at the header the same way.
    for block in re.split(r"\n\s*\n", re.sub(r"<br\s*/?>", "\n", notes_html, flags=re.IGNORECASE)):
        text = _plain(block)
        if _STORIES_HEADER.match(text):
            break
        if text:
            out.append(text)
    return out


def escape_commentary(text):
    return "".join("\\" + ch if ch in _RESERVED else ch for ch in text)


def build_commentary(paragraphs, url, hashtags=(), intro=INTRO, invitation=INVITATION, limit=COMMENTARY_LIMIT):
    """
    The post text. Whole paragraphs are dropped from the end, never cut mid-sentence, until it fits the limit; the opening
    line, the closing link and the hashtags are always kept. Raises if not even one paragraph fits.
    """
    hashtags = [word for word in (clean_hashtag(w) for w in hashtags or ()) if word]
    if not url:
        raise LinkedInPostError("The episode has no website page address to link to.")
    if not paragraphs:
        raise LinkedInPostError("The episode's show notes have no story paragraphs to post.")

    def assemble(chosen):
        body = "\n\n".join(escape_commentary(p) for p in chosen)
        tags = "\n\n" + " ".join(hashtag_markup(word) for word in hashtags) if hashtags else ""
        return f"{escape_commentary(intro)}\n\n{body}\n\n{escape_commentary(invitation)}\n{escape_commentary(url)}{tags}"

    chosen = list(paragraphs)
    while len(chosen) > 1 and len(assemble(chosen)) > limit:
        chosen.pop()
    text = assemble(chosen)
    if len(text) > limit:
        raise LinkedInPostError("The first show-notes paragraph alone is too long for a LinkedIn post.")
    return text


def author_urn(page_id):
    return f"urn:li:organization:{int(page_id)}"


def post_payload(author, commentary, url, title, description, thumbnail_urn=None):
    """The body for POST /rest/posts: a public post on the page's feed with the episode page attached as an article card."""
    article = {"source": url, "title": title or "", "description": description or ""}
    if thumbnail_urn:
        article["thumbnail"] = thumbnail_urn
    return {
        "author": author,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "content": {"article": article},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }


def post_mentions_episode(post, url):
    """True when a listed post is the one made for this episode page (its card points at the page, or its text names it)."""
    source = (((post.get("content") or {}).get("article")) or {}).get("source") or ""
    if source.rstrip("/") == url.rstrip("/"):
        return True
    return url.rstrip("/") in (post.get("commentary") or "").replace("\\", "")
