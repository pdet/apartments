from __future__ import annotations

import logging
import random
import time
import traceback
from dataclasses import dataclass
from typing import Callable, Protocol

from . import mvgm, vestim
from .listing import Listing
from .store import SeenStore

log = logging.getLogger(__name__)

TARGET_CITY = "Amsterdam"
RENTABLE_STATUS = "Te huur"
NON_DWELLING_TYPES = {"parkeerplaats", "garage", "garagebox", "berging"}
ALERT_AFTER_FAILURES = 6  # consecutive failed checks before emailing a "scraper may be broken" alert


class Notifier(Protocol):
    def send_listing(self, listing: Listing) -> None: ...
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
        sources: list[Source] = SOURCES,
        dry_run: bool = False,
    ) -> None:
        if notifier is None and not dry_run:
            raise ValueError("a notifier is required unless dry_run is set")
        self.store = store
        self.notifier = notifier
        self.sources = sources
        self.dry_run = dry_run
        self.failures = {source.name: 0 for source in sources}

    def run_once(self) -> None:
        for source in self.sources:
            self._check(source)

    def _check(self, source: Source) -> None:
        try:
            listings = source.fetch()
        except Exception:
            log.exception("%s: scraping failed", source.name)
            self._record_failure(source, traceback.format_exc())
            return
        if not listings:
            self._record_failure(source, "The scraper returned no listings at all; the site layout may have changed.")
            return
        self.failures[source.name] = 0

        matches = [listing for listing in listings if is_match(listing)]
        log.info("%s: %d listings scraped, %d for rent in %s", source.name, len(listings), len(matches), TARGET_CITY)

        if self.dry_run:
            for listing in matches:
                state = "seen" if self.store.is_seen(listing) else "NEW "
                log.info("  [%s] %s | %s | %s", state, listing.display_name, listing.price, listing.url)
            return

        if not self.store.is_seeded(source.name):
            for listing in matches:
                self.store.mark_seen(listing)
            self.store.mark_seeded(source.name)
            log.info("%s: first run, recorded %d existing listings without emailing", source.name, len(matches))
            return

        for listing in matches:
            if self.store.is_seen(listing):
                continue
            try:
                self.notifier.send_listing(listing)
            except Exception:
                log.exception("%s: failed to email %s; will retry next check", source.name, listing.url)
                continue
            self.store.mark_seen(listing)
            log.info("%s: emailed new listing %s (%s)", source.name, listing.display_name, listing.url)

    def _record_failure(self, source: Source, reason: str) -> None:
        self.failures[source.name] += 1
        count = self.failures[source.name]
        log.warning("%s: check failed (%d in a row)", source.name, count)
        if count != ALERT_AFTER_FAILURES or self.dry_run:
            return
        try:
            self.notifier.send_alert(
                f"{source.name} scraper may be broken",
                f"The last {count} checks of {source.name} failed. You won't get emails for new "
                f"{source.name} listings until this is fixed.\n\nLast error:\n{reason}",
            )
        except Exception:
            log.exception("Failed to send the alert email")


def run_forever(watcher: Watcher, interval_minutes: float) -> None:
    while True:
        try:
            watcher.run_once()
        except Exception:
            log.exception("Unexpected error during check; continuing")
        delay = interval_minutes * 60 + random.uniform(0, 60)
        log.info("Next check in %.0f seconds", delay)
        time.sleep(delay)
