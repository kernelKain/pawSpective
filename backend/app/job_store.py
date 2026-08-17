import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


JobStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "expired",
]


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    status: JobStatus
    progress: int
    created_at: float
    updated_at: float
    error: str | None
    story_source: str | None
    artifact_source: str | None
    voice_source: str | None
    variation_id: str | None
    animation_seed: int | None
    music_track_id: str | None
    filename: str


PROVENANCE_COLUMNS = {
    "artifact_source": "TEXT",
    "voice_source": "TEXT",
    "variation_id": "TEXT",
    "animation_seed": "INTEGER",
    "music_track_id": "TEXT",
}


class JobStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS story_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    error TEXT,
                    story_source TEXT,
                    artifact_source TEXT,
                    voice_source TEXT,
                    variation_id TEXT,
                    animation_seed INTEGER,
                    music_track_id TEXT,
                    filename TEXT NOT NULL
                )
                """,
            )
            existing_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(story_jobs)"
                ).fetchall()
            }
            for column, column_type in PROVENANCE_COLUMNS.items():
                if column not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE story_jobs ADD COLUMN {column} {column_type}"
                    )
            connection.execute(
                """
                UPDATE story_jobs
                SET status = 'expired', updated_at = ?
                WHERE status = 'completed'
                  AND (
                    artifact_source IS NULL
                    OR voice_source IS NULL
                    OR variation_id IS NULL
                    OR animation_seed IS NULL
                    OR music_track_id IS NULL
                  )
                """,
                (time.time(),),
            )

    def create(
        self,
        job_id: str,
        filename: str,
    ) -> JobRecord:
        now = time.time()

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO story_jobs (
                    job_id,
                    status,
                    progress,
                    created_at,
                    updated_at,
                    error,
                    story_source,
                    filename
                )
                VALUES (?, 'queued', 0, ?, ?, NULL, NULL, ?)
                """,
                (job_id, now, now, filename),
            )

        record = self.get(job_id)

        if record is None:
            raise RuntimeError("Job creation failed")

        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    job_id,
                    status,
                    progress,
                    created_at,
                    updated_at,
                    error,
                    story_source,
                    artifact_source,
                    voice_source,
                    variation_id,
                    animation_seed,
                    music_track_id,
                    filename
                FROM story_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()

        if row is None:
            return None

        return JobRecord(
            job_id=row["job_id"],
            status=row["status"],
            progress=row["progress"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error=row["error"],
            story_source=row["story_source"],
            artifact_source=row["artifact_source"],
            voice_source=row["voice_source"],
            variation_id=row["variation_id"],
            animation_seed=row["animation_seed"],
            music_track_id=row["music_track_id"],
            filename=row["filename"],
        )

    def update_progress(
        self,
        job_id: str,
        progress: int,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE story_jobs
                SET progress = ?, updated_at = ?
                WHERE job_id = ?
                  AND status IN ('queued', 'running')
                """,
                (
                    max(0, min(99, progress)),
                    time.time(),
                    job_id,
                ),
            )

    def mark_running(self, job_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE story_jobs
                SET
                    status = 'running',
                    progress = 5,
                    updated_at = ?,
                    error = NULL
                WHERE job_id = ?
                  AND status = 'queued'
                """,
                (time.time(), job_id),
            )

    def mark_completed(
        self,
        job_id: str,
        story_source: str,
        *,
        artifact_source: str | None = None,
        voice_source: str | None = None,
        variation_id: str | None = None,
        animation_seed: int | None = None,
        music_track_id: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE story_jobs
                SET
                    status = 'completed',
                    progress = 100,
                    updated_at = ?,
                    error = NULL,
                    story_source = ?,
                    artifact_source = ?,
                    voice_source = ?,
                    variation_id = ?,
                    animation_seed = ?,
                    music_track_id = ?
                WHERE job_id = ?
                  AND status IN ('queued', 'running')
                """,
                (
                    time.time(),
                    story_source,
                    artifact_source,
                    voice_source,
                    variation_id,
                    animation_seed,
                    music_track_id,
                    job_id,
                ),
            )

    def mark_failed(
        self,
        job_id: str,
        message: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE story_jobs
                SET
                    status = 'failed',
                    updated_at = ?,
                    error = ?
                WHERE job_id = ?
                  AND status IN ('queued', 'running')
                """,
                (
                    time.time(),
                    message[:240],
                    job_id,
                ),
            )

    def mark_cancelled(self, job_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE story_jobs
                SET
                    status = 'cancelled',
                    updated_at = ?,
                    error = NULL
                WHERE job_id = ?
                  AND status IN ('queued', 'running')
                """,
                (time.time(), job_id),
            )
        return cursor.rowcount > 0

    def recover_interrupted_jobs(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE story_jobs
                SET
                    status = 'failed',
                    updated_at = ?,
                    error = 'Rendering was interrupted by a backend restart.'
                WHERE status IN ('queued', 'running')
                """,
                (time.time(),),
            )

    def expired_job_ids(
        self,
        ttl_seconds: int,
    ) -> list[str]:
        cutoff = time.time() - ttl_seconds

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT job_id
                FROM story_jobs
                WHERE updated_at < ?
                """,
                (cutoff,),
            ).fetchall()

        return [row["job_id"] for row in rows]

    def delete(self, job_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                DELETE FROM story_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            )