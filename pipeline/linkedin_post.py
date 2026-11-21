"""
What the pipeline posts to a show's LinkedIn page (2026-11-20). Pure functions only: no network, no WordPress.

The post is the episode's show notes (the same text Captivate gets, without the "Stories & links" section and without the
sponsor footer), opened with "Today in edtech:" on its own line and closed with an invitation to listen and the link to the
episode's page on the website. The link is also attached as an article card (title, summary, picture) because LinkedIn's
API does not build a preview from a bare link in the text.

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


class LinkedInPostError(RuntimeError):
    pass


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


def build_commentary(paragraphs, url, intro=INTRO, invitation=INVITATION, limit=COMMENTARY_LIMIT):
    """
    The post text. Whole paragraphs are dropped from the end, never cut mid-sentence, until it fits the limit; the opening
    line and the closing link are always kept. Raises if not even one paragraph fits.
    """
    if not url:
        raise LinkedInPostError("The episode has no website page address to link to.")
    if not paragraphs:
        raise LinkedInPostError("The episode's show notes have no story paragraphs to post.")

    def assemble(chosen):
        body = "\n\n".join(escape_commentary(p) for p in chosen)
        return f"{escape_commentary(intro)}\n\n{body}\n\n{escape_commentary(invitation)}\n{escape_commentary(url)}"

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
