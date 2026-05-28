from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pipeline.config import AppConfig, DriveConfig, IngestConfig, PathsConfig, load_config
from pipeline.ingest import extract_first_frame, ingest_videos, preview_path_for_video
from pipeline.registry import Registry
from pipeline.scanner import discover_videos, register_discovered_videos


@pytest.fixture
def tmp_cfg(tmp_path: Path) -> AppConfig:
    incoming = tmp_path / "incoming"
    previews = tmp_path / "previews"
    incoming.mkdir()
    previews.mkdir()
    return AppConfig(
        root=tmp_path,
        drive=DriveConfig(folder_id="test", url="https://example.com"),
        paths=PathsConfig(
            incoming_dir=incoming,
            previews_dir=previews,
            registry_db=tmp_path / "registry.db",
            events_log=tmp_path / "events.jsonl",
        ),
        ingest=IngestConfig(
            video_extensions=[".mp4"],
            stability_wait_s=0,
            ignore_patterns=["*.jpg"],
        ),
    )


def test_discover_ignores_non_videos(tmp_cfg: AppConfig) -> None:
    tmp_cfg.paths.incoming_dir.joinpath("notes.csv").write_text("x")
    tmp_cfg.paths.incoming_dir.joinpath("photo.jpg").write_text("x")
    fixture = Path(__file__).parent / "fixtures" / "sample.mp4"
    if not fixture.exists():
        pytest.skip("Run tests/make_fixture_video.py to create sample.mp4")
    shutil.copy(fixture, tmp_cfg.paths.incoming_dir / "sample.mp4")
    videos = discover_videos(tmp_cfg)
    assert len(videos) == 1
    assert videos[0].name == "sample.mp4"


def test_extract_first_frame(tmp_cfg: AppConfig) -> None:
    fixture = Path(__file__).parent / "fixtures" / "sample.mp4"
    if not fixture.exists():
        pytest.skip("Run tests/make_fixture_video.py to create sample.mp4")
    video = tmp_cfg.paths.incoming_dir / "sample.mp4"
    shutil.copy(fixture, video)
    preview = preview_path_for_video(tmp_cfg, video)
    width, height = extract_first_frame(video, preview)
    assert preview.exists()
    assert width > 0 and height > 0


def test_ingest_registers_and_is_idempotent(tmp_cfg: AppConfig) -> None:
    fixture = Path(__file__).parent / "fixtures" / "sample.mp4"
    if not fixture.exists():
        pytest.skip("Run tests/make_fixture_video.py to create sample.mp4")
    shutil.copy(fixture, tmp_cfg.paths.incoming_dir / "sample.mp4")

    assert ingest_videos(tmp_cfg) == 0
    registry = Registry(tmp_cfg.paths.registry_db)
    counts = registry.counts_by_status()
    assert counts.get("ingested", 0) == 1

    assert ingest_videos(tmp_cfg) == 0
    counts_after = registry.counts_by_status()
    assert counts_after.get("ingested", 0) == 1


def test_load_default_config() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_config(repo_root / "config.yaml")
    assert cfg.drive.folder_id
    assert cfg.paths.incoming_dir.name == "incoming"
