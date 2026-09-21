"""Capture Bayline control-board screenshots with system Chrome."""

from __future__ import annotations

import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "docs" / "screenshots"
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
CHROME = "/usr/bin/google-chrome-stable"
SHOTS = [
    ("command_board.png", f"{BASE}/", "1440,900"),
    ("sortation_line.png", f"{BASE}/?shot=line", "1440,900"),
    ("building_bays.png", f"{BASE}/?shot=floor", "1440,900"),
    ("exception_board.png", f"{BASE}/?shot=board", "1440,980"),
    ("analyst_note.png", f"{BASE}/?shot=close", "1440,980"),
]


def wait_for_server() -> None:
    for _ in range(40):
        try:
            urllib.request.urlopen(BASE, timeout=1)
            return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("dashboard server did not start")


def main() -> None:
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen(
        ["python3", "-m", "http.server", str(PORT), "--bind", "127.0.0.1"],
        cwd=ROOT / "dashboard",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server()
        for name, url, size in SHOTS:
            dest = SCREENSHOTS / name
            subprocess.run(
                [
                    CHROME,
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--hide-scrollbars",
                    "--force-device-scale-factor=1",
                    f"--window-size={size}",
                    "--user-data-dir=/tmp/bayline-chrome-profile",
                    "--disk-cache-dir=/tmp/bayline-chrome-cache",
                    "--virtual-time-budget=8000",
                    f"--screenshot={dest}",
                    url,
                ],
                check=True,
                timeout=25,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"wrote {dest} ({dest.stat().st_size} bytes)")
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
