from dotenv import dotenv_values

from apartment_watcher import setup_wizard


def test_write_env_round_trips_special_characters(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_wizard, "ENV_FILE", tmp_path / ".env")
    values = {"GMAIL_APP_PASSWORD": 'ab"c\\d e#f', "MAX_RENT": ""}
    setup_wizard.write_env(values)
    assert dotenv_values(tmp_path / ".env") == values
