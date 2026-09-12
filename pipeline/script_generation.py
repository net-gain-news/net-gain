"""
Script generation business logic (SPEC.md Section 5): guidelines + recent
reviewed-final scripts as literal context, fed to Claude alongside a request
to source today's real stories via web search and write today's script.
"""

import re


def strip_html(html):
    """
    Guidelines are a rich-HTML WordPress page meant for humans (SPEC.md
    Section 3.2) - stripped to plain text here purely for cleaner prompt
    tokens, not for display.
    """
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def filter_recent_final_scripts(episodes, lookback_days, before_date):
    """
    From a show's episode list (as returned by WPClient.list_episodes_for_show,
    newest first), returns (date, script) pairs for episodes with a non-empty
    ng_script_final, dated strictly before `before_date` (a "YYYY-MM-DD"
    string) and within the lookback window - oldest first, so the prompt
    reads as a natural day-by-day recap.
    """
    cutoff = _days_before(before_date, lookback_days)
    matches = []
    for episode in episodes:
        meta = episode.get("meta", {})
        date = meta.get("ng_episode_date", "")
        script = meta.get("ng_script_final", "")
        if script and cutoff <= date < before_date:
            matches.append((date, script))
    matches.sort(key=lambda pair: pair[0])
    return matches


def _days_before(date_str, days):
    from datetime import date, timedelta

    y, m, d = (int(part) for part in date_str.split("-"))
    return (date(y, m, d) - timedelta(days=days)).isoformat()


def build_system_prompt(guidelines_text, show_name):
    return (
        f"You are the scriptwriter for \"{show_name}\", a daily good-news audio "
        "newscast. Follow this show's editorial guidelines exactly:\n\n"
        f"{guidelines_text}\n\n"
        "House rules for every episode:\n"
        "- Use the web_search tool to find today's real, verifiable stories "
        "relevant to this show's focus. Never invent or hallucinate a story.\n"
        "- Write natural spoken-word script text meant to be read aloud, not an "
        "article - no headers, bullet points, or markdown formatting.\n"
        "- Do not repeat a story already covered in the recent-episodes context "
        "you're given, even if it's still developing.\n"
        "- Output only the finished script text - no preamble, no notes to the "
        "editor, no commentary about your process."
    )


def build_user_message(episode_date, recent_scripts):
    if recent_scripts:
        recap = "\n\n".join(f"[{date}]\n{script}" for date, script in recent_scripts)
        context_block = (
            "Here are this show's most recent reviewed, final scripts, oldest "
            f"first, for continuity and to avoid repeating stories:\n\n{recap}\n\n"
        )
    else:
        context_block = "This is this show's first episode - there is no prior-episode context yet.\n\n"

    return (
        f"Today's date is {episode_date}.\n\n"
        f"{context_block}"
        "Write today's script now."
    )


def generate_script_for_show(wp, anthropic_generate, show, episode_date, recent_episodes):
    guidelines_html = wp.get_page_content(show["guidelines_page_id"]) if show.get("guidelines_page_id") else ""
    guidelines_text = strip_html(guidelines_html) if guidelines_html else (
        "No guidelines have been written for this show yet - use general good "
        "editorial judgment for a daily good-news newscast."
    )

    recent_scripts = filter_recent_final_scripts(
        recent_episodes, show.get("lookback_days", 30), episode_date
    )

    system_prompt = build_system_prompt(guidelines_text, show["name"])
    user_message = build_user_message(episode_date, recent_scripts)

    # High effort, not the default "low" - explicit human-operator request
    # (2026-09-12) for genuine research/writing quality on the actual
    # newscast content, not just the fastest passable answer.
    return anthropic_generate(system=system_prompt, user_content=user_message, effort="high")
