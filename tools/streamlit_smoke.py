"""Bounded localhost-only Streamlit startup and health smoke check."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "streamlit_app.py"


def _available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_smoke(timeout_seconds: float) -> None:
    if timeout_seconds <= 0.0:
        raise ValueError("timeout must be positive")
    port = _available_local_port()
    health_url = f"http://127.0.0.1:{port}/_stcore/health"
    environment = os.environ.copy()
    environment["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ENTRYPOINT),
        "--server.headless=true",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.fileWatcherType=none",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.monotonic() + timeout_seconds
    local_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        last_error = "server did not answer"
        while time.monotonic() < deadline:
            return_code = process.poll()
            if return_code is not None:
                output, _ = process.communicate(timeout=1)
                raise RuntimeError(
                    "Streamlit exited before becoming healthy "
                    f"({return_code}).\n{output}"
                )
            try:
                with local_opener.open(health_url, timeout=1) as response:
                    body = response.read().decode("utf-8", errors="replace").strip()
                    if response.status == 200 and body == "ok":
                        print(f"Streamlit health check passed at {health_url}")
                        return
                    last_error = f"HTTP {response.status}: {body!r}"
            except (urllib.error.URLError, TimeoutError) as error:
                last_error = str(error)
            time.sleep(0.1)
        raise TimeoutError(
            f"Streamlit did not become healthy within {timeout_seconds:g}s: "
            f"{last_error}"
        )
    finally:
        _stop_process(process)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="maximum seconds to wait for the localhost health endpoint",
    )
    arguments = parser.parse_args()
    try:
        run_smoke(arguments.timeout)
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(f"Streamlit smoke check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
