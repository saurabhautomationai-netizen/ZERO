"""Harmless, read-only test command for an isolated temporary workspace."""

import hashlib
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 3:
        return 2
    observed = hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()
    if observed != sys.argv[2]:
        print("fixture check failed")
        return 1
    print("fixture check succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
