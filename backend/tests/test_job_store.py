import backend.app.job_store as job_store_module
from backend.app.job_store import JobStore


def test_job_lifecycle_and_expiration(
    tmp_path,
    monkeypatch,
) -> None:
    now = 1_000.0
    monkeypatch.setattr(
        job_store_module.time,
        "time",
        lambda: now,
    )

    store = JobStore(tmp_path / "jobs.sqlite3")
    store.initialize()

    completed_id = "a" * 32
    failed_id = "b" * 32

    created = store.create(
        completed_id,
        "bruno-pawspective-reel.mp4",
    )

    assert created.status == "queued"
    assert created.progress == 0
    assert created.filename == "bruno-pawspective-reel.mp4"

    store.mark_running(completed_id)
    assert store.get(completed_id).status == "running"

    store.update_progress(completed_id, 150)
    assert store.get(completed_id).progress == 99

    store.update_progress(completed_id, 42)
    assert store.get(completed_id).progress == 42

    store.mark_completed(completed_id, "gemini")
    completed = store.get(completed_id)

    assert completed.status == "completed"
    assert completed.progress == 100
    assert completed.story_source == "gemini"
    assert completed.error is None

    store.create(failed_id, "failed.mp4")
    store.mark_failed(failed_id, "x" * 300)
    failed = store.get(failed_id)

    assert failed.status == "failed"
    assert len(failed.error) == 240

    now += 301

    assert set(store.expired_job_ids(300)) == {
        completed_id,
        failed_id,
    }

    store.delete(failed_id)
    assert store.get(failed_id) is None


def test_recovers_interrupted_jobs(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.initialize()

    queued_id = "c" * 32
    running_id = "d" * 32
    completed_id = "e" * 32

    store.create(queued_id, "queued.mp4")
    store.create(running_id, "running.mp4")
    store.mark_running(running_id)
    store.create(completed_id, "completed.mp4")
    store.mark_completed(completed_id, "template")

    store.recover_interrupted_jobs()

    for job_id in (queued_id, running_id):
        record = store.get(job_id)

        assert record.status == "failed"
        assert "backend restart" in record.error

    assert store.get(completed_id).status == "completed"
