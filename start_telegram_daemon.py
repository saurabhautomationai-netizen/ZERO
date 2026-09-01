"""Dedicated resilient background daemon for ZERO Telegram Bot."""

import time
import sys
import os

from zero_core.interfaces.telegram.runner import DEFAULT_TELEGRAM_RUNNER

if __name__ == "__main__":
    print("[*] ZERO Telegram Resilient Daemon started.", flush=True)
    while True:
        try:
            DEFAULT_TELEGRAM_RUNNER.run_forever()
        except KeyboardInterrupt:
            print("[!] Daemon stopped by user.", flush=True)
            break
        except Exception as e:
            print(f"[!] Daemon error (retrying in 5s): {e}", file=sys.stderr, flush=True)
            time.sleep(5)
