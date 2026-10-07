from __future__ import annotations

import logging
import math
import random
import signal
import time
import traceback
from dataclasses import dataclass
from typing import Callable, Protocol

from . import mvgm, vestim
from .applying import (
    APPLIED,
    CAP_REACHED,
    FAILED,
    OFF,
    SHADOW,
    SKIPPED,
    WOULD_APPLY,
    Applicant,
    ApplyResult,
)
from .criteria import Criteria
from .listing import Listing
from .notify import notify_desktop
from .store import SeenStore

log = logging.getLogger(__name__)

TARGET_CITY = "Amsterdam"
RENTABLE_STATUS = "Te huur"
NON_DWELLING_TYPES = {"parkeerplaats", "garage", "garagebox", "berging"}
ALERT_AFTER_FAILURES = 6  # consecutive failures (scraping, login or email) before alerting
QUIET_ALERT_AFTER = 144  # checks without any Amsterdam rental (about a day) before alerting
CHECK_TIMEOUT_SECONDS = 15 * 60  # a check normally takes about a minute


class Notifier(Protocol):
    def send_listing(self, listing: Listing, application: ApplyResult | None = None) -> None: ...
    def send_alert(self, subject: str, body: str) -> None: ...


@dataclass(frozen=True)
class Source:
    name: str
    fetch: Callable[[], list[Listing]]


SOURCES = [Source(vestim.SOURCE, vestim.fetch_listings), Source(mvgm.SOURCE, mvgm.fetch_listings)]


def is_match(listing: Listing) -> bool:
    """For rent, a dwelling, and in the city of Amsterdam itself."""
    object_type = listing.title.split(" ", 1)[0].casefold()
    return (
        listing.city.casefold() == TARGET_CITY.casefold()
        and listing.status.casefold() == RENTABLE_STATUS.casefold()
        and object_type not in NON_DWELLING_TYPES
    )


