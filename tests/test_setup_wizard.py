import plistlib
import subprocess
from unittest.mock import MagicMock

import pytest
from dotenv import dotenv_values

from apartment_watcher import setup_wizard


def test_write_env_round_trips_special_characters(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_wizard, "ENV_FILE", tmp_path / ".env")
    values = {"GMAIL_APP_PASSWORD": 'ab"c\\d e#f', "MAX_RENT": ""}
    setup_wizard.write_env(values)
    assert dotenv_values(tmp_path / ".env") == values


def test_setup_preserves_settings_and_literal_passwords_in_shadow_mode(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(setup_wizard, "ENV_FILE", env_path)
    values = {
        "GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "abcdefghijklmnop", "EMAIL_TO": "to@example.com",
        "MVGM_EMAIL": "account@example.com", "MVGM_PASSWORD": " pass${USER}word ", "AUTO_APPLY": "on",
        "MAX_APPLICATIONS_PER_DAY": "8", "MAX_RENT": "1500", "POLL_INTERVAL_MINUTES": "15",
    }
    setup_wizard.write_env(values)
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(setup_wizard.getpass, "getpass", lambda prompt: "")
    monkeypatch.setattr(setup_wizard, "EmailNotifier", MagicMock())
    applicant = MagicMock()
    monkeypatch.setattr(setup_wizard, "MvgmApplicant", applicant)
    stop, start = MagicMock(), MagicMock()
    monkeypatch.setattr(setup_wizard, "stop_service", stop)
    monkeypatch.setattr(setup_wizard, "start_service", start)
    setup_wizard.main()
    saved = dotenv_values(env_path, interpolate=False)
    assert saved["MVGM_PASSWORD"] == values["MVGM_PASSWORD"]
    assert saved["MAX_APPLICATIONS_PER_DAY"] == "8"
    assert saved["POLL_INTERVAL_MINUTES"] == "15"
    assert saved["AUTO_APPLY"] == "shadow"
    assert env_path.stat().st_mode & 0o777 == 0o600
    applicant.return_value.close.assert_called_once()
    stop.assert_called_once()
    start.assert_called_once()


def test_start_service_uses_installed_python_and_quoted_paths(tmp_path, monkeypatch):
    project = tmp_path / "Application Support" / "apartment-watcher"
    plist_path = tmp_path / "LaunchAgents" / "watcher.plist"
    monkeypatch.setattr(setup_wizard, "PROJECT_DIR", project)
    monkeypatch.setattr(setup_wizard, "PLIST", plist_path)
    run = MagicMock()
    monkeypatch.setattr(setup_wizard.subprocess, "run", run)
    setup_wizard.start_service()
    plist = plistlib.loads(plist_path.read_bytes())
    assert plist["ProgramArguments"] == [
        "/usr/bin/caffeinate", "-i", str(project / ".venv/bin/python"), "-u", "-m", "apartment_watcher",
    ]
    assert plist["WorkingDirectory"] == str(project)
    assert plist["StandardErrorPath"] == str(project / "watcher.log")
    assert run.call_args.kwargs["check"]


def test_optional_saved_limit_can_be_removed(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "-")
    assert setup_wizard.ask("Maximum rent", "1500", required=False, number=True) == ""


def test_household_input_rejects_zero_and_non_decimal_digits(monkeypatch):
    answers = iter(["0", "²", "2"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert setup_wizard.ask("Household", number=True, minimum=1) == "2"


def test_cancelled_setup_does_not_stop_existing_service(monkeypatch):
    def cancel(prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", cancel)
    monkeypatch.setattr(setup_wizard, "dotenv_values", lambda *args, **kwargs: {})
    stop = MagicMock()
    monkeypatch.setattr(setup_wizard, "stop_service", stop)
    with pytest.raises(KeyboardInterrupt):
        setup_wizard.main()
    stop.assert_not_called()


def test_stop_service_does_not_ignore_failure_for_running_agent(monkeypatch):
    run = MagicMock(side_effect=[MagicMock(returncode=0), subprocess.CalledProcessError(1, "launchctl")])
    monkeypatch.setattr(setup_wizard.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        setup_wizard.stop_service()


def test_stop_service_accepts_agent_not_installed(monkeypatch):
    run = MagicMock(return_value=MagicMock(returncode=113))
    monkeypatch.setattr(setup_wizard.subprocess, "run", run)
    setup_wizard.stop_service()
    run.assert_called_once()
