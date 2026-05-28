from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .config import AppConfig
from .events import EventLog
from .registry import Registry


def _dataset_video_dir(cfg: AppConfig) -> Path:
    if cfg.tackletek is None:
        raise RuntimeError("tackletek section missing from config.yaml")
    return cfg.tackletek.onevone_root / "OutsideExamples" / cfg.tackletek.dataset_name


def _dataset_output_dir(cfg: AppConfig) -> Path:
    if cfg.tackletek is None:
        raise RuntimeError("tackletek section missing from config.yaml")
    dataset = cfg.tackletek.dataset_name
    return _dataset_video_dir(cfg) / f"{dataset}_output"


def stage_video_for_matlab(cfg: AppConfig, source: Path) -> Path:
    dataset_dir = _dataset_video_dir(cfg)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dest = dataset_dir / source.name
    if dest.exists() and dest.stat().st_size == source.stat().st_size:
        return dest
    shutil.copy2(source, dest)
    return dest


def _build_matlab_command(cfg: AppConfig, clip_stem: str) -> str:
    if cfg.tackletek is None:
        raise RuntimeError("tackletek section missing from config.yaml")

    matlab_dir = str(cfg.tackletek.matlab_dir).replace("'", "''")
    dataset = cfg.tackletek.dataset_name.replace("'", "''")
    clip_stem = clip_stem.replace("'", "''")
    skip_arena = "true" if cfg.tackletek.skip_arena else "false"
    fps = cfg.tackletek.fps

    return (
        f"cd('{matlab_dir}'); "
        f"addpath(pwd); addpath(fullfile(pwd,'reid')); addpath(fullfile(pwd,'arena_setup')); "
        f"run_full_analysis_pipeline('{dataset}', 'FlatMode', true, 'FlatClips', {{'{clip_stem}'}}, "
        f"'SkipArena', {skip_arena}, 'Fps', {fps});"
    )


def process_videos(cfg: AppConfig, limit: int | None = None) -> int:
    if cfg.tackletek is None:
        raise RuntimeError("tackletek section missing from config.yaml")

    registry = Registry(cfg.paths.registry_db)
    events = EventLog(cfg.paths.events_log)
    events.append("process_started", dataset=cfg.tackletek.dataset_name)

    pending = registry.list_by_status(["ingested"])
    if limit is not None:
        pending = pending[:limit]

    if not pending:
        print("No ingested videos waiting for processing.")
        events.append("process_finished", processed=0, failed=0)
        return 0

    matlab_dir = cfg.tackletek.matlab_dir
    if not matlab_dir.is_dir():
        raise RuntimeError(f"MATLAB dir not found: {matlab_dir}")

    processed = 0
    failed = 0

    for record in pending:
        source = Path(record.local_path)
        if not source.exists():
            registry.mark_process_failed(record.id, f"Source video missing: {source}")
            events.append("process_failed", filename=record.filename, error="source missing")
            failed += 1
            continue

        registry.mark_running(record.id)
        events.append("processing_started", filename=record.filename, job_id=record.id)

        try:
            staged = stage_video_for_matlab(cfg, source)
            clip_stem = staged.stem
            if staged.name.lower().endswith(".ts.mp4"):
                clip_stem = staged.name[:-7]

            matlab_cmd = _build_matlab_command(cfg, clip_stem)
            result = subprocess.run(
                ["matlab", "-batch", matlab_cmd],
                capture_output=True,
                text=True,
            )

            output_dir = _dataset_output_dir(cfg) / clip_stem
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "MATLAB failed")[-4000:]
                registry.mark_process_failed(record.id, err)
                events.append(
                    "processing_failed",
                    filename=record.filename,
                    job_id=record.id,
                    returncode=result.returncode,
                    error=err,
                )
                failed += 1
                print(result.stderr or result.stdout, file=sys.stderr)
                continue

            registry.mark_processed(record.id, output_dir)
            events.append(
                "processing_completed",
                filename=record.filename,
                job_id=record.id,
                output_dir=str(output_dir),
            )
            processed += 1
            print(f"Processed: {record.filename} -> {output_dir}")
        except Exception as exc:  # noqa: BLE001
            registry.mark_process_failed(record.id, str(exc))
            events.append(
                "processing_failed",
                filename=record.filename,
                job_id=record.id,
                error=str(exc),
            )
            failed += 1
            print(f"Failed: {record.filename}: {exc}", file=sys.stderr)

    events.append("process_finished", processed=processed, failed=failed)
    print(f"Process complete: processed={processed}, failed={failed}")
    return 1 if failed else 0