class Watcher:
    def __init__(
        self,
        store: SeenStore,
        notifier: Notifier | None,
        sources: list[Source] | None = None,
        dry_run: bool = False,
        applicants: dict[str, Applicant] | None = None,
        criteria: Criteria | None = None,
        apply_mode: str = OFF,
        max_applications_per_day: int = 5,
    ) -> None:
        if notifier is None and not dry_run:
            raise ValueError("a notifier is required unless dry_run is set")
        self.store = store
        self.notifier = notifier
        self.sources = SOURCES if sources is None else sources
        self.dry_run = dry_run
        self.applicants = applicants or {}
        self.criteria = criteria or Criteria()
        self.apply_mode = apply_mode
        self.max_applications_per_day = max_applications_per_day
        self.failures: dict[str, int] = {}
        self._alerted: set[str] = set()
        self._logged_in: dict[str, bool] = {}  # login result per source, for the current check

    def run_once(self, apply_existing: bool = False) -> None:
        """Check every source. With apply_existing, also apply to matching listings seen before."""
        self._logged_in.clear()
        for source in self.sources:
            try:
                self._check(source, apply_existing)
            except Exception:
                log.exception("%s: check failed", source.name)
                self._record_failure(
                    source.name,
                    f"{source.name} scraper may be broken",
                    f"Checking {source.name} failed. You won't get emails for new {source.name} listings until this is fixed.",
                    traceback.format_exc(),
                )
            else:
                self._reset_failures(source.name)

    def _check(self, source: Source, apply_existing: bool) -> None:
        listings = source.fetch()
        unreadable = sum(1 for listing in listings if not listing.city or not listing.status)
        if unreadable * 2 > len(listings):
            raise RuntimeError(
                f"Could not read the city or status of {unreadable} of {len(listings)} listings; the site layout may have changed."
            )

        matches = [listing for listing in listings if is_match(listing)]
        log.info("%s: %d listings scraped, %d for rent in %s", source.name, len(listings), len(matches), TARGET_CITY)
        quiet_key = f"{source.name} quiet"
        if matches:
            self._reset_failures(quiet_key)
        else:
            self._record_failure(
                quiet_key,
                f"No {source.name} rentals in {TARGET_CITY} for a day",
                f"{source.name} has shown no rentals in {TARGET_CITY} for about a day. That can be normal, "
                "but the website may also have changed.",
                f"{len(listings)} listings found, none for rent in {TARGET_CITY}.",
                alert_after=QUIET_ALERT_AFTER,
            )

        if self.dry_run:
            for listing in matches:
                state = "seen" if self.store.is_seen(listing) else "NEW "
                fit = ""
                if listing.source in self.applicants:
                    reasons = self.criteria.failures(listing)
                    fit = " | " + ("fits criteria" if not reasons else "skip: " + "; ".join(reasons))
                log.info("  [%s] %s | %s | %s%s", state, listing.display_name, listing.price, listing.url, fit)
            return

        if not self.store.is_seeded(source.name):
            for listing in matches:
                self.store.mark_seen(listing)
            self.store.mark_seeded(source.name)
            log.info("%s: first run, recorded %d existing listings without emailing", source.name, len(matches))
            if not apply_existing:
                return

        for listing in matches:
            if not self.store.is_seen(listing):
                self._handle_new(listing)
            elif apply_existing and self.store.application_status(listing) is None:
                self._apply_existing(listing)

    def _handle_new(self, listing: Listing) -> None:
        application = self._maybe_apply(listing)
        if not self._send_listing(listing, application):
            return
        self.store.mark_seen(listing)
        log.info("%s: emailed new listing %s (%s)", listing.source, listing.display_name, listing.url)

    def _apply_existing(self, listing: Listing) -> None:
        # Existing listings only need another email when an application was submitted or failed.
        application = self._maybe_apply(listing)
        if application is None:
            return
        log.info("%s: %s -> %s %s", listing.source, listing.display_name, application.status, application.detail)
        if application.status in (APPLIED, FAILED):
            self._send_listing(listing, application)

    def _send_listing(self, listing: Listing, application: ApplyResult | None) -> bool:
        try:
            self.notifier.send_listing(listing, application)
        except Exception:
            log.exception("%s: failed to email %s; will retry next check", listing.source, listing.url)
            self._record_failure(
                "email",
                "Emails are failing",
                "Sending apartment emails failed. Run Install again to check the Gmail settings.",
                traceback.format_exc(),
            )
            return False
        self._reset_failures("email")
        return True

    def _maybe_apply(self, listing: Listing) -> ApplyResult | None:
        """Apply to the listing if auto-apply is on and it fits the criteria; None if auto-apply doesn't cover it."""
        applicant = self.applicants.get(listing.source)
        if applicant is None or self.apply_mode == OFF:
            return None
        previous = self.store.application_status(listing)
        if previous is not None:  # never apply twice
            return ApplyResult(previous, "recorded earlier")
        reasons = self.criteria.failures(listing)
        if reasons:
            return ApplyResult(SKIPPED, "; ".join(reasons))
        if self.apply_mode == SHADOW:
            return ApplyResult(WOULD_APPLY, "shadow mode, nothing was submitted")
        if self.store.applications_last_day() >= self.max_applications_per_day:
            return ApplyResult(CAP_REACHED, f"daily limit of {self.max_applications_per_day} applications reached")
        if not self._ensure_logged_in(listing.source, applicant):
            return ApplyResult(FAILED, "could not log in")
        try:
            result = applicant.apply(listing)
        except Exception as exc:
            log.exception("%s: applying to %s failed", listing.source, listing.url)
            result = ApplyResult(FAILED, f"{type(exc).__name__}: {exc}")
        self.store.record_application(listing, result, self.apply_mode)
        log.info("%s: auto-apply %s for %s %s", listing.source, result.status, listing.url, result.detail)
        return result

    def _ensure_logged_in(self, source: str, applicant: Applicant) -> bool:
        if source not in self._logged_in:
            key = f"{source} login"
            try:
                applicant.login()
            except Exception:
                log.exception("%s: login failed", source)
                self._logged_in[source] = False
                self._record_failure(
                    key,
                    f"{source} auto-apply login failing",
                    f"Logging in to {source} failed, so auto-apply isn't working. Check the credentials in .env.",
                    traceback.format_exc(),
                )
            else:
                self._logged_in[source] = True
                self._reset_failures(key)
        return self._logged_in[source]

    def _reset_failures(self, key: str) -> None:
        self.failures[key] = 0
        self._alerted.discard(key)

    def _record_failure(
        self, key: str, subject: str, problem: str, reason: str, alert_after: int = ALERT_AFTER_FAILURES
    ) -> None:
        count = self.failures[key] = self.failures.get(key, 0) + 1
        log.warning("%s: failed (%d in a row)", key, count)
        if count < alert_after or key in self._alerted or self.dry_run:
            return
        try:
            self.notifier.send_alert(subject, f"{problem}\n\nThis failed {count} times in a row. Last error:\n{reason}")
        except Exception:
            log.exception("Failed to send the alert email; will retry next check")
            if count == alert_after:
                notify_desktop(f"{subject}. {problem} Alert email also failed; run Install.command to check email settings.")
        else:
            self._alerted.add(key)


def run_forever(watcher: Watcher, interval_minutes: float) -> None:
    if not math.isfinite(interval_minutes) or interval_minutes <= 0:
        raise ValueError("The polling interval must be a positive, finite number of minutes")
    while True:
        # If a check hangs, SIGALRM's default action kills the process and launchd restarts it.
        signal.alarm(CHECK_TIMEOUT_SECONDS)
        try:
            watcher.run_once()
        except Exception:
            log.exception("Unexpected error during check; continuing")
        finally:
            signal.alarm(0)
        delay = interval_minutes * 60 + random.uniform(0, 60)
        log.info("Next check in %.0f seconds", delay)
        time.sleep(delay)
