from __future__ import annotations

import fnmatch
import time
from pathlib import Path

from .config import AppConfig
from .events import EventLog
from .registry import Registry


def _matches_extension(path: Path, extensions: list[str]) -> bool:
    name_lower = path.name.lower()
    for ext in extensions:
        if name_lower.endswith(ext.lower()):
            return True
    return False


def _is_ignored(path: Path, ignore_patterns: list[str]) -> bool:
    name = path.name
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def discover_videos(cfg: AppConfig) -> list[Path]:
    incoming = cfg.paths.incoming_dir
    if not incoming.exists():
        return []

    videos: list[Path] = []
    for path in sorted(incoming.rglob("*")):
        if not path.is_file():
            continue
        if _is_ignored(path, cfg.ingest.ignore_patterns):
            continue
        if _matches_extension(path, cfg.ingest.video_extensions):
            videos.append(path.resolve())
    return videos


def is_file_stable(path: Path, wait_s: int) -> bool:
    if not path.exists():
        return False
    size_a = path.stat().st_size
    mtime_a = path.stat().st_mtime
    if wait_s <= 0:
        return size_a > 0
    time.sleep(wait_s)
    if not path.exists():
        return False
    size_b = path.stat().st_size
    mtime_b = path.stat().st_mtime
    return size_a == size_b and mtime_a == mtime_b and size_b > 0


def register_discovered_videos(cfg: AppConfig) -> list[tuple[Path, bool]]:
    registry = Registry(cfg.paths.registry_db)
    events = EventLog(cfg.paths.events_log)
    discovered: list[tuple[Path, bool]] = []

    for video_path in discover_videos(cfg):
        stat = video_path.stat()
        record, is_new_or_changed = registry.upsert_discovered(
            filename=video_path.name,
            local_path=video_path,
            file_size=stat.st_size,
            mtime=stat.st_mtime,
        )
        if is_new_or_changed:
            events.append(
                "video_discovered",
                filename=record.filename,
                local_path=record.local_path,
                size_mb=round(stat.st_size / (1024 * 1024), 2),
                status=record.status,
            )
        discovered.append((video_path, is_new_or_changed))
    return discovered


def videos_pending_ingest(cfg: AppConfig) -> list[Path]:
    registry = Registry(cfg.paths.registry_db)
    pending: list[Path] = []
    for record in registry.list_by_status(["discovered", "failed"]):
        path = Path(record.local_path)
        if path.exists() and _matches_extension(path, cfg.ingest.video_extensions):
            pending.append(path)
    return pending
