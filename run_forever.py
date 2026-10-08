from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAX_RETRY_DELAY = 60


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("hardon.supervisor")
    retry_delay = 5

    while True:
        started_at = time.monotonic()
        try:
            result = subprocess.run(
                [sys.executable, "-u", "main.py"],
                cwd=ROOT,
                check=False,
            )
            exit_code = result.returncode
        except OSError:
            logger.exception("Could not start the bot process")
            exit_code = 1

        if exit_code == 0:
            logger.info("Bot stopped normally")
            return

        if time.monotonic() - started_at >= MAX_RETRY_DELAY:
            retry_delay = 5
        logger.error("Bot exited with code %s; retrying in %s seconds", exit_code, retry_delay)
        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)


if __name__ == "__main__":
    main()
