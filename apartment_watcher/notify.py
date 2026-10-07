from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage

from .listing import Listing

DEFAULT_RECIPIENT = "pedroholanda@gmail.com"


class EmailNotifier:
    """Sends notifications through Gmail SMTP using an App Password."""

    def __init__(self, sender: str, app_password: str, recipient: str = DEFAULT_RECIPIENT) -> None:
        self.sender = sender
        self.app_password = app_password
        self.recipient = recipient

    @classmethod
    def from_env(cls) -> EmailNotifier:
        sender = os.environ.get("GMAIL_ADDRESS")
        app_password = os.environ.get("GMAIL_APP_PASSWORD")
        if not sender or not app_password:
            raise SystemExit("Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD (see .env.example), or use --dry-run.")
        return cls(sender, app_password, os.environ.get("EMAIL_TO") or DEFAULT_RECIPIENT)

    def send_listing(self, listing: Listing) -> None:
        text, html_body = listing_bodies(listing)
        self._send(listing_subject(listing), text, html_body)

    def send_alert(self, subject: str, body: str) -> None:
        self._send(f"[Apartment watcher] {subject}", body)

    def _send(self, subject: str, text: str, html_body: str | None = None) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = self.recipient
        message.set_content(text)
        if html_body:
            message.add_alternative(html_body, subtype="html")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(self.sender, self.app_password)
            smtp.send_message(message)


def listing_subject(listing: Listing) -> str:
    parts = [listing.display_name]
    if listing.price:
        parts.append(listing.price)
    if listing.size_m2:
        parts.append(f"{listing.size_m2} m²")
    return f"[{listing.source}] " + " – ".join(parts)


def listing_bodies(listing: Listing) -> tuple[str, str]:
    rows = [
        ("Price", listing.price),
        ("Size", f"{listing.size_m2} m²" if listing.size_m2 else None),
        ("Bedrooms", str(listing.bedrooms) if listing.bedrooms else None),
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
