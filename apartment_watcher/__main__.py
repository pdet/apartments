import argparse
import logging
import os

from dotenv import load_dotenv

from .notify import EmailNotifier
from .store import SeenStore
from .watcher import Watcher, run_forever

log = logging.getLogger("apartment_watcher")


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="apartment_watcher",
        description="Email new rental apartments in Amsterdam listed by Vestim and MVGM.",
    )
    parser.add_argument("--once", action="store_true", help="run a single check and exit")
    parser.add_argument(
        "--dry-run", action="store_true", help="print matching listings; don't send email or update the database"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("POLL_INTERVAL_MINUTES", 10)),
        help="minutes between checks (default: %(default)s)",
    )
    parser.add_argument("--db", default="data/seen.db", help="SQLite file with seen listings (default: %(default)s)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    notifier = None if args.dry_run else EmailNotifier.from_env()
    store = SeenStore(args.db)
    watcher = Watcher(store, notifier, dry_run=args.dry_run)
    try:
        if args.once:
            watcher.run_once()
        else:
            run_forever(watcher, args.interval)
    except KeyboardInterrupt:
        log.info("Stopped")
    finally:
        store.close()


if __name__ == "__main__":
    main()
