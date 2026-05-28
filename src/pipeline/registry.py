from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class VideoRecord:
    id: str
    filename: str
    local_path: str
    file_size: int
    mtime: float
    status: str
    preview_path: str | None
    discovered_at: str
    ingested_at: str | None
    processed_at: str | None
    error_message: str | None
    output_dir: str | None


class Registry:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS videos (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    local_path TEXT NOT NULL UNIQUE,
                    file_size INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    status TEXT NOT NULL,
                    preview_path TEXT,
                    discovered_at TEXT NOT NULL,
                    ingested_at TEXT,
                    processed_at TEXT,
                    error_message TEXT,
                    output_dir TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status)")
            conn.commit()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> VideoRecord:
        return VideoRecord(
            id=row["id"],
            filename=row["filename"],
            local_path=row["local_path"],
            file_size=row["file_size"],
            mtime=row["mtime"],
            status=row["status"],
            preview_path=row["preview_path"],
            discovered_at=row["discovered_at"],
            ingested_at=row["ingested_at"],
            processed_at=row["processed_at"],
            error_message=row["error_message"],
            output_dir=row["output_dir"],
        )

    def get_by_path(self, local_path: Path) -> VideoRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM videos WHERE local_path = ?",
                (str(local_path.resolve()),),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def upsert_discovered(
        self,
        filename: str,
        local_path: Path,
        file_size: int,
        mtime: float,
    ) -> tuple[VideoRecord, bool]:
        local_path = local_path.resolve()
        existing = self.get_by_path(local_path)
        if existing:
            if existing.file_size == file_size and existing.mtime == mtime:
                return existing, False
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE videos
                    SET file_size = ?, mtime = ?, status = 'discovered',
                        preview_path = NULL, ingested_at = NULL,
                        processed_at = NULL, error_message = NULL, output_dir = NULL
                    WHERE id = ?
                    """,
                    (file_size, mtime, existing.id),
                )
                conn.commit()
            updated = self.get_by_path(local_path)
            assert updated is not None
            return updated, True

        record_id = str(uuid.uuid4())
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO videos (
                    id, filename, local_path, file_size, mtime, status,
                    preview_path, discovered_at, ingested_at, processed_at,
                    error_message, output_dir
                ) VALUES (?, ?, ?, ?, ?, 'discovered', NULL, ?, NULL, NULL, NULL, NULL)
                """,
                (record_id, filename, str(local_path), file_size, mtime, now),
            )
            conn.commit()
        created = self.get_by_path(local_path)
        assert created is not None
        return created, True

    def mark_ingested(self, record_id: str, preview_path: Path) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE videos
                SET status = 'ingested', preview_path = ?, ingested_at = ?, error_message = NULL
                WHERE id = ?
                """,
                (str(preview_path.resolve()), _utc_now_iso(), record_id),
            )
            conn.commit()

    def mark_failed(self, record_id: str, error_message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE videos
                SET status = 'failed', error_message = ?
                WHERE id = ?
                """,
                (error_message, record_id),
            )
            conn.commit()

    def mark_running(self, record_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE videos SET status = 'running', error_message = NULL WHERE id = ?",
                (record_id,),
            )
            conn.commit()

    def mark_processed(self, record_id: str, output_dir: Path) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE videos
                SET status = 'completed', processed_at = ?, output_dir = ?, error_message = NULL
                WHERE id = ?
                """,
                (_utc_now_iso(), str(output_dir.resolve()), record_id),
            )
            conn.commit()

    def mark_process_failed(self, record_id: str, error_message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE videos
                SET status = 'failed', error_message = ?
                WHERE id = ?
                """,
                (error_message, record_id),
            )
            conn.commit()

    def list_by_status(self, statuses: Iterable[str]) -> list[VideoRecord]:
        status_list = list(statuses)
        placeholders = ",".join("?" for _ in status_list)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM videos WHERE status IN ({placeholders}) ORDER BY discovered_at",
                status_list,
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def counts_by_status(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM videos GROUP BY status"
            ).fetchall()
        return {row["status"]: row["n"] for row in rows}

    def list_all(self) -> list[VideoRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM videos ORDER BY discovered_at").fetchall()
        return [self._row_to_record(row) for row in rows]
