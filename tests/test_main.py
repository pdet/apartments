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
