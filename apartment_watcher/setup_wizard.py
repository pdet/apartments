"""Asks a few questions, writes .env, checks email and MVGM login, and starts the background service."""

from __future__ import annotations

import getpass
import os
import plistlib
import subprocess
from pathlib import Path

from dotenv import dotenv_values

from .mvgm_apply import MvgmApplicant
from .notify import EmailNotifier

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"
LABEL = "nl.apartment-watcher"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def ask(
    question: str, current: str | None = None, secret: bool = False, required: bool = True,
    number: bool = False, minimum: int = 0,
) -> str:
    hint = " [press Enter to keep the current one]" if secret and current else f" [{current}]" if current else ""
    while True:
        answer = (getpass.getpass if secret else input)(f"{question}{hint}: ")
        if not secret:
            answer = answer.strip()
        if not required and answer == "-":
            return ""
        answer = answer or current or ""
        if number and answer and (not answer.isascii() or not answer.isdecimal() or int(answer) < minimum):
            print(f"  Please type a whole number of at least {minimum}, without dots or euro signs.")
        elif required and not answer:
            print("  This one is needed.")
        else:
            return answer


def yes(question: str, default: bool) -> bool:
    answer = input(f"{question} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    return default if not answer else answer.startswith("y")


def write_env(values: dict[str, str]) -> None:
    lines = []
    for key, value in values.items():
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{escaped}"')
    with ENV_FILE.open("w", encoding="utf-8") as env_file:
        os.fchmod(env_file.fileno(), 0o600)
        env_file.write("\n".join(lines) + "\n")


def stop_service() -> None:
    target = f"gui/{os.getuid()}/{LABEL}"
    if subprocess.run(["launchctl", "print", target], capture_output=True).returncode == 0:
        subprocess.run(["launchctl", "bootout", target], check=True, capture_output=True)


def start_service() -> None:
    log_file = str(PROJECT_DIR / "watcher.log")
    plist = {
        "Label": LABEL,
        # caffeinate keeps the Mac from falling asleep while the watcher runs.
        "ProgramArguments": ["/usr/bin/caffeinate", "-i", str(PROJECT_DIR / ".venv" / "bin" / "python"), "-u", "-m", "apartment_watcher"],
        "WorkingDirectory": str(PROJECT_DIR),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": log_file,
        "StandardErrorPath": log_file,
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(plist))
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST)], check=True)


def main() -> None:
    current = {k: v for k, v in dotenv_values(ENV_FILE, interpolate=False).items() if v is not None}
    env = current.copy()

    print("\nApartment watcher setup\n=======================\n")
    print("1) Email. The watcher sends emails from your Gmail account.")
    print("   You need a Gmail 'App Password': open https://myaccount.google.com/apppasswords,")
    print("   type any name (e.g. 'apartments'), click Create and copy the 16-letter password.\n")
    while True:
        env["GMAIL_ADDRESS"] = ask("Your Gmail address", current.get("GMAIL_ADDRESS"))
        env["GMAIL_APP_PASSWORD"] = ask("Gmail App Password", current.get("GMAIL_APP_PASSWORD"), secret=True).replace(" ", "")
        env["EMAIL_TO"] = ask("Send apartment emails to", current.get("EMAIL_TO") or env["GMAIL_ADDRESS"])
        try:
            EmailNotifier(env["GMAIL_ADDRESS"], env["GMAIL_APP_PASSWORD"], env["EMAIL_TO"]).send_test()
            print("  ✓ Test email sent. Check your inbox.\n")
            break
        except Exception as exc:
            print(f"  ✗ Could not send email ({exc}). Check the address and App Password and try again.\n")
            current.pop("GMAIL_APP_PASSWORD", None)

    print("2) Auto-apply (optional). The watcher can check which MVGM apartments fit you.")
    if yes("   Set up auto-apply for MVGM?", current.get("AUTO_APPLY", "off").strip().lower() not in ("", "off")):
        while True:
            env["MVGM_EMAIL"] = ask("   Your ikwilhuren.nu email", current.get("MVGM_EMAIL"))
            env["MVGM_PASSWORD"] = ask("   Your ikwilhuren.nu password", current.get("MVGM_PASSWORD"), secret=True)
            applicant = MvgmApplicant(env["MVGM_EMAIL"], env["MVGM_PASSWORD"])
            try:
                applicant.login()
                print("  ✓ Logged in to ikwilhuren.nu\n")
                break
            except Exception as exc:
                print(f"  ✗ Could not log in ({exc}).")
                current.pop("MVGM_PASSWORD", None)
                if not yes("   Try again?", True):
                    break
            finally:
                applicant.close()
        print("   Leave a new limit empty for 'no limit'; type '-' to remove a saved limit.")
        env["MAX_RENT"] = ask("   Maximum rent per month in euros", current.get("MAX_RENT"), required=False, number=True)
        env["MIN_SIZE_M2"] = ask("   Minimum size in m²", current.get("MIN_SIZE_M2"), required=False, number=True)
        env["GROSS_YEARLY_INCOME"] = ask(
            "   Gross yearly income in euros (household total)", current.get("GROSS_YEARLY_INCOME"), required=False, number=True
        )
        env["HOUSEHOLD_SIZE"] = ask("   How many people will live there", current.get("HOUSEHOLD_SIZE") or "1", number=True, minimum=1)
        env["AUTO_APPLY"] = "shadow"
    else:
        env["AUTO_APPLY"] = "off"
    env["POLL_INTERVAL_MINUTES"] = current.get("POLL_INTERVAL_MINUTES") or "10"
    stop_service()
    write_env(env)

    print("\n3) Starting the watcher in the background (it also starts when you log in)...")
    start_service()
    print("  ✓ Done! You'll get an email for every new apartment in Amsterdam.")
    print(f"  To change settings, run Install again. Activity log: {PROJECT_DIR / 'watcher.log'}\n")


if __name__ == "__main__":
    main()
