import ssl
from unittest.mock import MagicMock

from apartment_watcher import notify
from apartment_watcher.applying import WOULD_APPLY, ApplyResult
from apartment_watcher.listing import Listing


def test_listing_email_handles_newlines_zero_bedrooms_and_html(monkeypatch):
    smtp = MagicMock()
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", smtp)
    listing = Listing(
        "MVGM", "1", "https://example.com/1?a=1&b=2", "Studio <Canal>\n1", "Amsterdam", "Te huur",
        price="€ 1.500,- /mnd", bedrooms=0,
    )
    notify.EmailNotifier("sender@gmail.com", "password", "recipient@example.com").send_listing(
        listing, ApplyResult(WOULD_APPLY, "shadow mode, nothing was submitted")
    )
    connection = smtp.return_value.__enter__.return_value
    message = connection.send_message.call_args.args[0]
    assert str(message["Subject"]).startswith("[Would apply] [MVGM] Studio <Canal> 1")
    assert "Bedrooms: 0" in message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "&lt;Canal&gt;" in html and "a=1&amp;b=2" in html
    assert "<Canal>" not in html
    connection.login.assert_called_once_with("sender@gmail.com", "password")
    context = smtp.call_args.kwargs["context"]
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
