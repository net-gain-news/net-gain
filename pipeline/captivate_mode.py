"""
How an episode gets onto Captivate: by the pipeline through Captivate's API (the original, fully automatic way) or by the
operator in Captivate's dashboard (manual posting, 2026-11-12).

Why manual exists: an episode created through the API gets a static house-ad slot that Captivate's campaign never fills, and the
dashboard then refuses to edit it. Episodes created in the dashboard get the right slots. Captivate has said it will not fix
the API side for now, so the operator posts each episode by hand and the pipeline carries on from there.

The switch is one line in the pipeline's .env file, so going back to the automatic way is a one-line edit with no deploy:

    CAPTIVATE_MANUAL_SHOWS=all                          # every show posts by hand
    CAPTIVATE_MANUAL_SHOWS=f40bbab2-a721-...,16         # only these shows (Captivate show id or WordPress show id)
    (line absent, or empty)                             # automatic, exactly as before

Everything the automatic way does is still in the code, untouched.
"""

# A step note that starts with this means "the hand-off was sent and the pipeline is waiting for the operator's episode". The
# automatic path also looks for it, so that switching the setting off while an episode is waiting adopts the operator's episode
# instead of creating a second one.
MANUAL_WAIT_NOTE = "Waiting for you to post this episode in Captivate"


def manual_tokens(config):
    raw = (config.get("CAPTIVATE_MANUAL_SHOWS") or "").strip().lower()
    return {token.strip() for token in raw.replace(";", ",").split(",") if token.strip()}


def is_manual(config, show):
    """True when this show's episodes are posted to Captivate by hand."""
    tokens = manual_tokens(config)
    if not tokens:
        return False
    if "all" in tokens:
        return True
    return bool(tokens & {str(show.get("captivate_show_id") or "").lower(), str(show.get("id") or "")})


def waiting_for_operator(step):
    """True for a captivate_published step that is in progress because the hand-off went out and nothing has been adopted yet."""
    step = step or {}
    return step.get("status") == "in_progress" and (step.get("note") or "").startswith(MANUAL_WAIT_NOTE)
