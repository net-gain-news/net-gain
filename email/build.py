"""
Builds the two Kit layout templates (daily, weekly) in the Net Gain Edtech Denim look, plus local previews filled with the
real feed so they can be checked in a browser before importing into Kit (Settings > Email templates > Import code).

    python3 email/build.py            # writes kit/net-gain-edtech-daily.html, kit/net-gain-edtech-weekly.html and preview/*.html

A Kit layout wraps each email's body at {{ message_content }}. In the RSS automations that body is the "Post content" block:
{{ post.content }} for the daily email, {{ post.summary }} (one compact card per episode) for the weekly digest - both come
from the website's email feed (net-gain-studio/includes/class-email-feed.php), so the cards are styled there.
"""
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FEED = "https://netgain.news/series/edtech/feed/ng-email/"
LOGO = "https://netgain.news/wp-content/uploads/2026/10/net-gain-edtech-email-logo-460.png"
SITE = "https://netgain.news"

# Denim palette, as on the live site (header, page, cards)
NAVY, NAVY_LINK, PAGE, CARD, CARD_BORDER, INK, MUTED, ACCENT = "#1f2a3a", "#9fbbdb", "#e6dccc", "#efe7da", "#d6cab7", "#22293a", "#5f6470", "#2f5379"
HEAD = "'Archivo','Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = "'IBM Plex Mono','Courier New',Courier,monospace"
BODY = "'IBM Plex Sans','Helvetica Neue',Helvetica,Arial,sans-serif"

VARIANTS = {
    "daily": {"label": "Daily briefing", "title": "Net Gain Edtech daily briefing", "intro": ""},
    "weekly": {
        "label": "Weekly digest",
        "title": "Net Gain Edtech weekly digest",
        "intro": f"""
              <tr><td style="padding:0 0 6px;font-family:{MONO};font-size:10px;line-height:12px;letter-spacing:0.12em;text-transform:uppercase;color:{MUTED};">This week on Net Gain Edtech</td></tr>
              <tr><td style="padding:0 0 10px;font-family:{HEAD};font-size:30px;line-height:34px;font-weight:700;letter-spacing:-0.02em;color:{INK};">Your week in K&#8209;12 edtech.</td></tr>
              <tr><td style="padding:0 0 26px;font-family:{BODY};font-size:16px;line-height:25px;color:{MUTED};">Every episode from the past week in one place. Listen, read the transcript, or open the episode page for the show notes and sources.</td></tr>""",
    },
}


