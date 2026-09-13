"""
Script generation business logic (SPEC.md Section 5): guidelines + recent
reviewed-final scripts as literal context, fed to Claude alongside a request
to source today's real stories via web search and write today's script.

Recent episodes serve two distinct purposes in that context (Section 5.1):
duplicate-story suppression (every episode with a final script, always) and
editorial-preference learning (a strict subset - only episodes where the
host's edit was substantial enough to carry a real signal about what they
actually wanted instead of the draft).
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


def filter_recent_episodes_for_context(episodes, lookback_days, before_date):
    """
    From a show's episode list (as returned by WPClient.list_episodes_for_show,
    newest first), returns (date, final_script, draft_or_none) triples for
    episodes with a non-empty ng_script_final, dated strictly before
    `before_date` (a "YYYY-MM-DD" string) and within the lookback window -
    oldest first, so the prompt reads as a natural day-by-day recap.

    draft_or_none carries the original AI draft only when script_reviewed was
    NOT flagged "degraded" - that flag is the existing near-identical-edit
    signal (class-admin-actions.php's similar_text() check, Section 5.2), so
    relying on it directly avoids re-implementing a second, cruder similarity
    check here. A near-identical draft/final pair has no editorial-preference
    signal to teach and would just add prompt noise.
    """
    cutoff = _days_before(before_date, lookback_days)
    matches = []
    for episode in episodes:
        meta = episode.get("meta", {})
        date = meta.get("ng_episode_date", "")
        final = meta.get("ng_script_final", "")
        if not final or not (cutoff <= date < before_date):
            continue

        draft = meta.get("ng_script_draft", "")
        reviewed_status = (meta.get("ng_step_status") or {}).get("script_reviewed", {}).get("status")
        draft_for_context = draft if (draft and reviewed_status != "degraded") else None
        matches.append((date, final, draft_for_context))

    matches.sort(key=lambda triple: triple[0])
    return matches


def _days_before(date_str, days):
    from datetime import date, timedelta

    y, m, d = (int(part) for part in date_str.split("-"))
    return (date(y, m, d) - timedelta(days=days)).isoformat()


def build_system_prompt(guidelines_text, show_name):
    return (
        f"You are the scriptwriter for \"{show_name}\", a daily audio newscast. "
        "This show's actual subject matter, tone, and format are defined entirely "
        "by its editorial guidelines below - they are the sole source of truth for "
        "what this show is, not any assumption about genre. Follow them exactly:\n\n"
        f"{guidelines_text}\n\n"
        "House rules for every episode:\n"
        "- Use the web_search tool to find today's real, verifiable stories "
        "relevant to this show's focus. Never invent or hallucinate a story.\n"
        "- Write natural spoken-word script text meant to be read aloud, not an "
        "article - no headers, bullet points, or markdown formatting.\n"
        "- Do not repeat a story already covered in the recent-episodes context "
        "you're given, even if it's still developing.\n"
        "- Where a recent episode shows your own original draft alongside the "
        "host's actual final version, that pairing is deliberate: the final "
        "reflects the host's real editorial judgment overriding your draft. "
        "Compare them and carry forward whatever pattern of tone, sentence "
        "length, structure, or word choice the edit reveals - don't repeat "
        "the same issue today that was corrected there.\n"
        "- Output only the finished script text - no preamble, no notes to the "
        "editor, no commentary about your process."
    )


def build_user_message(episode_date, recent_context):
    if recent_context:
        entries = []
        for date, final, draft in recent_context:
            if draft:
                entries.append(
                    f"[{date}]\nYour original draft:\n{draft}\n\n"
                    f"The host's actual final, as broadcast:\n{final}"
                )
            else:
                entries.append(f"[{date}]\n{final}")
        recap = "\n\n---\n\n".join(entries)
        context_block = (
            "Here are this show's most recent reviewed, final scripts, oldest "
            "first, for continuity and to avoid repeating stories. Some entries "
            "also show your own original draft alongside the host's final - "
            f"see the house rules above for what to do with those:\n\n{recap}\n\n"
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
        "editorial judgment for a daily newscast. Do not assume any particular "
        "tone, genre, or subject matter until guidelines are written."
    )

    recent_context = filter_recent_episodes_for_context(
        recent_episodes, show.get("lookback_days", 30), episode_date
    )

    system_prompt = build_system_prompt(guidelines_text, show["name"])
    user_message = build_user_message(episode_date, recent_context)

    # High effort, not the default "low" - explicit human-operator request
    # (2026-09-12) for genuine research/writing quality on the actual
    # newscast content, not just the fastest passable answer.
    return anthropic_generate(system=system_prompt, user_content=user_message, effort="high")
