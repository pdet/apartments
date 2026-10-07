import os
import plistlib
import subprocess
from pathlib import Path
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
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True
    assert plist["ThrottleInterval"] == 300
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


def test_setup_repairs_saved_invalid_settings_before_restarting(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(setup_wizard, "ENV_FILE", env_path)
    setup_wizard.write_env({
        "GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "abcdefghijklmnop", "AUTO_APPLY": "off",
        "MAX_RENT": "bad", "MIN_SIZE_M2": "-1", "GROSS_YEARLY_INCOME": "bad", "HOUSEHOLD_SIZE": "0",
        "MAX_APPLICATIONS_PER_DAY": "bad", "POLL_INTERVAL_MINUTES": "nan",
    })
    answers = iter(["", "", "", "1500", "50", "", "2", "5", "0", "2.5"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(setup_wizard.getpass, "getpass", lambda prompt: "")
    monkeypatch.setattr(setup_wizard, "EmailNotifier", MagicMock())
    stop, start = MagicMock(), MagicMock()
    monkeypatch.setattr(setup_wizard, "stop_service", stop)
    monkeypatch.setattr(setup_wizard, "start_service", start)
    setup_wizard.main()
    saved = dotenv_values(env_path, interpolate=False)
    assert {name: saved[name] for name in (
        "MAX_RENT", "MIN_SIZE_M2", "GROSS_YEARLY_INCOME", "HOUSEHOLD_SIZE", "MAX_APPLICATIONS_PER_DAY", "POLL_INTERVAL_MINUTES",
    )} == {
        "MAX_RENT": "1500", "MIN_SIZE_M2": "50", "GROSS_YEARLY_INCOME": "", "HOUSEHOLD_SIZE": "2",
        "MAX_APPLICATIONS_PER_DAY": "5", "POLL_INTERVAL_MINUTES": "2.5",
    }
    stop.assert_called_once()
    start.assert_called_once()


def test_repair_numeric_settings_normalizes_whitespace_defaults(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("Valid defaults should not prompt"))
    env = {"MAX_APPLICATIONS_PER_DAY": "   ", "POLL_INTERVAL_MINUTES": "10"}
    setup_wizard.repair_numeric_settings(env)
    assert env["MAX_APPLICATIONS_PER_DAY"] == ""


def test_cancelled_setting_repair_keeps_saved_settings_and_service(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(setup_wizard, "ENV_FILE", env_path)
    setup_wizard.write_env({
        "GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "abcdefghijklmnop", "POLL_INTERVAL_MINUTES": "bad",
    })
    saved = env_path.read_bytes()
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=["", "", "", KeyboardInterrupt()]))
    monkeypatch.setattr(setup_wizard.getpass, "getpass", lambda prompt: "")
    monkeypatch.setattr(setup_wizard, "EmailNotifier", MagicMock())
    stop, start = MagicMock(), MagicMock()
    monkeypatch.setattr(setup_wizard, "stop_service", stop)
    monkeypatch.setattr(setup_wizard, "start_service", start)
    with pytest.raises(KeyboardInterrupt):
        setup_wizard.main()
    assert env_path.read_bytes() == saved
    stop.assert_not_called()
    start.assert_not_called()


@pytest.mark.parametrize("failure_stage", ["sync", "setup", "interrupt"])
def test_installer_restarts_existing_service_after_failure(tmp_path, failure_stage):
    app = tmp_path / "Library" / "Application Support" / "apartment-watcher"
    app.mkdir(parents=True)
    script = app / "Install.command"
    source = Path(__file__).resolve().parents[1] / "Install.command"
    script.write_text(source.read_text().replace("$HOME", "$TEST_INSTALL_HOME"))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    state = tmp_path / "service-loaded"
    state.touch()
    commands = tmp_path / "launchctl-calls"
    executables = {
        fake_bin / "launchctl": '#!/bin/bash\necho "$1" >> "$TEST_INSTALL_CALLS"\ncase "$1" in\nprint) test -f "$TEST_INSTALL_STATE";;\nbootout) rm "$TEST_INSTALL_STATE";;\nbootstrap) touch "$TEST_INSTALL_STATE";;\nesac\n',
        fake_bin / "uv": f"#!/bin/bash\nexit {1 if failure_stage == 'sync' else 0}\n",
        app / ".venv" / "bin" / "python": "#!/bin/bash\n" + ('kill -INT "$PPID"\n' if failure_stage == "interrupt" else "") + "exit 130\n",
    }
    for path, contents in executables.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        path.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", str(script)], input="\n", text=True, capture_output=True,
        env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin", "TEST_INSTALL_HOME": str(tmp_path),
             "TEST_INSTALL_STATE": str(state), "TEST_INSTALL_CALLS": str(commands)},
    )
    assert result.returncode != 0
    assert state.exists()
    assert commands.read_text().splitlines() == ["print", "bootout", "print", "bootstrap"]
