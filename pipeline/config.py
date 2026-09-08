"""
Environment configuration. Fails loudly and specifically on anything missing
rather than guessing or silently defaulting - per the project's own stated
discipline (SPEC.md Section 1 / CLAUDE.md): prefer failing loudly over
quietly proceeding on a bad assumption.
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv is a local-dev convenience; real deployments set real env vars.

REQUIRED_VARS = [
    "ANTHROPIC_API_KEY",
    "WP_BASE_URL",
    "WP_SERVICE_USERNAME",
    "WP_SERVICE_APP_PASSWORD",
]


class ConfigError(RuntimeError):
    pass


def load_config():
    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        raise ConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". See pipeline/.env.example."
        )

    return {
        "ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"],
        "WP_BASE_URL": os.environ["WP_BASE_URL"].rstrip("/"),
        "WP_SERVICE_USERNAME": os.environ["WP_SERVICE_USERNAME"],
        "WP_SERVICE_APP_PASSWORD": os.environ["WP_SERVICE_APP_PASSWORD"],
        "SMTP_HOST": os.environ.get("SMTP_HOST", ""),
        "SMTP_PORT": int(os.environ.get("SMTP_PORT", "587")),
        "SMTP_USERNAME": os.environ.get("SMTP_USERNAME", ""),
        "SMTP_PASSWORD": os.environ.get("SMTP_PASSWORD", ""),
        "ALERT_FROM_EMAIL": os.environ.get("ALERT_FROM_EMAIL", ""),
        "ALERT_TO_EMAIL": os.environ.get("ALERT_TO_EMAIL", ""),
    }
