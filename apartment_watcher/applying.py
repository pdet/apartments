"""Types shared by the auto-apply code."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .listing import Listing

# AUTO_APPLY modes
OFF = "off"
SHADOW = "shadow"  # decide and report, but never submit anything
ON = "on"
MODES = (OFF, SHADOW, ON)

# ApplyResult statuses. The first three come from an Applicant; the rest from the watcher.
APPLIED = "applied"
ALREADY_APPLIED = "already_applied"
FAILED = "failed"
WOULD_APPLY = "would_apply"
SKIPPED = "skipped"
CAP_REACHED = "cap_reached"


@dataclass(frozen=True)
class ApplyResult:
    status: str
    detail: str = ""


class LoginError(Exception):
    pass


class Applicant(Protocol):
    def login(self) -> None:
        """Log in; raises LoginError on bad credentials."""

    def apply(self, listing: Listing) -> ApplyResult:
        """Apply to a listing (requires login()); returns APPLIED, ALREADY_APPLIED or FAILED."""
