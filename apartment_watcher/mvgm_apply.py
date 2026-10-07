"""Logging in to MVGM (ikwilhuren.nu) and applying to listings."""

from __future__ import annotations

from bs4 import BeautifulSoup

from . import mvgm
from .applying import ApplyResult, LoginError
from .listing import Listing
from .session import TIMEOUT

LOGIN_URL = f"{mvgm.BASE_URL}/login/"


def is_logged_in(html: str) -> bool:
    """Anonymous pages link to /login/ and show the login form; logged-in pages don't."""
    soup = BeautifulSoup(html, "html.parser")
    return soup.select_one('a[href="/login/"], form#frmLogin') is None


class MvgmApplicant:
    def __init__(self, email: str, password: str) -> None:
        self.email = email
        self.password = password
        self.session = None

    def login(self) -> None:
        session, token = mvgm.open_session()
        response = session.post(
            LOGIN_URL,
            data={"postrequest": "login", "_token": token, "txtEmail": self.email, "txtWachtwoord": self.password},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        if not is_logged_in(response.text):
            raise LoginError("MVGM rejected the email/password")
        self.session = session

    def apply(self, listing: Listing) -> ApplyResult:
        # The logged-in "Ik heb belangstelling" flow still has to be mapped with a real account.
        raise NotImplementedError("live applying to MVGM is not available yet")
