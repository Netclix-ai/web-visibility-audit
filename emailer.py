"""Transactional email sending via Resend.

Two emails are sent whenever a lead completes the public audit widget:
  1. The prospect snapshot summary to the lead's own email.
  2. A lead-notification email (contact info + links) to the agency.

Kept as a thin, isolated wrapper so the sending provider can be swapped
later (e.g. SendGrid/Postmark) without touching calling code.
"""
import os
import logging

import resend

logger = logging.getLogger("emailer")

resend.api_key = os.environ.get("RESEND_API_KEY")

DEFAULT_FROM = "onboarding@resend.dev"  # Resend's shared sending domain, usable without DNS verification


def send_email(to: str, subject: str, html: str, from_email: str | None = None, reply_to: str | None = None) -> bool:
    """Send an email via Resend. Returns True on success, False on failure
    (failures are logged, never raised, so a flaky email provider can't
    break the lead-capture / audit flow)."""
    if not os.environ.get("RESEND_API_KEY"):
        logger.warning("RESEND_API_KEY not set; skipping email to %s", to)
        return False
    try:
        params = {
            "from": from_email or DEFAULT_FROM,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if reply_to:
            params["reply_to"] = [reply_to]
        resend.Emails.send(params)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False
