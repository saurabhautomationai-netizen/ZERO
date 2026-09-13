"""Harmless subprocess fixture: no network, AI CLIs or project writes."""

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


def main():
    mode = sys.argv[1]
    if mode == "echo":
        print(json.dumps({"args": sys.argv[2:], "stdin": sys.stdin.buffer.read().decode("utf-8"),
                          "cwd": Path.cwd().as_posix(), "env": dict(os.environ)}, ensure_ascii=True))
    elif mode == "exit":
        sys.exit(int(sys.argv[2]))
    elif mode == "flood":
        def emit(stream, byte):
            for _ in range(256):
                stream.write(byte * 8192)
                stream.flush()
        thread = threading.Thread(target=emit, args=(sys.stderr.buffer, b"e"))
        thread.start()
        emit(sys.stdout.buffer, b"o")
        thread.join()
    elif mode == "utf8":
        for byte in "A\u20ac\U0001f642Z".encode("utf-8"):
            sys.stdout.buffer.write(bytes((byte,)))
            sys.stdout.buffer.flush()
            time.sleep(0.01)
    elif mode == "invalid":
        sys.stdout.buffer.write(b"\xff")
    elif mode == "sleep":
        Path(sys.argv[2]).write_text(str(os.getpid()), encoding="ascii")
        time.sleep(120)
    elif mode in ("tree", "orphan"):
        directory = Path(sys.argv[2])
        Path(directory / "root.pid").write_text(str(os.getpid()), encoding="ascii")
        subprocess.Popen([sys.executable, "-B", "-I", str(Path(__file__).resolve()),
                          "branch", str(directory)], shell=False, env=dict(os.environ))
        deadline = time.monotonic() + 10
        while not (directory / "leaf.pid").exists():
            if time.monotonic() > deadline:
                sys.exit(90)
            time.sleep(0.01)
        (directory / "ready").write_text("ready", encoding="ascii")
        if mode == "tree":
            time.sleep(120)
    elif mode == "branch":
        directory = Path(sys.argv[2])
        (directory / "branch.pid").write_text(str(os.getpid()), encoding="ascii")
        subprocess.Popen([sys.executable, "-B", "-I", str(Path(__file__).resolve()),
                          "sleep", str(directory / "leaf.pid")], shell=False, env=dict(os.environ))
        time.sleep(120)


if __name__ == "__main__":
    main()
