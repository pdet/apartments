import runpy
import sys
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv

from apartment_watcher import __main__ as cli, watcher
from apartment_watcher.listing import Listing
from apartment_watcher.store import SeenStore


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda **kwargs: None)
    for name in ("AUTO_APPLY", "MAX_RENT", "MIN_SIZE_M2", "GROSS_YEARLY_INCOME", "HOUSEHOLD_SIZE", "MAX_APPLICATIONS_PER_DAY", "POLL_INTERVAL_MINUTES"):
        monkeypatch.delenv(name, raising=False)
    listing = Listing("Test", "1", "https://example.com/1", "Street 1", "Amsterdam", "Te huur")
    monkeypatch.setattr(watcher, "SOURCES", [watcher.Source("Test", lambda: [listing])])


def test_dry_run_does_not_create_database(tmp_path):
    db = tmp_path / "data" / "apartments.duckdb"
    cli.main(["--once", "--dry-run", "--db", str(db)])
    assert not db.parent.exists()


def test_dry_run_does_not_modify_existing_database(tmp_path):
    db = tmp_path / "apartments.duckdb"
    store = SeenStore(db)
    store.close()
    before = db.read_bytes()
    cli.main(["--once", "--dry-run", "--db", str(db)])
    assert db.read_bytes() == before


@pytest.mark.parametrize("interval", ["0", "-1", "nan", "inf", "bad"])
def test_invalid_interval_fails_before_creating_database(tmp_path, interval):
    db = tmp_path / "apartments.duckdb"
    with pytest.raises(SystemExit) as exc:
        cli.main(["--once", "--dry-run", "--interval", interval, "--db", str(db)])
    assert exc.value.code == 2
    assert not db.exists()


def test_explicit_interval_overrides_invalid_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("POLL_INTERVAL_MINUTES", "bad")
    cli.main(["--once", "--dry-run", "--interval", "10", "--db", str(tmp_path / "unused.duckdb")])


def test_live_applying_remains_disabled(monkeypatch):
    monkeypatch.setenv("AUTO_APPLY", "on")
    with pytest.raises(SystemExit, match="isn't available yet"):
        cli.main(["--once", "--dry-run"])


def test_password_environment_substitutions_stay_literal(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text('MVGM_PASSWORD="pass${USER}word"\n')
    monkeypatch.delenv("MVGM_PASSWORD", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda **kwargs: load_dotenv(env_path, **kwargs))
    cli.main(["--once", "--dry-run", "--db", str(tmp_path / "unused.duckdb")])
    assert cli.os.environ["MVGM_PASSWORD"] == "pass${USER}word"


@pytest.mark.parametrize("argv, mode, exit_code, message", [
    (["--help"], "off", 0, None),
    (["--interval", "0"], "off", 2, "a setting is wrong, run Install again"),
    (["--once", "--dry-run"], "on", "AUTO_APPLY=on isn't available yet; use AUTO_APPLY=shadow for now.", "AUTO_APPLY=on"),
])
def test_entrypoint_reports_only_failed_exits(monkeypatch, argv, mode, exit_code, message):
    desktop = MagicMock()
    monkeypatch.setattr("apartment_watcher.notify.notify_desktop", desktop)
    monkeypatch.setattr("dotenv.load_dotenv", lambda **kwargs: None)
    monkeypatch.setattr("sys.argv", ["apartment_watcher", *argv])
    monkeypatch.setenv("AUTO_APPLY", mode)
    monkeypatch.delitem(sys.modules, "apartment_watcher.__main__")
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("apartment_watcher", run_name="__main__")
    assert exc.value.code == exit_code
    if message is None:
        desktop.assert_not_called()
    else:
        desktop.assert_called_once()
        assert message in desktop.call_args.args[0]


def test_entrypoint_reports_and_preserves_unexpected_error(monkeypatch):
    desktop = MagicMock()
    monkeypatch.setattr("apartment_watcher.notify.notify_desktop", desktop)
    monkeypatch.setattr("dotenv.load_dotenv", lambda **kwargs: None)
    monkeypatch.setattr("sys.argv", ["apartment_watcher", "--once", "--dry-run"])
    monkeypatch.setattr("apartment_watcher.store.SeenStore", MagicMock(side_effect=OSError("database unavailable")))
    monkeypatch.delitem(sys.modules, "apartment_watcher.__main__")
    with pytest.raises(OSError, match="database unavailable"):
        runpy.run_module("apartment_watcher", run_name="__main__")
    desktop.assert_called_once_with("Apartment watcher stopped: database unavailable")
