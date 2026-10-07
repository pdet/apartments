"""Logging in to MVGM (ikwilhuren.nu) and applying to listings."""

from __future__ import annotations

from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from . import mvgm
from .applying import ApplyResult, LoginError
from .listing import Listing
from .session import TIMEOUT

LOGIN_URL = f"{mvgm.BASE_URL}/login/"


def is_logged_in(html: str) -> bool:
    """Require the account navigation and reject anonymous links or a login form."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("#navbar-account") is None or soup.select_one('form#frmLogin, input[name="txtWachtwoord"]'):
        return False
    return not any(urlsplit(link["href"]).path.rstrip("/") == "/login" for link in soup.select("a[href]"))


class MvgmApplicant:
    def __init__(self, email: str, password: str) -> None:
        self.email = email
        self.password = password
        self.session = None

    def login(self) -> None:
        self.close()
        if not self.email or not self.password:
            raise LoginError("Set MVGM_EMAIL and MVGM_PASSWORD before checking the login")
        session, _ = mvgm.open_session()
        try:
            response = session.get(LOGIN_URL, timeout=TIMEOUT)
            response.raise_for_status()
            token = mvgm.parse_csrf_token(response.text)
            response = session.post(
                LOGIN_URL,
                data={"postrequest": "login", "_token": token, "txtEmail": self.email, "txtWachtwoord": self.password},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            response = session.get(mvgm.SEARCH_URL, timeout=TIMEOUT)
            response.raise_for_status()
            if not is_logged_in(response.text):
                raise LoginError("Could not verify MVGM login; check the email/password or site layout")
        except BaseException:
            session.close()
            raise
        self.session = session

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None

    def apply(self, listing: Listing) -> ApplyResult:
        # The logged-in "Ik heb belangstelling" flow still has to be mapped with a real account.
        raise NotImplementedError("live applying to MVGM is not available yet")
