
"""Entry point for the Fast Easy Car acquisition hunter.

    python run.py            # run continuously
    RUN_ONCE=1 python run.py # one cycle, then exit
"""

import fcntl
import logging
import os
import signal
import sys
from pathlib import Path

from hunter import VERSION
from hunter.api import Base44Client
from hunter.scheduler import main_loop
from hunter.settings import Env
from hunter.store import Store


def load_dotenv(path: str = ".env") -> None:
    """Read .env next to run.py. Real environment variables win."""
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


def acquire_lock(path: str):
    """Acquire an exclusive OS lock for this collector process.

    The lock is automatically released when the process exits,
    including after a Railway container restart.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    handle = open(path, "a+")

    try:
        fcntl.flock(
            handle.fileno(),
            fcntl.LOCK_EX | fcntl.LOCK_NB,
        )
    except BlockingIOError:
        handle.close()
        return None

    return handle


def release_lock(handle) -> None:
    """Release the collector lock."""
    if handle is None:
        return

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def main() -> int:
    load_dotenv()

    env = Env()

    logging.basicConfig(
        level=getattr(logging, env.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    problems = env.validate()

    if problems:
        for problem in problems:
            logging.error(problem)
        return 1

    # Ensure the database directory exists.
    db_path = Path(env.db_path).resolve()

    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        logging.exception("Unable to create database directory.")
        return 1

    # Keep the lock file alongside the SQLite database.
    lock_path = str(db_path.parent / "collector.lock")

    try:
        lock_handle = acquire_lock(lock_path)
    except OSError:
        logging.exception("Unable to acquire collector lock.")
        return 1

    if lock_handle is None:
        logging.error(
            "Another collector is already running against this database."
        )
        return 1

    store = None

    try:
        store = Store(env.db_path)

        api = Base44Client(
            env.base44_url,
            env.ingest_key,
        )

        def shutdown(signum, frame):
            logging.info("Stopping collector.")
            raise SystemExit(0)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        logging.info(
            "Fast Easy Car Hunter collector v%s starting against %s",
            VERSION,
            env.base44_url,
        )

        return main_loop(api, store, env)

    except (KeyboardInterrupt, SystemExit):
        logging.info("Collector shutting down.")
        return 0

    except Exception:
        logging.exception("Collector encountered an unexpected error.")
        return 1

    finally:
        if store is not None:
            store.close()

        release_lock(lock_handle)


if __name__ == "__main__":
    sys.exit(main())
