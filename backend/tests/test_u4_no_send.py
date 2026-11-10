"""
U4 tests — No-send capability assertions.

Tests:
  - no smtplib / sendmail / MIMEText / smtp in app/ code
  - no twilio / sns / fcm / apns / discord / slack_webhook / teams_webhook
  - action registry has no send_ actions and no email/sms/push/webhook actions
"""
from __future__ import annotations

import pathlib
import re


APP_ROOT = pathlib.Path(__file__).resolve().parent.parent / "app"


def _grep_app(pattern: str) -> list[str]:
    """Return list of (file:line: text) for every match of pattern in app/."""
    regex = re.compile(pattern, re.IGNORECASE)
    hits: list[str] = []
    for py_file in APP_ROOT.rglob("*.py"):
        for i, line in enumerate(py_file.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if regex.search(line):
                hits.append(f"{py_file.relative_to(APP_ROOT.parent)}:{i}: {line.strip()}")
    return hits


# ── No SMTP / email send ───────────────────────────────────────────────────────

def test_no_smtp_import():
    """No file in app/ may import smtplib, sendmail, or MIMEText."""
    patterns = r"\b(smtplib|sendmail|MIMEText|MIMEMultipart|smtpd|aiosmtplib)\b"
    hits = _grep_app(patterns)
    assert hits == [], (
        "Found SMTP/email-send references (no send capability allowed):\n"
        + "\n".join(hits)
    )


def test_no_sms_push_webhook():
    """No file in app/ may use Twilio, SNS, FCM, APNS, Discord, Slack or Teams webhooks."""
    patterns = (
        r"\b(twilio|boto3\.client.*sns|sns\.publish|fcm|apns"
        r"|discord\.webhook|slack_webhook|teams_webhook|requests\.post.*hook)\b"
    )
    hits = _grep_app(patterns)
    assert hits == [], (
        "Found SMS/push/webhook-send references (no send capability allowed):\n"
        + "\n".join(hits)
    )


# ── Action registry has no send actions ───────────────────────────────────────

def test_action_registry_has_no_send_action():
    """No registered action type may start with 'send_' or contain email/sms/push/webhook."""
    from app.services.campus.actions import ALLOWLIST

    forbidden_prefixes = ("send_",)
    forbidden_substrings = ("email", "sms", "push", "webhook")

    violations: list[str] = []
    for action_type in ALLOWLIST:
        name = action_type.lower()
        for prefix in forbidden_prefixes:
            if name.startswith(prefix):
                violations.append(f"Action '{action_type}' starts with forbidden prefix '{prefix}'")
        for sub in forbidden_substrings:
            if sub in name:
                violations.append(f"Action '{action_type}' contains forbidden substring '{sub}'")

    assert violations == [], (
        "Action ALLOWLIST contains send/email/sms/push/webhook actions:\n"
        + "\n".join(violations)
    )
