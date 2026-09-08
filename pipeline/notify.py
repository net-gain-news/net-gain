"""
Minimal failure-email hook (SPEC.md Section 9: "Failure email alerting, per
show, per failure - not just a log file nobody is watching"). Deliberately
not a full alerting subsystem (routing rules, templates, missed-upload
alerts) - just an honest, working notification for the one failure mode
this phase can actually produce. Logs and no-ops if SMTP isn't configured,
rather than pretending to send.
"""

import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("net_gain.notify")


def notify_failure(config, show_name, step_key, error_message):
    if not config.get("SMTP_HOST") or not config.get("ALERT_TO_EMAIL"):
        logger.warning(
            "SMTP not configured - failure alert not sent (show=%s step=%s error=%s)",
            show_name,
            step_key,
            error_message,
        )
        return

    message = EmailMessage()
    message["Subject"] = f"Net Gain Studio: {step_key} failed for {show_name}"
    message["From"] = config["ALERT_FROM_EMAIL"] or config["SMTP_USERNAME"]
    message["To"] = config["ALERT_TO_EMAIL"]
    message.set_content(
        f"Show: {show_name}\nStep: {step_key}\nError: {error_message}\n"
    )

    try:
        with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"], timeout=15) as smtp:
            smtp.starttls()
            if config.get("SMTP_USERNAME"):
                smtp.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
            smtp.send_message(message)
    except Exception:
        logger.exception("Failed to send failure alert email (show=%s step=%s)", show_name, step_key)
