from __future__ import annotations

import html
import os
import smtplib
import ssl
from email.message import EmailMessage

from .applying import ALREADY_APPLIED, APPLIED, CAP_REACHED, FAILED, SKIPPED, WOULD_APPLY, ApplyResult
from .listing import Listing

SUBJECT_PREFIX = {APPLIED: "[Applied] ", WOULD_APPLY: "[Would apply] ", FAILED: "[Apply failed] ", CAP_REACHED: "[Apply manually] "}
APPLICATION_LABEL = {
    APPLIED: "submitted",
    ALREADY_APPLIED: "already applied",
    WOULD_APPLY: "would apply",
    SKIPPED: "skipped",
    FAILED: "failed, apply manually",
    CAP_REACHED: "not applied, apply manually",
}


class EmailNotifier:
    """Sends notifications through Gmail SMTP using an App Password."""

    def __init__(self, sender: str, app_password: str, recipient: str) -> None:
        self.sender = sender
        self.app_password = app_password
        self.recipient = recipient

    @classmethod
    def from_env(cls) -> EmailNotifier:
        sender = os.environ.get("GMAIL_ADDRESS")
        app_password = os.environ.get("GMAIL_APP_PASSWORD")
        if not sender or not app_password:
            raise SystemExit("Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD (see .env.example), or use --dry-run.")
        return cls(sender, app_password, os.environ.get("EMAIL_TO") or sender)

    def send_listing(self, listing: Listing, application: ApplyResult | None = None) -> None:
        text, html_body = listing_bodies(listing, application)
        self._send(listing_subject(listing, application), text, html_body)

    def send_alert(self, subject: str, body: str) -> None:
        self._send(f"[Apartment watcher] {subject}", body)

    def send_test(self) -> None:
        self._send("[Apartment watcher] Test email", "Your apartment watcher can send emails. You're all set.")

    def _send(self, subject: str, text: str, html_body: str | None = None) -> None:
        message = EmailMessage()
        message["Subject"] = " ".join(subject.splitlines())
        message["From"] = self.sender
        message["To"] = self.recipient
        message.set_content(text)
        if html_body:
            message.add_alternative(html_body, subtype="html")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30, context=ssl.create_default_context()) as smtp:
            smtp.login(self.sender, self.app_password)
            smtp.send_message(message)


def listing_subject(listing: Listing, application: ApplyResult | None = None) -> str:
    parts = [listing.display_name]
    if listing.price:
        parts.append(listing.price)
    if listing.size_m2:
        parts.append(f"{listing.size_m2} m²")
    prefix = SUBJECT_PREFIX.get(application.status, "") if application else ""
    return f"{prefix}[{listing.source}] " + " – ".join(parts)


def listing_bodies(listing: Listing, application: ApplyResult | None = None) -> tuple[str, str]:
    auto_apply = None
    if application:
        label = APPLICATION_LABEL.get(application.status, application.status)
        auto_apply = f"{label} ({application.detail})" if application.detail else label
    rows = [
        ("Auto-apply", auto_apply),
        ("Price", listing.price),
        ("Size", f"{listing.size_m2} m²" if listing.size_m2 else None),
        ("Bedrooms", str(listing.bedrooms) if listing.bedrooms is not None else None),
        ("Available", listing.available),
        ("Status", listing.status),
    ]
    rows = [(label, value) for label, value in rows if value]

    text = "\n".join(
        [f"New rental listing on {listing.source}", "", listing.display_name]
        + [f"{label}: {value}" for label, value in rows]
        + ["", listing.url]
    )
    html_rows = "".join(
        f"<tr><td><b>{html.escape(label)}</b></td><td>{html.escape(value)}</td></tr>" for label, value in rows
    )
    html_body = (
        f"<p>New rental listing on {html.escape(listing.source)}</p>"
        f'<h2><a href="{html.escape(listing.url)}">{html.escape(listing.display_name)}</a></h2>'
        f"<table>{html_rows}</table>"
        f'<p><a href="{html.escape(listing.url)}">{html.escape(listing.url)}</a></p>'
    )
    return text, html_body
