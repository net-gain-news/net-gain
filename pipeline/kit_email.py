"""
The emails Kit sends for a show (2026-11-06): one per episode (the daily email) and one roundup a week.

This replaces Kit's RSS-to-email automations. Those poll the website's email feed on Kit's own schedule (15 to 46 minutes
after an episode appeared, on the days checked) and then hold every draft for a fixed 30 minutes before sending. Here the
pipeline makes the broadcast itself, the moment the episode is live, so the email arrives within a couple of minutes.

The cards are not built here. The plugin already renders them (net-gain-studio/includes/class-email-feed.php) for the show's
email feed: <content:encoded> is the full daily card, <description> the compact card used in the weekly roundup, and
<ng:summary> the plain-text summary used for the inbox preview line. This module reads that feed and wraps what it finds
in a Kit broadcast, in the show's own Kit HTML layout template (Denim header, Index block, footer).

Pure functions only (no network, no WordPress) except fetch_feed(), so the rules are unit-testable.
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

import text_rules

NS = {"content": "http://purl.org/rss/1.0/modules/content/", "ng": "https://netgain.news/ns/email"}
UA = {"User-Agent": "NetGainStudio-Pipeline/1.0 (+https://netgain.news)"}

# Kit schedules a broadcast for a time, so "now" is a moment shortly ahead. Kit's own RSS automation uses 30 minutes; the
# pipeline does not need that cushion (the episode page, audio and thumbnail were all verified live before this step runs).
SEND_LEAD_SECONDS = 90

# The inbox preview line Kit shows after the subject. Kit allows 150 characters.
PREVIEW_LIMIT = 140

# A weekly roundup is sent if the pipeline is up within this long after its slot. Later than that and the slot is skipped
# (and the operator told) rather than sending a Monday-morning email on Monday night.
WEEKLY_LATE_LIMIT = timedelta(hours=6)

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

# Daily emails older than this are not sent automatically (Kit sending was down for over a day): a day-old "latest episode"
# email, sent after the next episode is already out, would be wrong rather than late.
DAILY_STALE_AFTER = timedelta(hours=36)


class KitEmailError(RuntimeError):
    pass


# --- reading the show's email feed ----------------------------------------------------------

def parse_feed(xml_text):
    """The feed's items, newest first: dicts with title, link, published (aware UTC datetime), summary, daily_card, compact_card."""
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall("channel/item"):
        pub_raw = (item.findtext("pubDate") or "").strip()
        try:
            published = datetime.strptime(pub_raw, "%a, %d %b %Y %H:%M:%S %z").astimezone(timezone.utc)
        except ValueError:
            continue  # an item without a readable time cannot be placed in a week or matched to an episode
        items.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "published": published,
                "summary": (item.findtext("ng:summary", namespaces=NS) or "").strip(),
                "daily_card": item.findtext("content:encoded", namespaces=NS) or "",
                "compact_card": item.findtext("description") or "",
            }
        )
    return items


def fetch_feed(feed_url, now=None, session=None):
    """Fetches and parses the show's email feed, bypassing the host's cache so a just-published episode is in it."""
    if not feed_url:
        raise KitEmailError("The show has no email feed address.")
    stamp = int((now or datetime.now(timezone.utc)).timestamp())
    response = (session or requests).get(feed_url, params={"cb": stamp}, headers=UA, timeout=30)
    if response.status_code != 200:
        raise KitEmailError(f"The email feed returned {response.status_code}: {feed_url}")
    return parse_feed(response.content)


def _same_page(a, b):
    return (a or "").rstrip("/") == (b or "").rstrip("/")


def item_for_page(items, permalink):
    """The feed item for the episode page at `permalink`, or None."""
    for item in items:
        if _same_page(item["link"], permalink):
            return item
    return None


# --- shared pieces ------------------------------------------------------------------------

