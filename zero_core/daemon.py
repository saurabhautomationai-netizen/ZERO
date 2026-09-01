"""ZERO Unified Background Daemon.

Runs both the FastAPI Web Command Center and the Telegram Bot Runner
in a single, resilient process with structured logging and graceful shutdown.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import uvicorn

from zero_core.config import load_env

load_env()

from zero_core.interfaces.telegram.runner import DEFAULT_TELEGRAM_RUNNER


def setup_logging():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(repo_root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, "zero.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def telegram_worker():
    if not DEFAULT_TELEGRAM_RUNNER.is_configured():
        logging.warning("Telegram Bot Token is not configured. Running Web Command Center only.")
        return
    logging.info("Starting Telegram Bot Runner daemon...")
    DEFAULT_TELEGRAM_RUNNER.run_forever()


def patrol_worker():
    from zero_core.patrol import DEFAULT_PATROL_WORKER
    logging.info("Starting Autonomous Project Patrol Worker daemon (6h cycle)...")
    # Initial scan after short warmup
    time.sleep(10)
    while True:
        try:
            DEFAULT_PATROL_WORKER.run_patrol_sweep()
        except Exception as e:
            logging.error(f"Error in Patrol Worker cycle: {e}")
        # Sleep 6 hours (21,600 seconds)
        time.sleep(21600)


def main():
    setup_logging()
    logging.info("=" * 50)
    logging.info("[*] Launching ZERO Unified Operating System Daemon")
    logging.info("  • Web Command Center: http://127.0.0.1:8000/")
    logging.info("  • Telegram Interface: Active")
    logging.info("  • Autonomous Project Patrol: Active")
    logging.info("=" * 50)

    # Start Telegram background daemon thread
    t_tel = threading.Thread(target=telegram_worker, daemon=True, name="TelegramWorker")
    t_tel.start()

    # Start Patrol background daemon thread
    t_patrol = threading.Thread(target=patrol_worker, daemon=True, name="PatrolWorker")
    t_patrol.start()

    # Run Uvicorn server on main thread
    try:
        server_config = uvicorn.Config(
            "zero_core.interfaces.web.app:app",
            host="127.0.0.1",
            port=8000,
            log_level="info",
            access_log=False,
        )
        server = uvicorn.Server(server_config)
        server.run()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Stopping ZERO Daemon...")


if __name__ == "__main__":
    main()

