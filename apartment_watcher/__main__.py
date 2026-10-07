import argparse
import logging
import math
import os
from pathlib import Path

from dotenv import load_dotenv

from . import mvgm
from .applying import MODES, OFF, ON
from .criteria import Criteria
from .mvgm_apply import MvgmApplicant
from .notify import EmailNotifier, notify_desktop
from .store import SeenStore
from .watcher import Watcher, run_forever

log = logging.getLogger("apartment_watcher")


def main(argv: list[str] | None = None) -> None:
    load_dotenv(interpolate=False)
    parser = argparse.ArgumentParser(
        prog="apartment_watcher",
        description="Email new rental apartments in Amsterdam listed by Vestim and MVGM.",
    )
    parser.add_argument("--once", action="store_true", help="run a single check and exit")
    parser.add_argument(
        "--dry-run", action="store_true", help="print matching listings; don't send email or update the database"
    )
    parser.add_argument(
        "--apply-existing", action="store_true", help="run one check that also applies to listings seen before"
    )
    parser.add_argument("--check-login", action="store_true", help="log in to MVGM with the .env credentials and exit")
    parser.add_argument("--test-email", action="store_true", help="send a test email and exit")
    parser.add_argument(
        "--interval",
        type=float,
        default=os.environ.get("POLL_INTERVAL_MINUTES") or "10",
        help="minutes between checks (default: %(default)s)",
    )
    parser.add_argument("--db", default="data/apartments.duckdb", help="DuckDB file (default: %(default)s)")
    args = parser.parse_args(argv)
    if not math.isfinite(args.interval) or args.interval <= 0:
        parser.error("--interval / POLL_INTERVAL_MINUTES must be a positive, finite number")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    applicant = MvgmApplicant(os.environ.get("MVGM_EMAIL", ""), os.environ.get("MVGM_PASSWORD", ""))
    if args.check_login:
        try:
            applicant.login()
        finally:
            applicant.close()
        log.info("MVGM login OK")
        return
    if args.test_email:
        EmailNotifier.from_env().send_test()
        log.info("Test email sent")
        return

    mode = os.environ.get("AUTO_APPLY", OFF).strip().lower() or OFF
    if mode not in MODES:
        raise SystemExit(f"AUTO_APPLY must be one of {', '.join(MODES)}")
    if mode == ON:
        raise SystemExit("AUTO_APPLY=on isn't available yet; use AUTO_APPLY=shadow for now.")

    try:
        criteria = Criteria.from_env()
        daily_limit = int(os.environ.get("MAX_APPLICATIONS_PER_DAY") or 5)
        if daily_limit < 1:
            raise ValueError("MAX_APPLICATIONS_PER_DAY must be at least 1")
    except ValueError as exc:
        parser.error(str(exc))
    notifier = None if args.dry_run else EmailNotifier.from_env()
    db = args.db if not args.dry_run or Path(args.db).is_file() else ":memory:"
    store = SeenStore(db, read_only=args.dry_run and db != ":memory:")
    try:
        watcher = Watcher(
            store,
            notifier,
            dry_run=args.dry_run,
            applicants={} if mode == OFF else {mvgm.SOURCE: applicant},
            criteria=criteria,
            apply_mode=mode,
            max_applications_per_day=daily_limit,
        )
        if args.once or args.apply_existing:
            watcher.run_once(apply_existing=args.apply_existing)
        else:
            run_forever(watcher, args.interval)
    except KeyboardInterrupt:
        log.info("Stopped")
    finally:
        applicant.close()
        store.close()


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        if exc.code not in (0, None):
            notify_desktop(f"Apartment watcher stopped: {exc.code if isinstance(exc.code, str) else 'a setting is wrong, run Install again'}")
        raise
    except Exception as exc:
        notify_desktop(f"Apartment watcher stopped: {exc}")
        raise
