"""Run one stored command and record its output and exit code.

Started detached by ``commands.start_run`` as::

    python -m ckanext.serverterminal.runner <run folder>

It does not import CKAN so it starts fast and keeps running if the web server
is restarted.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


KILL_GRACE_SECONDS = 10


def _write_result(path: Path, result: dict) -> None:
    tmp = path / "result.json.tmp"
    tmp.write_text(json.dumps(result), encoding="utf-8")
    os.replace(tmp, path / "result.json")


def run(path: Path) -> int:
    meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    timed_out = False

    with open(path / "output.log", "wb") as output:
        try:
            process = subprocess.Popen(
                meta["argv"],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            output.write(f"{exc}\n".encode())
            _write_result(path, {"exit_code": 127, "finished": int(time.time()), "timed_out": False})
            return 127

        try:
            exit_code = process.wait(timeout=meta["timeout"])
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                exit_code = process.wait(timeout=KILL_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                exit_code = process.wait()

    _write_result(path, {"exit_code": exit_code, "finished": int(time.time()), "timed_out": timed_out})
    return exit_code


if __name__ == "__main__":
    sys.exit(run(Path(sys.argv[1])))
