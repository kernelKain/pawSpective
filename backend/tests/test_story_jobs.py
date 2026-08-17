import asyncio
import time
from threading import Event

import backend.app.story_jobs as story_jobs_module
from backend.app.job_store import JobStore
from backend.app.settings import settings
from backend.app.story import StoryGenerationError
from backend.app.story_jobs import StoryJobManager
from backend.app.story_pipeline import StoryPipelineResult
from backend.tests.test_story import story_request


def make_manager(tmp_path) -> tuple[JobStore, StoryJobManager]:
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.initialize()

    jobs_directory = tmp_path / "jobs"
    jobs_directory.mkdir()

    return (
        store,
        StoryJobManager(store, jobs_directory),
    )


def test_manager_runs_job_to_completion(
    tmp_path,
    monkeypatch,
) -> None:
    store, manager = make_manager(tmp_path)
    job_id = "1" * 32
    directory = manager.job_directory(job_id)
    directory.mkdir()
    source_path = directory / "source.mp4"
    source_path.write_bytes(b"video")
    store.create(job_id, "bruno.mp4")

    def fake_pipeline(
        source,
        request,
        work_directory,
        progress,
        check_cancelled,
    ) -> StoryPipelineResult:
        assert source == source_path
        check_cancelled()
        progress(55)
        output_path = (
            work_directory / "pawspective-reel.mp4"
        )
        output_path.write_bytes(b"rendered")

        return StoryPipelineResult(
            output_path=output_path,
            story_source="template",
            artifact_source="live_render",
            voice_source="elevenlabs",
            variation_id=request.variation_id,
            animation_seed=request.animation_seed,
            music_track_id="sunny-paws",
        )

    monkeypatch.setattr(
        story_jobs_module,
        "run_story_pipeline",
        fake_pipeline,
    )

    async def run() -> None:
        manager.semaphore = asyncio.Semaphore(1)
        await manager.run(
            job_id,
            source_path,
            story_request(),
        )

    asyncio.run(run())

    record = store.get(job_id)

    assert record.status == "completed"
    assert record.progress == 100
    assert record.story_source == "template"
    assert record.artifact_source == "live_render"
    assert record.voice_source == "elevenlabs"
    assert record.variation_id == "original"
    assert record.animation_seed == 0
    assert record.music_track_id == "sunny-paws"
    assert not source_path.exists()
    assert (
        directory / "pawspective-reel.mp4"
    ).read_bytes() == b"rendered"


def test_manager_records_pipeline_failure(
    tmp_path,
    monkeypatch,
) -> None:
    store, manager = make_manager(tmp_path)
    job_id = "2" * 32
    directory = manager.job_directory(job_id)
    directory.mkdir()
    source_path = directory / "source.mp4"
    source_path.write_bytes(b"video")
    store.create(job_id, "bruno.mp4")

    def fail_pipeline(*args, **kwargs):
        raise StoryGenerationError("Gemini failed")

    monkeypatch.setattr(
        story_jobs_module,
        "run_story_pipeline",
        fail_pipeline,
    )

    async def run() -> None:
        manager.semaphore = asyncio.Semaphore(1)
        await manager.run(
            job_id,
            source_path,
            story_request(),
        )

    asyncio.run(run())

    record = store.get(job_id)

    assert record.status == "failed"
    assert "could not be completed" in record.error
    assert not source_path.exists()


def test_cleanup_removes_expired_record_and_files(
    tmp_path,
) -> None:
    store, manager = make_manager(tmp_path)
    job_id = "3" * 32
    directory = manager.job_directory(job_id)
    directory.mkdir()
    (directory / "pawspective-reel.mp4").write_bytes(
        b"expired",
    )
    store.create(job_id, "bruno.mp4")

    with store.connect() as connection:
        connection.execute(
            "UPDATE story_jobs SET updated_at = ? WHERE job_id = ?",
            (
                time.time()
                - settings.job_ttl_seconds
                - 1,
                job_id,
            ),
        )

    manager.cleanup_expired()

    assert store.get(job_id) is None
    assert not directory.exists()


def test_running_cancellation_stops_work_and_removes_final_output(
    tmp_path,
    monkeypatch,
) -> None:
    store, manager = make_manager(tmp_path)
    job_id = "4" * 32
    directory = manager.job_directory(job_id)
    directory.mkdir()
    source_path = directory / "source.mp4"
    source_path.write_bytes(b"video")
    store.create(job_id, "cancelled.mp4")
    started = Event()

    def cancellable_pipeline(
        _source,
        _request,
        work_directory,
        _progress,
        check_cancelled,
    ) -> StoryPipelineResult:
        (work_directory / "pawspective-reel.mp4").write_bytes(b"partial")
        started.set()
        while True:
            check_cancelled()
            time.sleep(0.01)

    monkeypatch.setattr(
        story_jobs_module,
        "run_story_pipeline",
        cancellable_pipeline,
    )

    async def run() -> None:
        manager.semaphore = asyncio.Semaphore(1)
        task = asyncio.create_task(manager.run(job_id, source_path, story_request()))
        assert await asyncio.to_thread(started.wait, 2)
        assert manager.cancel(job_id)
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(run())

    record = store.get(job_id)
    assert record is not None
    assert record.status == "cancelled"
    assert not directory.exists()
