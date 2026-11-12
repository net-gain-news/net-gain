"""
Manual posting to Captivate (see captivate_mode.py): the email that hands an episode's ingredients to the operator, and the
matching of the episode they post in the dashboard back to our own record. Pure functions, no network.
"""
import html
import re

DASHBOARD_URL = "https://my.captivate.fm"


def extract_episodes(response):
    """The episode list out of GET /shows/{id}/episodes, whatever shape it comes in."""
    if isinstance(response, list):
        return [e for e in response if isinstance(e, dict)]
    if isinstance(response, dict):
        for key in ("episodes", "data"):
            value = response.get(key)
            if isinstance(value, list):
                return [e for e in value if isinstance(e, dict)]
    return []


def normalize_title(title):
    """Case, spacing, curly quotes and HTML entities must not decide whether two titles are the same."""
    text = html.unescape(str(title or ""))
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("‑", "-")
    return re.sub(r"\s+", " ", text).strip().casefold()


def find_posted_episode(episodes, title):
    """
    The Captivate episode the operator posted for this title: every episode whose normalised title equals ours.
    Returns (matches, ...) as a list so the caller can tell none, one and several apart.
    """
    wanted = normalize_title(title)
    if not wanted:
        return []
    return [e for e in episodes if normalize_title(e.get("title")) == wanted]


def html_to_text(fragment):
    text = re.sub(r"(?is)<a\b[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", lambda m: f"{re.sub('<[^>]+>', '', m.group(2))} ({m.group(1)})", fragment or "")
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text)).strip()


def build_handoff_message(handoff):
    """
    (subject, plain_text, html) for the email that asks the operator to post one episode. `handoff` carries: show_name, date
    (the episode date), title, notes_html, audio_url, art_url (may be ""), episode_number, publish_now (bool), publish_at (the
    Captivate-zone date string), account_zone, check_slots (bool).
    """
    e = html.escape
    subject = f"Net Gain Studio: post {handoff['show_name']} for {handoff['date']} in Captivate"
    if handoff["publish_now"]:
        when_text = "Publish it now (leave the date as it is, status Published)."
    else:
        when_text = (f"Set the publish date and time to {handoff['publish_at']} ({handoff['account_zone']}) and the status to "
                     "Published. Captivate reads dates in that zone.")

    text = "\n".join([
        f"{handoff['show_name']}, {handoff['date']}: the episode is ready for you to post in Captivate ({DASHBOARD_URL}).",
        "",
        "1. Audio (192 kbps CBR, made for Captivate - use this file, not the original):",
        f"   {handoff['audio_url']}",
        "",
        "2. Title:",
        f"   {handoff['title']}",
        "",
        "3. Show notes (the links are part of the notes; copy this from the rendered email, not from this plain text):",
        html_to_text(handoff["notes_html"]),
        "",
        "4. Episode art (square, 3000 px):",
        f"   {handoff['art_url'] or '(none was made for this episode)'}",
        "",
        f"5. Episode number: {handoff['episode_number']}",
        f"6. {when_text}",
        "",
        "Leave the ad settings as Captivate offers them; do not add ads by hand.",
        "The pipeline checks Captivate every minute for an episode with exactly this title. Keep the title as it is above; if you "
        "must change it, tell Claude and the episode can be linked by hand.",
        "Once it finds the episode it publishes the website page, YouTube and the email as usual"
        + (", and checks the ad slots Captivate gave it, and emails you if they are not a dynamic post-roll." if handoff.get("check_slots") else "."),
    ])

    page = f"""<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5;color:#1f2a3a;max-width:640px">
<h2 style="margin:0 0 4px">Post {e(handoff['show_name'])} for {e(handoff['date'])} in Captivate</h2>
<p style="margin:0 0 16px;color:#555">Everything the episode needs is below. Open <a href="{DASHBOARD_URL}">Captivate</a>, add a new episode and fill it in.</p>
<ol style="padding-left:20px">
<li style="margin-bottom:14px"><b>Audio</b> (192 kbps CBR, made for Captivate; use this file, not your original):<br><a href="{e(handoff['audio_url'])}">{e(handoff['audio_url'])}</a></li>
<li style="margin-bottom:14px"><b>Title</b> (keep it exactly; the pipeline finds your episode by it):<br>
<span style="display:inline-block;margin-top:4px;padding:6px 10px;background:#eef2f7;border-radius:4px">{e(handoff['title'])}</span></li>
<li style="margin-bottom:14px"><b>Show notes</b> (select this block and paste it into the notes box; the links come with it):
<div style="margin-top:6px;padding:10px 12px;border:1px solid #d5dde8;border-radius:4px">{handoff['notes_html']}</div></li>
<li style="margin-bottom:14px"><b>Episode art</b> (square, 3000 px): {f'<a href="{e(handoff["art_url"])}">{e(handoff["art_url"])}</a>' if handoff['art_url'] else '(none was made for this episode)'}</li>
<li style="margin-bottom:14px"><b>Episode number:</b> {e(str(handoff['episode_number']))}</li>
<li style="margin-bottom:14px"><b>Publishing:</b> {e(when_text)}</li>
</ol>
<p>Leave the ad settings as Captivate offers them; do not add ads by hand.</p>
<p style="color:#555">The pipeline checks Captivate every minute for an episode with exactly this title. When it finds it, it publishes the website page, YouTube and the email as usual{', and checks the ad slots Captivate gave the episode (it emails you if they are not a dynamic post-roll)' if handoff.get('check_slots') else ''}. If you have to change the title, tell Claude and the episode can be linked by hand.</p>
</div>"""
    return subject, text, page


def build_reminder_message(show_name, date, title, minutes, found_status=None):
    """The nudge sent when the operator's episode has still not shown up (or showed up but is not Published)."""
    subject = f"Net Gain Studio: {show_name} for {date} is still waiting for its Captivate episode"
    if found_status:
        body = (f"An episode titled \"{title}\" exists in Captivate but its status is {found_status}, not Published, {minutes} minutes "
                "after the hand-off. The website page, YouTube and the email will not go out until it is Published. Open it in "
                "Captivate and publish it (check its date).")
    else:
        body = (f"No episode titled \"{title}\" has appeared in Captivate {minutes} minutes after the hand-off email. The website "
                "page, YouTube and the email are waiting for it. Post it in Captivate with exactly that title. If you already "
                "posted it under a different title, tell Claude and it will be linked by hand.")
    return subject, body
