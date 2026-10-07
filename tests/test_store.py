from apartment_watcher.applying import APPLIED, FAILED, ON, ApplyResult
from apartment_watcher.listing import Listing
from apartment_watcher.store import SeenStore


def test_replaced_application_refreshes_daily_count():
    store = SeenStore(":memory:")
    listing = Listing("MVGM", "1", "https://example.com/1", "Street 1", "Amsterdam", "Te huur")
    try:
        store.record_application(listing, ApplyResult(FAILED), ON)
        store._conn.execute("UPDATE applications SET attempted_at = now() - INTERVAL 2 DAY")
        assert store.applications_last_day() == 0
        store.record_application(listing, ApplyResult(APPLIED), ON)
        assert store.applications_last_day() == 1
        assert store.application_status(listing) == APPLIED
    finally:
        store.close()
