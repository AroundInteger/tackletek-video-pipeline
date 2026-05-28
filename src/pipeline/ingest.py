from __future__ import annotations

from pathlib import Path

import cv2

from .config import AppConfig
from .events import EventLog
from .registry import Registry
from .scanner import is_file_stable, register_discovered_videos, videos_pending_ingest


def preview_path_for_video(cfg: AppConfig, video_path: Path) -> Path:
    stem = video_path.stem
    if video_path.name.lower().endswith(".ts.mp4"):
        stem = video_path.name[:-7]
    return cfg.paths.previews_dir / f"{stem}_frame0.png"


def extract_first_frame(video_path: Path, output_path: Path) -> tuple[int, int]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError(f"Could not read first frame from: {video_path}")
        height, width = frame.shape[:2]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output_path), frame):
            raise RuntimeError(f"Could not write preview: {output_path}")
        return width, height
    finally:
        cap.release()


def ingest_videos(cfg: AppConfig, force: bool = False) -> int:
    register_discovered_videos(cfg)
    registry = Registry(cfg.paths.registry_db)
    events = EventLog(cfg.paths.events_log)
    events.append("ingest_started")

    processed = 0
    failed = 0
    skipped = 0

    candidates = videos_pending_ingest(cfg)
    ingested_records = {r.local_path: r for r in registry.list_by_status(["ingested", "completed"])}

    for video_path in candidates:
        record = registry.get_by_path(video_path)
        if record is None:
            continue

        if not force and record.status == "ingested" and record.preview_path:
            skipped += 1
            continue

        if record.local_path in ingested_records and not force:
            existing = ingested_records[record.local_path]
            if existing.preview_path and Path(existing.preview_path).exists():
                skipped += 1
                continue

        if not is_file_stable(video_path, cfg.ingest.stability_wait_s):
            events.append(
                "ingest_skipped_unstable",
                filename=video_path.name,
                reason="file size or mtime changed during stability wait",
            )
            continue

        preview = preview_path_for_video(cfg, video_path)
        try:
            width, height = extract_first_frame(video_path, preview)
            registry.mark_ingested(record.id, preview)
            events.append(
                "ingest_completed",
                filename=video_path.name,
                preview=str(preview),
                width=width,
                height=height,
            )
            processed += 1
            print(f"Ingested: {video_path.name} -> {preview}")
        except Exception as exc:  # noqa: BLE001 - log and continue
            registry.mark_failed(record.id, str(exc))
            events.append(
                "ingest_failed",
                filename=video_path.name,
                error=str(exc),
            )
            failed += 1
            print(f"Failed: {video_path.name}: {exc}")

    events.append(
        "ingest_finished",
        processed=processed,
        failed=failed,
        skipped=skipped,
    )
    print(f"Ingest complete: processed={processed}, failed={failed}, skipped={skipped}")
    return 1 if failed else 0
