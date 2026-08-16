import asyncio
import logging
import shutil
from pathlib import Path

from backend.app.contracts import StoryReelRequest
from backend.app.job_store import JobStore
from backend.app.settings import settings
from backend.app.story_pipeline import (
    PIPELINE_ERRORS,
    run_story_pipeline,
)


logger = logging.getLogger("uvicorn.error")


class StoryJobManager:
    def __init__(
        self,
        store: JobStore,
        jobs_directory: Path,
    ) -> None:
        self.store = store
        self.jobs_directory = jobs_directory
        self.semaphore: asyncio.Semaphore | None = None
        self.tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        self.jobs_directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.store.initialize()
        self.store.recover_interrupted_jobs()

        self.semaphore = asyncio.Semaphore(
            settings.max_concurrent_story_jobs,
        )

        self.cleanup_expired()

    async def stop(self) -> None:
        if not self.tasks:
            return

        done, pending = await asyncio.wait(
            self.tasks,
            timeout=5,
        )

        for task in pending:
            task.cancel()

        await asyncio.gather(
            *pending,
            return_exceptions=True,
        )

    def job_directory(self, job_id: str) -> Path:
        root = self.jobs_directory.resolve()
        destination = (
            self.jobs_directory / job_id
        ).resolve()

        if destination.parent != root:
            raise ValueError("Invalid job directory")

        return destination

    def enqueue(
        self,
        job_id: str,
        source_path: Path,
        request: StoryReelRequest,
    ) -> None:
        task = asyncio.create_task(
            self.run(job_id, source_path, request),
        )

        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def run(
        self,
        job_id: str,
        source_path: Path,
        request: StoryReelRequest,
    ) -> None:
        if self.semaphore is None:
            self.store.mark_failed(
                job_id,
                "The render queue is unavailable.",
            )
            return

        async with self.semaphore:
            self.store.mark_running(job_id)

            try:
                result = await asyncio.to_thread(
                    run_story_pipeline,
                    source_path,
                    request,
                    self.job_directory(job_id),
                    lambda value: self.store.update_progress(
                        job_id,
                        value,
                    ),
                )

                self.store.mark_completed(
                    job_id,
                    result.story_source,
                )

            except PIPELINE_ERRORS:
                logger.exception(
                    "Story job %s failed",
                    job_id,
                )
                self.store.mark_failed(
                    job_id,
                    (
                        "The Story Reel could not be completed. "
                        "Please retry with the original clip."
                    ),
                )

            except Exception:
                logger.exception(
                    "Unexpected Story job %s failure",
                    job_id,
                )
                self.store.mark_failed(
                    job_id,
                    "An unexpected rendering error occurred.",
                )

            finally:
                self.remove_intermediate_files(job_id)

    def remove_intermediate_files(
        self,
        job_id: str,
    ) -> None:
        directory = self.job_directory(job_id)

        for path in directory.iterdir():
            if path.name != "pawspective-reel.mp4":
                if path.is_file():
                    path.unlink(missing_ok=True)

    def cleanup_expired(self) -> None:
        for job_id in self.store.expired_job_ids(
            settings.job_ttl_seconds,
        ):
            directory = self.job_directory(job_id)

            if directory.exists():
                shutil.rmtree(directory)

            self.store.delete(job_id)