def layout(kind):
    v = VARIANTS[kind]
    intro_block = ""
    if v["intro"]:
        intro_block = f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{v["intro"]}\n            </table>'
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{v["title"]}</title>
<style type="text/css">
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;700&family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:wght@400;500&display=swap');
body {{ margin:0; padding:0; background:{PAGE}; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
table {{ border-collapse:collapse; mso-table-lspace:0; mso-table-rspace:0; }}
img {{ border:0; outline:none; text-decoration:none; -ms-interpolation-mode:bicubic; }}
a {{ color:{ACCENT}; }}
@media only screen and (max-width:620px) {{
  .ng-outer {{ padding:0 !important; }}
  .ng-wrap {{ width:100% !important; max-width:100% !important; }}
  .ng-pad {{ padding-left:20px !important; padding-right:20px !important; }}
  .ng-thumb {{ display:block !important; width:100% !important; padding:0 0 14px 0 !important; }}
  .ng-thumb img {{ width:100% !important; }}
  .ng-copy {{ display:block !important; width:100% !important; }}
  .ng-logo {{ width:190px !important; height:auto !important; }}
}}
</style>
</head>
<body style="margin:0;padding:0;background:{PAGE};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{PAGE}" style="background:{PAGE};">
  <tr>
    <td class="ng-outer" align="center" style="padding:28px 12px;">
      <table role="presentation" class="ng-wrap" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;">

        <!-- Header: the show logo on the Denim navy bar, as on the website -->
        <tr>
          <td class="ng-pad" bgcolor="{NAVY}" style="background:{NAVY};padding:24px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td align="left" valign="middle"><a href="{SITE}/edtech/"><img class="ng-logo" src="{LOGO}" width="230" height="21" alt="Net Gain Edtech" style="display:block;width:230px;height:auto;"></a></td>
                <td align="right" valign="middle" style="font-family:{MONO};font-size:10px;line-height:12px;letter-spacing:0.12em;text-transform:uppercase;color:{NAVY_LINK};">{v["label"]}</td>
              </tr>
            </table>
          </td>
        </tr>
        <tr><td height="4" bgcolor="{ACCENT}" style="height:4px;line-height:4px;font-size:0;background:{ACCENT};">&nbsp;</td></tr>

        <!-- Body: Kit puts the email content here -->
        <tr>
          <td class="ng-pad" bgcolor="{CARD}" style="background:{CARD};padding:34px 32px 8px;border-left:1px solid {CARD_BORDER};border-right:1px solid {CARD_BORDER};">
            {intro_block}
            {{{{ message_content }}}}
          </td>
        </tr>

        <!-- The Net Gain Edtech Index -->
        <tr>
          <td class="ng-pad" bgcolor="{CARD}" style="background:{CARD};padding:12px 32px 34px;border-left:1px solid {CARD_BORDER};border-right:1px solid {CARD_BORDER};">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid {CARD_BORDER};background:{PAGE};">
              <tr>
                <td style="padding:22px 24px;">
                  <div style="font-family:{MONO};font-size:10px;line-height:12px;letter-spacing:0.12em;text-transform:uppercase;color:{MUTED};padding:0 0 8px;">The Net Gain Edtech Index</div>
                  <div style="font-family:{BODY};font-size:15px;line-height:23px;color:{INK};padding:0 0 12px;">A proprietary portfolio of fifty publicly traded edtech companies, tracked on every episode.</div>
                  <a href="{SITE}/edtech/index/" style="font-family:{MONO};font-size:12px;line-height:16px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:{ACCENT};text-decoration:none;">See how the Index moved &rarr;</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td class="ng-pad" bgcolor="{NAVY}" style="background:{NAVY};padding:26px 32px 30px;">
            <div style="font-family:{BODY};font-size:14px;line-height:22px;color:#c9d4e3;padding:0 0 14px;">Net Gain Edtech is brought to you by <a href="https://www.edsby.com/" style="color:{NAVY_LINK};text-decoration:underline;">Edsby</a>, the digital learning platform for K&#8209;12.</div>
            <div style="font-family:{MONO};font-size:11px;line-height:16px;letter-spacing:0.08em;text-transform:uppercase;padding:0 0 18px;">
              <a href="{SITE}/edtech/" style="color:{NAVY_LINK};text-decoration:none;">Website</a>&nbsp;&nbsp;<span style="color:#4d6585;">|</span>&nbsp;&nbsp;<a href="{SITE}/edtech/episodes/" style="color:{NAVY_LINK};text-decoration:none;">All episodes</a>&nbsp;&nbsp;<span style="color:#4d6585;">|</span>&nbsp;&nbsp;<a href="https://net-gain-edtech.captivate.fm/listen" style="color:{NAVY_LINK};text-decoration:none;">Follow the show</a>
            </div>
            <div style="font-family:{BODY};font-size:12px;line-height:19px;color:#8fa3bd;">
              You&rsquo;re receiving this because you subscribed to Net Gain Edtech.<br>
              <a href="{{{{ unsubscribe_url }}}}" style="color:{NAVY_LINK};text-decoration:underline;">Unsubscribe</a> &nbsp;|&nbsp; <a href="{{{{ subscriber_preferences_url }}}}" style="color:{NAVY_LINK};text-decoration:underline;">Update your preferences</a><br>
              {{{{ address }}}}
            </div>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""


def fetch_items():
    import time
    req = urllib.request.Request(FEED + f"?cb={int(time.time())}", headers={"User-Agent": "Mozilla/5.0 (compatible; NetGainEmailPreview/1.0)"})
    xml = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    items = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def tag(name):
            m = re.search(rf"<{name}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>", it, re.S)
            return m.group(1) if m else ""
        items.append({"title": tag("title"), "description": tag("description"), "content": tag("content:encoded")})
    return items


def preview(kind, html, items):
    fills = {
        "{{ unsubscribe_url }}": "#",
        "{{ subscriber_preferences_url }}": "#",
        "{{ address }}": "600 1st Ave, Ste 330 PMB 92768, Seattle, WA 98104-2246",
    }
    if kind == "daily":
        body = items[0]["content"]
    else:
        body = "\n".join(i["description"] for i in items[:6])
    html = html.replace("{{ message_content }}", body)
    for k, v in fills.items():
        html = html.replace(k, v)
    return html


def main():
    os.makedirs(os.path.join(HERE, "kit"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "preview"), exist_ok=True)
    items = fetch_items() if "--offline" not in sys.argv else []
    for kind in VARIANTS:
        html = layout(kind)
        path = os.path.join(HERE, "kit", f"net-gain-edtech-{kind}.html")
        open(path, "w", encoding="utf-8").write(html)
        print("wrote", path, len(html), "bytes")
        if items:
            open(os.path.join(HERE, "preview", f"{kind}.html"), "w", encoding="utf-8").write(preview(kind, html, items))


if __name__ == "__main__":
    main()
