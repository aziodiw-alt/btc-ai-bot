import os
import signal
import subprocess
import sys
import time
from pathlib import Path


volume_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")

if volume_path:
    persistent_directory = Path(volume_path)
    persistent_directory.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault(
        "DATABASE_PATH",
        str(persistent_directory / "trades.db"),
    )
    os.environ.setdefault(
        "TELEGRAM_DATABASE_PATH",
        str(persistent_directory / "trades.db"),
    )
    os.environ.setdefault(
        "DASHBOARD_DATABASE_PATH",
        str(persistent_directory / "dashboard.db"),
    )

port = os.getenv("PORT", "8080")
processes = [
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "gunicorn",
            "--bind",
            f"0.0.0.0:{port}",
            "--workers",
            "1",
            "--threads",
            "4",
            "--timeout",
            "120",
            "--chdir",
            "web",
            "app:app",
        ]
    ),
    subprocess.Popen([sys.executable, "bot.py"]),
]


def stop_all(*_):
    for process in processes:
        if process.poll() is None:
            process.terminate()

    deadline = time.monotonic() + 10
    for process in processes:
        remaining = max(0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()


signal.signal(signal.SIGTERM, stop_all)
signal.signal(signal.SIGINT, stop_all)

exit_code = 0

try:
    while True:
        for process in processes:
            return_code = process.poll()
            if return_code is not None:
                exit_code = return_code or 1
                raise SystemExit
        time.sleep(1)
except (KeyboardInterrupt, SystemExit):
    stop_all()

sys.exit(exit_code)
