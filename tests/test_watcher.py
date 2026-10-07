import pytest

from apartment_watcher.listing import Listing
from apartment_watcher.store import SeenStore
from apartment_watcher.watcher import ALERT_AFTER_FAILURES, Source, Watcher, is_match


def make_listing(listing_id, city="Amsterdam", status="Te huur", title=None):
    return Listing(
        source="Test",
        listing_id=listing_id,
        url=f"https://example.com/{listing_id}",
        title=title or f"Appartement Straat {listing_id}",
        city=city,
        status=status,
    )


class FakeNotifier:
    def __init__(self):
        self.listings = []
        self.alerts = []
        self.fail = False

    def send_listing(self, listing):
        if self.fail:
            raise OSError("SMTP down")
        self.listings.append(listing)

    def send_alert(self, subject, body):
        self.alerts.append(subject)


class FakeSource:
    def __init__(self):
        self.listings = []
        self.error = None

    def fetch(self):
        if self.error:
            raise self.error
        return list(self.listings)


@pytest.fixture
def setup():
    store = SeenStore(":memory:")
    notifier = FakeNotifier()
    source = FakeSource()
    watcher = Watcher(store, notifier, sources=[Source("Test", source.fetch)])
    yield watcher, notifier, source
    store.close()


def test_is_match():
    assert is_match(make_listing("1"))
    assert is_match(make_listing("1", city="amsterdam"))
    assert not is_match(make_listing("1", city="Amstelveen"))
    assert not is_match(make_listing("1", city="Amsterdam-Duivendrecht"))
    assert not is_match(make_listing("1", status="Verhuurd"))
    assert not is_match(make_listing("1", title="Parkeerplaats Straat 1"))


def test_first_run_seeds_without_emailing(setup):
    watcher, notifier, source = setup
    source.listings = [make_listing("1"), make_listing("2")]

    watcher.run_once()
    assert notifier.listings == []

    watcher.run_once()
    assert notifier.listings == []


def test_emails_only_new_matching_listings(setup):
    watcher, notifier, source = setup
    source.listings = [make_listing("1")]
    watcher.run_once()

    new = make_listing("2")
    source.listings = [
        make_listing("1"),
        new,
        make_listing("3", city="Amstelveen"),
        make_listing("4", status="Verhuurd"),
    ]
    watcher.run_once()
    assert notifier.listings == [new]

    watcher.run_once()
    assert notifier.listings == [new]


def test_seeding_with_no_matches_still_counts_as_seeded(setup):
    watcher, notifier, source = setup
    source.listings = [make_listing("1", city="Amstelveen")]
    watcher.run_once()

    new = make_listing("2")
    source.listings = [new]
    watcher.run_once()
    assert notifier.listings == [new]


def test_failed_email_is_retried_next_run(setup):
    watcher, notifier, source = setup
    source.listings = [make_listing("1")]
    watcher.run_once()

    new = make_listing("2")
    source.listings = [make_listing("1"), new]
    notifier.fail = True
    watcher.run_once()
    assert notifier.listings == []

    notifier.fail = False
    watcher.run_once()
    assert notifier.listings == [new]


def test_alert_sent_once_after_consecutive_failures(setup):
    watcher, notifier, source = setup
    source.error = RuntimeError("layout changed")

    for _ in range(ALERT_AFTER_FAILURES - 1):
        watcher.run_once()
    assert notifier.alerts == []

    watcher.run_once()
    assert notifier.alerts == ["Test scraper may be broken"]

    for _ in range(ALERT_AFTER_FAILURES):
        watcher.run_once()
    assert len(notifier.alerts) == 1

    # Recovering resets the counter, so a later outage alerts again.
    source.error = None
    source.listings = [make_listing("1")]
    watcher.run_once()
    source.error = RuntimeError("layout changed again")
    for _ in range(ALERT_AFTER_FAILURES):
        watcher.run_once()
    assert len(notifier.alerts) == 2


def test_empty_results_count_as_failure(setup):
    watcher, notifier, source = setup
    for _ in range(ALERT_AFTER_FAILURES):
        watcher.run_once()
    assert notifier.alerts == ["Test scraper may be broken"]
