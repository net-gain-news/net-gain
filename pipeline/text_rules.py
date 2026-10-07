"""
House text rules applied to everything AI-generated (headlines, scripts, show notes, descriptions,
episode graphics) - one place, so no generator can forget one.

K-12 (operator rule, 2026-10-07): wherever the term K-12 is generated it must use a NON-BREAKING
hyphen (U+2011) between the K and the 12, so it can never be split across two lines. The rule is
enforced in code, not left to the prompts: anthropic_client.generate() runs every response through
apply_text_rules(), and every generator prompt also states the rule (K12_PROMPT_RULE).

What is deliberately left alone:
  * URLs - an href or link rewritten with a different character would stop working;
  * machine-facing fields that are not read as text, such as YouTube tags (metadata_generation
    restores ordinary hyphens there with machine_safe());
  * WordPress URL slugs, which the plugin builds with ordinary hyphens (see the sanitize_title
    filter in net-gain-studio.php).
Text the host types into a script by hand is not "AI-generated" and is not changed here.
"""

import re

NB_HYPHEN = "‑"

# Dash-like characters a model might produce between K and 12 (hyphen-minus, hyphen, non-breaking
# hyphen, figure dash, en dash, em dash, minus sign). PreK-12 counts too. The first alternative swallows
# URLs whole so they pass through untouched.
_URL_OR_K12 = re.compile(
    r"(?P<url>https?://[^\s\"'<>]+)"
    r"|(?<![A-Za-z0-9])(?P<k>(?:[Pp]re)?[Kk])[-‐‑‒–—−](?=12(?![0-9]))"
)

K12_PROMPT_RULE = (
    "K-12 SPELLING: whenever you write the term K-12, put a NON-BREAKING hyphen (the character U+2011, "
    f"as in K{NB_HYPHEN}12) between the K and the 12 - never an ordinary hyphen or an en dash - so the "
    "term can never break across two lines. Use ordinary hyphens everywhere else."
)


def apply_text_rules(text):
    """Return text with every K-12 spelled with the non-breaking hyphen (URLs untouched)."""
    if not text:
        return text

    def replace(match):
        if match.group("url"):
            return match.group("url")
        return match.group("k") + NB_HYPHEN

    return _URL_OR_K12.sub(replace, text)


def machine_safe(text):
    """Ordinary hyphens again, for fields that are identifiers or search keys rather than read text."""
    return text.replace(NB_HYPHEN, "-") if text else text
