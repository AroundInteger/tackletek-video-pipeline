from __future__ import annotations

import argparse
from pathlib import Path

from .config import apply_cli_overrides, ensure_data_dirs, load_config
from .events import EventLog
from .ingest import ingest_videos
from .process import process_videos
from .registry import Registry
from .scanner import register_discovered_videos
from .sync import sync_from_drive


def _common_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--incoming-dir",
        type=Path,
        default=None,
        help="Folder of videos to scan/ingest (overrides config paths.incoming_dir)",
    )
    common.add_argument(
        "--stability-wait-s",
        type=int,
        default=None,
        help="Seconds to wait for file stability before ingest (use 0 for local folders)",
    )
    return common


def _load_cfg(args: argparse.Namespace):
    cfg = load_config(getattr(args, "config", None))
    apply_cli_overrides(
        cfg,
        incoming_dir=getattr(args, "incoming_dir", None),
        stability_wait_s=getattr(args, "stability_wait_s", None),
    )
    ensure_data_dirs(cfg)
    return cfg


def _print_status(cfg) -> int:
    registry = Registry(cfg.paths.registry_db)
    counts = registry.counts_by_status()
    print("Video pipeline status")
    print(f"  Incoming:  {cfg.paths.incoming_dir}")
    print(f"  Previews:  {cfg.paths.previews_dir}")
    print(f"  Registry:  {cfg.paths.registry_db}")
    print(f"  Events:    {cfg.paths.events_log}")
    print()
    if counts:
        print("Counts by status:")
        for status in sorted(counts):
            print(f"  {status:12s} {counts[status]}")
    else:
        print("No videos registered yet.")

    records = registry.list_all()
    if records:
        print()
        print("Recent videos:")
        for record in records[-10:]:
            preview = record.preview_path or "-"
            print(
                f"  [{record.status}] {record.filename} "
                f"(preview: {preview})"
            )
    return 0


def _print_tail_log(cfg, n: int) -> int:
    events = EventLog(cfg.paths.events_log)
    records = events.tail(n)
    if not records:
        print("No events logged yet.")
        return 0
    for record in records:
        ts = record.get("ts", "?")
        event = record.get("event", "?")
        extras = {k: v for k, v in record.items() if k not in {"ts", "event"}}
        if extras:
            detail = " ".join(f"{k}={v!r}" for k, v in extras.items())
            print(f"{ts}  {event}  {detail}")
        else:
            print(f"{ts}  {event}")
    return 0


def main(argv: list[str] | None = None) -> int:
    common = _common_parser()
    parser = argparse.ArgumentParser(
        description="TackleTek video pipeline: sync, ingest, process, status",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (default: repo root config.yaml)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sync_p = sub.add_parser("sync", help="Download videos from Google Drive")
    sync_p.add_argument("--dry-run", action="store_true", help="Print gdown command only")

    ingest_p = sub.add_parser(
        "ingest",
        parents=[common],
        help="Extract frame 0 previews for new stable videos",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ingest_p.add_argument("--force", action="store_true", help="Re-ingest even if already ingested")

    process_p = sub.add_parser("process", help="Run TackleTek MATLAB analysis on ingested videos")
    process_p.add_argument("--limit", type=int, default=None, help="Max videos to process this run")

    sub.add_parser(
        "scan",
        parents=[common],
        help="Register discovered videos without ingesting",
    )

    sub.add_parser(
        "status",
        parents=[common],
        help="Show registry summary",
    )

    tail_p = sub.add_parser("tail-log", help="Show recent event log entries")
    tail_p.add_argument("-n", type=int, default=20, help="Number of events to show")

    run_all_p = sub.add_parser(
        "run-all",
        parents=[common],
        help="sync + scan + ingest + process",
    )
    run_all_p.add_argument("--skip-sync", action="store_true")
    run_all_p.add_argument("--skip-process", action="store_true")
    run_all_p.add_argument("--limit", type=int, default=None)

    args = parser.parse_args(argv)

    if args.command == "sync":
        cfg = _load_cfg(args)
        return sync_from_drive(cfg, dry_run=args.dry_run)

    if args.command == "tail-log":
        cfg = _load_cfg(args)
        return _print_tail_log(cfg, args.n)

    cfg = _load_cfg(args)

    if args.command == "scan":
        register_discovered_videos(cfg)
        print(f"Scan complete ({cfg.paths.incoming_dir}).")
        return 0
    if args.command == "ingest":
        return ingest_videos(cfg, force=args.force)
    if args.command == "process":
        return process_videos(cfg, limit=args.limit)
    if args.command == "status":
        return _print_status(cfg)
    if args.command == "run-all":
        rc = 0
        if not args.skip_sync:
            rc = sync_from_drive(cfg) or rc
        register_discovered_videos(cfg)
        rc = ingest_videos(cfg) or rc
        if not args.skip_process:
            rc = process_videos(cfg, limit=args.limit) or rc
        return rc

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
