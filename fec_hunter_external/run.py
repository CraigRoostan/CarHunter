"""Entry point for the Fast Easy Car acquisition hunter.

    python run.py            # run continuously
    RUN_ONCE=1 python run.py # one cycle, then exit
"""

import logging
import os
import signal
import sys

from hunter import VERSION
from hunter.api import Base44Client
from hunter.scheduler import main_loop
from hunter.settings import Env
from hunter.store import Store


def load_dotenv(path: str = '.env') -> None:
    """Read .env next to run.py. Real environment variables win."""
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def acquire_lock(path: str) -> bool:
    """One collector per database. A lock left by a killed process is taken over."""
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                pid = int((handle.read() or '0').strip())
            os.kill(pid, 0)
            return False
        except (ValueError, OSError):
            pass  # stale lock
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(str(os.getpid()))
    return True


def main() -> int:
    load_dotenv()
    env = Env()
    logging.basicConfig(
        level=getattr(logging, env.log_level, logging.INFO),
        format='%(asctime)s %(levelname)s %(message)s',
    )

    problems = env.validate()
    if problems:
        for problem in problems:
            logging.error(problem)
        return 1

    lock_path = os.path.join(os.path.dirname(os.path.abspath(env.db_path)) or '.', 'collector.lock')
    if not acquire_lock(lock_path):
        logging.error('Another collector is already running against this database.')
        return 1

    store = Store(env.db_path)
    api = Base44Client(env.base44_url, env.ingest_key)

    def shutdown(signum, frame):
        logging.info('Stopping collector.')
        store.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logging.info('Fast Easy Car Hunter collector v%s starting against %s', VERSION, env.base44_url)
    try:
        return main_loop(api, store, env)
    finally:
        store.close()


if __name__ == '__main__':
    sys.exit(main())