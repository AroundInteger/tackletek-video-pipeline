from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DriveConfig:
    folder_id: str
    url: str


@dataclass
class PathsConfig:
    incoming_dir: Path
    previews_dir: Path
    registry_db: Path
    events_log: Path


@dataclass
class IngestConfig:
    video_extensions: list[str] = field(default_factory=lambda: [".mp4", ".mov"])
    stability_wait_s: int = 30
    ignore_patterns: list[str] = field(default_factory=list)


@dataclass
class TackleTekConfig:
    matlab_dir: Path
    onevone_root: Path
    dataset_name: str
    skip_arena: bool = True
    fps: int = 30


@dataclass
class AppConfig:
    root: Path
    drive: DriveConfig
    paths: PathsConfig
    ingest: IngestConfig
    tackletek: TackleTekConfig | None = None


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def load_config(config_path: Path | None = None) -> AppConfig:
    if config_path is None:
        config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    config_path = config_path.resolve()
    root = config_path.parent

    with config_path.open(encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    drive_raw = raw.get("drive", {})
    paths_raw = raw.get("paths", {})
    ingest_raw = raw.get("ingest", {})
    tackletek_raw = raw.get("tackletek")

    tackletek: TackleTekConfig | None = None
    if tackletek_raw:
        tackletek = TackleTekConfig(
            matlab_dir=_resolve(root, tackletek_raw["matlab_dir"]),
            onevone_root=_resolve(root, tackletek_raw["onevone_root"]),
            dataset_name=tackletek_raw["dataset_name"],
            skip_arena=bool(tackletek_raw.get("skip_arena", True)),
            fps=int(tackletek_raw.get("fps", 30)),
        )

    return AppConfig(
        root=root,
        drive=DriveConfig(
            folder_id=str(drive_raw.get("folder_id", "")),
            url=str(drive_raw.get("url", "")),
        ),
        paths=PathsConfig(
            incoming_dir=_resolve(root, paths_raw.get("incoming_dir", "data/incoming")),
            previews_dir=_resolve(root, paths_raw.get("previews_dir", "data/previews")),
            registry_db=_resolve(root, paths_raw.get("registry_db", "data/registry.db")),
            events_log=_resolve(root, paths_raw.get("events_log", "data/events.jsonl")),
        ),
        ingest=IngestConfig(
            video_extensions=[str(x).lower() for x in ingest_raw.get("video_extensions", [".mp4"])],
            stability_wait_s=int(ingest_raw.get("stability_wait_s", 30)),
            ignore_patterns=list(ingest_raw.get("ignore_patterns", [])),
        ),
        tackletek=tackletek,
    )


def ensure_data_dirs(cfg: AppConfig) -> None:
    cfg.paths.incoming_dir.mkdir(parents=True, exist_ok=True)
    cfg.paths.previews_dir.mkdir(parents=True, exist_ok=True)
    cfg.paths.registry_db.parent.mkdir(parents=True, exist_ok=True)
    cfg.paths.events_log.parent.mkdir(parents=True, exist_ok=True)


def apply_cli_overrides(
    cfg: AppConfig,
    *,
    incoming_dir: Path | str | None = None,
    stability_wait_s: int | None = None,
) -> AppConfig:
    if incoming_dir is not None:
        cfg.paths.incoming_dir = Path(incoming_dir).expanduser().resolve()
    if stability_wait_s is not None:
        cfg.ingest.stability_wait_s = stability_wait_s
    return cfg
