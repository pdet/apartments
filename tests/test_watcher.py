import subprocess
import sys
from dataclasses import replace

import pytest

from apartment_watcher.applying import (
    APPLIED,
    CAP_REACHED,
    FAILED,
    ON,
    SHADOW,
    SKIPPED,
    WOULD_APPLY,
    ApplyResult,
    LoginError,
)
from apartment_watcher.criteria import Criteria
from apartment_watcher.listing import Listing
from apartment_watcher.store import SeenStore
from apartment_watcher import watcher as watcher_module
from apartment_watcher.watcher import ALERT_AFTER_FAILURES, QUIET_ALERT_AFTER, Source, Watcher, is_match


def make_listing(listing_id, city="Amsterdam", status="Te huur", title=None, price="€ 1.500,- /mnd", size_m2=60):
    return Listing(
        source="Test",
        listing_id=listing_id,
        url=f"https://example.com/{listing_id}",
        title=title or f"Appartement Straat {listing_id}",
        city=city,
        status=status,
        price=price,
        size_m2=size_m2,
    )


class FakeNotifier:
    def __init__(self):
        self.listings = []
        self.applications = []
        self.alerts = []
        self.fail = False

    def send_listing(self, listing, application=None):
        if self.fail:
            raise OSError("SMTP down")
        self.listings.append(listing)
        self.applications.append(application)

    def send_alert(self, subject, body):
        if self.fail:
            raise OSError("SMTP down")
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


def test_no_amsterdam_rentals_alerts_only_after_a_day(setup):
    watcher, notifier, source = setup
    source.listings = [make_listing("1", city="Amstelveen")]
    for _ in range(QUIET_ALERT_AFTER - 1):
        watcher.run_once()
    assert notifier.alerts == []

    watcher.run_once()
    assert notifier.alerts == ["No Test rentals in Amsterdam for a day"]


def test_unreadable_listings_count_as_failure(setup):
    watcher, notifier, source = setup
    source.listings = [make_listing("1", city=""), make_listing("2", status="")]
    for _ in range(ALERT_AFTER_FAILURES):
        watcher.run_once()
    assert notifier.alerts == ["Test scraper may be broken"]


def test_failing_email_falls_back_to_desktop_notification(setup, monkeypatch):
    watcher, notifier, source = setup
    desktop = []
    monkeypatch.setattr(watcher_module, "notify_desktop", desktop.append)
    source.listings = [make_listing("seed")]
    watcher.run_once()

    notifier.fail = True
    source.listings = [make_listing(str(i)) for i in range(ALERT_AFTER_FAILURES)]
    watcher.run_once()
    assert len(desktop) == 1 and desktop[0].startswith("Emails are failing")

    notifier.fail = False
    watcher.run_once()
    assert watcher.failures["email"] == 0 and len(notifier.listings) == ALERT_AFTER_FAILURES


