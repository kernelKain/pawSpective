import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.job_store import JobStore
from backend.app.main import app
from backend.app.rate_limit import SlidingWindowRateLimiter
from backend.app.settings import settings
from backend.app.story_jobs import StoryJobManager
from backend.tests.test_story import story_request


client = TestClient(app)


@pytest.fixture
def job_api(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.initialize()

    jobs_directory = tmp_path / "jobs"
    jobs_directory.mkdir()
    manager = StoryJobManager(store, jobs_directory)
    limiter = SlidingWindowRateLimiter(
        limit=5,
        window_seconds=3_600,
    )

    monkeypatch.setattr(
        main_module,
        "job_store",
        store,
    )
    monkeypatch.setattr(
        main_module,
        "story_job_manager",
        manager,
    )
    monkeypatch.setattr(
        main_module,
        "story_job_limiter",
        limiter,
    )
    monkeypatch.setattr(
        manager,
        "enqueue",
        lambda job_id, source_path, request: None,
    )

    return store, manager


def submit_story_job():
    return client.post(
        "/api/v1/story-jobs",
        files={
            "file": (
                "clip.mp4",
                b"synthetic-video",
                "video/mp4",
            ),
        },
        data={
            "payload": json.dumps(
                story_request().model_dump(mode="json"),
            ),
        },
    )


def test_job_submission_returns_http_202(job_api) -> None:
    store, manager = job_api

    response = submit_story_job()

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["status_url"] == (
        f"/api/v1/story-jobs/{body['job_id']}"
    )
    assert len(body["job_id"]) == 32

    record = store.get(body["job_id"])

    assert record.status == "queued"
    assert record.filename == (
        "Bruno-pawspective-reel.mp4"
    )
    assert manager.job_directory(
        body["job_id"],
    ).exists()


def test_polling_queued_running_completed(job_api) -> None:
    store, manager = job_api
    job_id = "a" * 32
    directory = manager.job_directory(job_id)
    directory.mkdir()
    store.create(job_id, "bruno.mp4")

    queued = client.get(
        f"/api/v1/story-jobs/{job_id}",
    )
    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"
    assert queued.json()["progress"] == 0

    store.mark_running(job_id)
    store.update_progress(job_id, 60)

    running = client.get(
        f"/api/v1/story-jobs/{job_id}",
    )
    assert running.status_code == 200
    assert running.json()["status"] == "running"
    assert running.json()["progress"] == 60
    assert running.json()["download_url"] is None

    output_path = directory / "pawspective-reel.mp4"
    output_path.write_bytes(b"rendered-mp4")
    store.mark_completed(job_id, "gemini")

    completed = client.get(
        f"/api/v1/story-jobs/{job_id}",
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["progress"] == 100
    assert completed.json()["story_source"] == "gemini"
    assert completed.json()["download_url"].endswith(
        "/download",
    )

    download = client.get(
        completed.json()["download_url"],
    )
    assert download.status_code == 200
    assert download.content == b"rendered-mp4"
    assert download.headers[
        "x-pawspective-story-source"
    ] == "gemini"


def test_failed_job_response(job_api) -> None:
    store, _ = job_api
    job_id = "b" * 32
    store.create(job_id, "failed.mp4")
    store.mark_running(job_id)
    store.mark_failed(job_id, "Rendering failed safely.")

    response = client.get(
        f"/api/v1/story-jobs/{job_id}",
    )

    assert response.status_code == 200
    assert response.json() == {
        "job_id": job_id,
        "status": "failed",
        "progress": 5,
        "error": "Rendering failed safely.",
        "story_source": None,
        "download_url": None,
    }


def test_download_before_completion_returns_404(
    job_api,
) -> None:
    store, _ = job_api
    job_id = "c" * 32
    store.create(job_id, "queued.mp4")

    response = client.get(
        f"/api/v1/story-jobs/{job_id}/download",
    )

    assert response.status_code == 404
    assert "not available" in response.json()["detail"]


@pytest.mark.parametrize(
    "job_id",
    [
        "not-a-job-id",
        "A" * 32,
        "0" * 31 + "!",
    ],
)
def test_unsafe_job_ids_return_404(
    job_api,
    job_id: str,
) -> None:
    response = client.get(
        f"/api/v1/story-jobs/{job_id}",
    )
    download = client.get(
        f"/api/v1/story-jobs/{job_id}/download",
    )

    assert response.status_code == 404
    assert download.status_code == 404


def test_rate_limit_returns_retry_after(
    job_api,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        main_module,
        "story_job_limiter",
        SlidingWindowRateLimiter(
            limit=1,
            window_seconds=3_600,
        ),
    )

    assert submit_story_job().status_code == 202

    response = submit_story_job()

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 1


def test_readiness_is_503_without_ffmpeg(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        replace(
            settings,
            demo_mode=True,
            media_directory=tmp_path / "media",
            jobs_directory=tmp_path / "jobs",
        ),
    )
    monkeypatch.setattr(
        main_module.shutil,
        "which",
        lambda command: (
            None
            if command == "ffmpeg"
            else "/usr/bin/ffprobe"
        ),
    )

    response = client.get(
        "/api/v1/health/ready",
    )

    assert response.status_code == 503
    assert "FFmpeg is unavailable" in response.json()[
        "detail"
    ]["problems"]


def test_readiness_is_503_without_required_secrets(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        replace(
            settings,
            demo_mode=False,
            gemini_api_key="",
            elevenlabs_api_key="",
            elevenlabs_dog_voice_id="",
            media_directory=tmp_path / "media",
            jobs_directory=tmp_path / "jobs",
        ),
    )
    monkeypatch.setattr(
        main_module.shutil,
        "which",
        lambda command: f"/usr/bin/{command}",
    )

    response = client.get(
        "/api/v1/health/ready",
    )

    assert response.status_code == 503
    problems = response.json()["detail"]["problems"]
    assert "Gemini configuration is missing" in problems
    assert "ElevenLabs configuration is missing" in problems
    assert (
        "ElevenLabs voice configuration is missing"
        in problems
    )
