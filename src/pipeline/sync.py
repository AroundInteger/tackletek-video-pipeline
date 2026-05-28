from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import AppConfig
from .events import EventLog


def sync_from_drive(cfg: AppConfig, dry_run: bool = False) -> int:
    cfg.paths.incoming_dir.mkdir(parents=True, exist_ok=True)
    events = EventLog(cfg.paths.events_log)
    events.append("sync_started", folder_id=cfg.drive.folder_id, url=cfg.drive.url)

    if not dry_run:
        try:
            import gdown  # noqa: F401
        except ImportError as exc:
            events.append("sync_failed", reason="gdown not installed")
            raise RuntimeError("Missing dependency: pip install gdown") from exc

    cmd = [
        sys.executable,
        "-m",
        "gdown",
        "--folder",
        cfg.drive.url or cfg.drive.folder_id,
        "-O",
        str(cfg.paths.incoming_dir.resolve()),
    ]

    if dry_run:
        print(" ".join(cmd))
        events.append("sync_dry_run", command=" ".join(cmd))
        return 0

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        events.append(
            "sync_failed",
            returncode=result.returncode,
            stderr=result.stderr[-2000:] if result.stderr else "",
        )
        print(result.stderr or result.stdout, file=sys.stderr)
        return result.returncode

    events.append(
        "sync_completed",
        incoming_dir=str(cfg.paths.incoming_dir),
        stdout_tail=result.stdout[-500:] if result.stdout else "",
    )
    return 0


def discover_synced_files(incoming_dir: Path) -> list[Path]:
    if not incoming_dir.exists():
        return []
    files: list[Path] = []
    for path in sorted(incoming_dir.rglob("*")):
        if path.is_file():
            files.append(path)
    return files