def test_hanging_check_is_killed_by_the_watchdog():
    code = (
        "import time\n"
        "from apartment_watcher import watcher\n"
        "watcher.CHECK_TIMEOUT_SECONDS = 1\n"
        "class Hangs:\n"
        "    def run_once(self): time.sleep(30)\n"
        "watcher.run_forever(Hangs(), 10)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], timeout=20)
    assert result.returncode == -14  # SIGALRM


def test_failed_alert_is_retried_until_delivered(setup, monkeypatch):
    watcher, notifier, source = setup
    source.error = RuntimeError("layout changed")
    send_alert = notifier.send_alert
    desktop = []
    monkeypatch.setattr(watcher_module, "notify_desktop", desktop.append)

    def fail_alert(*args):
        raise OSError("SMTP down")

    monkeypatch.setattr(notifier, "send_alert", fail_alert)
    for _ in range(ALERT_AFTER_FAILURES + 1):
        watcher.run_once()
    assert len(desktop) == 1
    assert "email settings" in desktop[0]
    monkeypatch.setattr(notifier, "send_alert", send_alert)
    watcher.run_once()
    watcher.run_once()
    assert notifier.alerts == ["Test scraper may be broken"]


def test_processing_failure_alerts_and_does_not_block_other_sources(setup, monkeypatch):
    watcher, notifier, source = setup
    source.listings = [make_listing("1")]
    other = replace(make_listing("2"), source="Other")
    watcher.sources.append(Source("Other", lambda: [other]))
    watcher.store.mark_seeded("Other")
    is_seeded = watcher.store.is_seeded

    def fail_first_source(name):
        if name == "Test":
            raise OSError("database unavailable")
        return is_seeded(name)

    monkeypatch.setattr(watcher.store, "is_seeded", fail_first_source)
    for _ in range(ALERT_AFTER_FAILURES + 1):
        watcher.run_once()
    assert notifier.listings == [other]
    assert notifier.alerts == ["Test scraper may be broken"]

    monkeypatch.setattr(watcher.store, "is_seeded", is_seeded)
    watcher.run_once()
    monkeypatch.setattr(watcher.store, "is_seeded", fail_first_source)
    for _ in range(ALERT_AFTER_FAILURES):
        watcher.run_once()
    assert notifier.alerts == ["Test scraper may be broken", "Test scraper may be broken"]


@pytest.mark.parametrize("fails", [False, True])
def test_watchdog_is_disarmed_before_sleep(monkeypatch, fails):
    alarms = []
    monkeypatch.setattr(watcher_module.signal, "alarm", alarms.append)

    class Check:
        def run_once(self):
            assert alarms == [watcher_module.CHECK_TIMEOUT_SECONDS]
            if fails:
                raise RuntimeError("check failed")

    def stop_sleep(delay):
        assert alarms == [watcher_module.CHECK_TIMEOUT_SECONDS, 0]
        raise KeyboardInterrupt

    monkeypatch.setattr(watcher_module.time, "sleep", stop_sleep)
    with pytest.raises(KeyboardInterrupt):
        watcher_module.run_forever(Check(), 10)


class FakeApplicant:
    def __init__(self):
        self.applied = []
        self.logins = 0
        self.login_error = None
        self.apply_error = None

    def login(self):
        self.logins += 1
        if self.login_error:
            raise self.login_error

    def apply(self, listing):
        if self.apply_error:
            raise self.apply_error
        self.applied.append(listing.listing_id)
        return ApplyResult(APPLIED)


@pytest.fixture
def apply_setup():
    store = SeenStore(":memory:")
    notifier = FakeNotifier()
    source = FakeSource()
    applicant = FakeApplicant()
    watcher = Watcher(
        store,
        notifier,
        sources=[Source("Test", source.fetch)],
        applicants={"Test": applicant},
        criteria=Criteria(max_rent=1600, min_size_m2=50),
        apply_mode=ON,
        max_applications_per_day=2,
    )
    source.listings = [make_listing("seed")]
    watcher.run_once()
    yield watcher, notifier, source, applicant, store
    store.close()


def test_applies_to_new_listing_that_fits(apply_setup):
    watcher, notifier, source, applicant, store = apply_setup
    fits, too_expensive = make_listing("1"), make_listing("2", price="€ 2.000,- /mnd")
    source.listings = [fits, too_expensive]
    watcher.run_once()

    assert applicant.applied == ["1"]
    assert [a.status for a in notifier.applications] == [APPLIED, SKIPPED]
    assert "rent € 2.000 > max € 1.600" in notifier.applications[1].detail
    assert store.application_status(fits) == APPLIED
    assert store.application_status(too_expensive) is None


def test_shadow_mode_never_submits(apply_setup):
    watcher, notifier, source, applicant, store = apply_setup
    watcher.apply_mode = SHADOW
    source.listings = [make_listing("1")]
    watcher.run_once()

    assert applicant.applied == [] and applicant.logins == 0
    assert notifier.applications[0].status == WOULD_APPLY


def test_mode_off_or_other_source_has_no_application(apply_setup):
    watcher, notifier, source, applicant, store = apply_setup
    watcher.applicants = {}
    source.listings = [make_listing("1")]
    watcher.run_once()
    assert notifier.applications == [None]


def test_daily_cap(apply_setup):
    watcher, notifier, source, applicant, store = apply_setup
    source.listings = [make_listing(str(i)) for i in range(3)]
    watcher.run_once()

    assert applicant.applied == ["0", "1"]
    assert notifier.applications[2].status == CAP_REACHED


def test_apply_error_is_recorded_and_still_emailed(apply_setup):
    watcher, notifier, source, applicant, store = apply_setup
    applicant.apply_error = RuntimeError("form changed")
    listing = make_listing("1")
    source.listings = [listing]
    watcher.run_once()

    assert notifier.applications[0].status == FAILED
    assert store.application_status(listing) == FAILED


def test_login_failure_alerts_after_repeated_failures(apply_setup):
    watcher, notifier, source, applicant, store = apply_setup
    applicant.login_error = LoginError("bad password")
    for i in range(ALERT_AFTER_FAILURES):
        source.listings = [make_listing(f"new{i}"), make_listing(f"other{i}")]
        watcher.run_once()

    assert applicant.logins == ALERT_AFTER_FAILURES  # once per check, not once per listing
    assert notifier.alerts == ["Test auto-apply login failing"]
    assert all(a.status == FAILED for a in notifier.applications)


def test_apply_existing_applies_once_to_listings_seen_before(apply_setup):
    watcher, notifier, source, applicant, store = apply_setup
    watcher.run_once(apply_existing=True)
    watcher.run_once(apply_existing=True)

    assert applicant.applied == ["seed"]
    assert len(notifier.listings) == 1