def iso_utc(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def send_time(now):
    """When to tell Kit to send: a moment shortly after now, as an ISO UTC string."""
    return iso_utc(now + timedelta(seconds=SEND_LEAD_SECONDS))


def preview_text(summary, limit=PREVIEW_LIMIT):
    """The inbox preview line: the episode summary on one line, cut at a word boundary with an ellipsis if too long."""
    text = re.sub(r"\s+", " ", text_rules.apply_text_rules(summary or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-–—")
    return cut + "…"


def episode_marker(episode_id):
    return f"[ng-ep-{int(episode_id)}]"


def weekly_marker(show_id, slot_key):
    return f"[ng-week-{int(show_id)}-{slot_key}]"


# --- the daily email ---------------------------------------------------------------------------

def daily_payload(kit, show_name, episode, item, now):
    """
    Keyword arguments for KitClient.create_broadcast for one episode's daily email.
    `episode` is the WordPress episode record (id, meta); `item` is its feed item.
    """
    episode_id = episode["id"]
    episode_date = (episode.get("meta") or {}).get("ng_episode_date") or item["published"].date().isoformat()
    return {
        "subject": text_rules.apply_text_rules(item["title"]),
        "preview_text": preview_text(item["summary"]),
        "description": f"{show_name} daily {episode_date} {episode_marker(episode_id)}",
        "content": item["daily_card"],
        "template_id": kit["daily_template_id"],
        "tag_id": kit["daily_tag_id"],
        "send_at": send_time(now),
        "published_at": iso_utc(item["published"]),
        "email_address": kit.get("from_email") or "",
    }


def check_daily_settings(kit):
    """Returns a plain-language problem with the show's daily Kit settings, or None if they are complete."""
    missing = []
    if not kit.get("daily_tag_id"):
        missing.append("the daily Kit tag ID")
    if not kit.get("daily_template_id"):
        missing.append("the daily Kit layout template ID")
    if not kit.get("feed_url"):
        missing.append("the email feed address")
    return f"Kit sending is on but {', '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set on the show setup screen." if missing else None


def settings_problems(kit, tags, templates):
    """
    What is wrong with a show's Kit settings when checked against the account's real tags and templates (lists of Kit
    records with an 'id'). An empty list means the settings can be used.
    """
    tag_ids = {int(t["id"]) for t in tags}
    template_ids = {int(t["id"]) for t in templates}
    problems = []
    daily = check_daily_settings(kit)
    if daily:
        problems.append(daily)
    else:
        if kit["daily_tag_id"] not in tag_ids:
            problems.append(f"The daily tag ID {kit['daily_tag_id']} is not a tag in this Kit account.")
        if kit["daily_template_id"] not in template_ids:
            problems.append(f"The daily layout template ID {kit['daily_template_id']} is not an email template in this Kit account.")
    weekly = check_weekly_settings(kit)
    if weekly:
        problems.append(weekly)
    elif weekly is None:
        if kit["weekly_tag_id"] not in tag_ids:
            problems.append(f"The weekly tag ID {kit['weekly_tag_id']} is not a tag in this Kit account.")
        if kit["weekly_template_id"] not in template_ids:
            problems.append(f"The weekly layout template ID {kit['weekly_template_id']} is not an email template in this Kit account.")
    return problems


# --- the weekly roundup ------------------------------------------------------------------------

def _slot_at(zone, day_index, hh_mm, on_or_before_local):
    """The latest occurrence of (weekday, wall-clock time) in `zone` that is not after `on_or_before_local`."""
    hour, minute = (int(part) for part in hh_mm.split(":"))
    days_back = (on_or_before_local.weekday() - day_index) % 7
    day = on_or_before_local.date() - timedelta(days=days_back)
    slot = datetime.combine(day, dtime(hour, minute), tzinfo=zone)
    if slot > on_or_before_local:
        slot = datetime.combine(day - timedelta(days=7), dtime(hour, minute), tzinfo=zone)
    return slot


def weekly_slots(kit, now):
    """
    (slot_start, previous_slot_start) for the most recent weekly send time at or before `now`, as aware datetimes in the show's
    zone. The time is a wall-clock time in a named zone, so it keeps its local hour through daylight saving changes.
    """
    zone = ZoneInfo(kit["weekly_timezone"])
    day_index = WEEKDAYS[kit["weekly_day"]]
    local_now = now.astimezone(zone)
    slot = _slot_at(zone, day_index, kit["weekly_time"], local_now)
    previous = _slot_at(zone, day_index, kit["weekly_time"], slot - timedelta(seconds=1))
    return slot, previous


def slot_key(slot):
    """The stable identity of a weekly send: its local date and time with offset, e.g. 2026-11-09T08:00:00-05:00."""
    return slot.isoformat()


def check_weekly_settings(kit):
    """None when the weekly roundup is configured, else why not (an empty string means 'simply switched off')."""
    if not kit.get("weekly_day"):
        return ""
    missing = []
    if not kit.get("weekly_tag_id"):
        missing.append("the weekly Kit tag ID")
    if not kit.get("weekly_template_id"):
        missing.append("the weekly Kit layout template ID")
    if not kit.get("feed_url"):
        missing.append("the email feed address")
    if missing:
        return f"The weekly roundup is scheduled but {', '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set on the show setup screen."
    return None


def weekly_state(kit, now):
    """
    What the weekly roundup should do right now, as (state, slot, previous_slot):
      'off'       not configured
      'handled'   this slot was already sent (or consciously skipped)
      'baseline'  nothing has ever been handled for this show: note the current slot as handled WITHOUT sending, so switching
                  the roundup on never sends a catch-up (the previous system sent that week's) or raises a false alarm
      'missed'    the pipeline was not running for more than WEEKLY_LATE_LIMIT after the slot: skip it and tell the operator
      'due'       send it
    """
    problem = check_weekly_settings(kit)
    if problem is not None:
        return "off", None, None
    slot, previous = weekly_slots(kit, now)
    last = kit.get("weekly_last_slot") or ""
    if slot_key(slot) == last:
        return "handled", slot, previous
    if not last:
        return "baseline", slot, previous
    if now - slot.astimezone(timezone.utc) > WEEKLY_LATE_LIMIT:
        return "missed", slot, previous
    return "due", slot, previous


def episodes_in_window(items, previous_slot, slot):
    """Feed items published after the previous send and up to this one (a week, newest first)."""
    start, end = previous_slot.astimezone(timezone.utc), slot.astimezone(timezone.utc)
    return [item for item in items if start < item["published"] <= end]


def weekly_body(items):
    """
    The roundup's body: each episode's compact card, newest first, stacked. The same shape Kit's own digest produced (one
    block per episode inside a single full-width table), so the weekly layout template renders it exactly as before.
    """
    blocks = "".join(f"\n<div>\n{item['compact_card']}\n</div>" for item in items)
    return f'<table cellpadding="0" cellspacing="0" style="width:100%;margin:0 auto"><tbody><tr><td>{blocks}\n</td></tr></tbody></table>'


def weekly_payload(kit, show, items, slot, now):
    """Keyword arguments for KitClient.create_broadcast for the weekly roundup of `items` (already the week's, newest first)."""
    newest = items[0]
    return {
        # Kit's own digest used the show's name as the subject; so does this.
        "subject": text_rules.apply_text_rules(show["name"]),
        "preview_text": preview_text(newest["summary"]),
        "description": f"{show['name']} weekly {slot.date().isoformat()} {weekly_marker(show['id'], slot_key(slot))}",
        "content": weekly_body(items),
        "template_id": kit["weekly_template_id"],
        "tag_id": kit["weekly_tag_id"],
        "send_at": send_time(now),
        "published_at": iso_utc(now),
        "email_address": kit.get("from_email") or "",
    }
