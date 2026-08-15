import json
from pathlib import Path
from shutil import copyfile

from fastapi.testclient import TestClient

from backend.app.contracts import SceneAnalysisResponse
from backend.app.analysis import SceneAnalysisError
from backend.app.media import MediaValidationError
from backend.app.main import app


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PATH = (
    PROJECT_ROOT
    / "examples"
    / "scene-analysis.example.json"
)

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_rejects_unsupported_media_type() -> None:
    response = client.post(
        "/api/v1/analyze-video",
        files={
            "file": (
                "clip.txt",
                b"not a video",
                "text/plain",
            ),
        },
    )

    assert response.status_code == 415


def test_rejects_empty_video() -> None:
    response = client.post(
        "/api/v1/analyze-video",
        files={"file": ("clip.mp4", b"", "video/mp4")},
    )

    assert response.status_code == 422
    assert "empty" in response.json()["detail"]


def test_rejects_video_outside_duration_limits(monkeypatch) -> None:
    import backend.app.main as main_module

    for duration_ms, expected_message in [
        (4_999, "at least five seconds"),
        (15_001, "maximum accepted duration"),
    ]:
        monkeypatch.setattr(
            main_module,
            "probe_duration_ms",
            lambda _, duration=duration_ms: duration,
        )

        response = client.post(
            "/api/v1/analyze-video",
            files={"file": ("clip.mp4", b"video", "video/mp4")},
        )

        assert response.status_code == 422
        assert expected_message in response.json()["detail"]


def test_translates_media_failure_to_validation_response(monkeypatch) -> None:
    import backend.app.main as main_module

    def fail_probe(_: Path) -> int:
        raise MediaValidationError("Reading the video metadata timed out.")

    monkeypatch.setattr(main_module, "probe_duration_ms", fail_probe)

    response = client.post(
        "/api/v1/analyze-video",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
    )

    assert response.status_code == 422
    assert "timed out" in response.json()["detail"]


def test_translates_scene_analysis_failure_to_gateway_response(
    monkeypatch,
) -> None:
    import backend.app.main as main_module

    monkeypatch.setattr(main_module, "probe_duration_ms", lambda _: 8_000)
    monkeypatch.setattr(
        main_module,
        "normalize_video",
        lambda source, destination: copyfile(source, destination),
    )

    def fail_analysis(*args):
        raise SceneAnalysisError("Gemini failed")

    monkeypatch.setattr(main_module, "analyze_video", fail_analysis)

    response = client.post(
        "/api/v1/analyze-video",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
    )

    assert response.status_code == 502
    assert "temporarily unavailable" in response.json()["detail"]


def test_accepts_valid_video_pipeline(
    monkeypatch,
) -> None:
    import backend.app.main as main_module

    payload = json.loads(
        EXAMPLE_PATH.read_text(encoding="utf-8"),
    )

    def fake_probe(_: Path) -> int:
        return 8_000

    def fake_normalize(
        source_path: Path,
        destination_path: Path,
    ) -> None:
        copyfile(source_path, destination_path)

    def fake_analyze(
        _: Path,
        duration_ms: int,
    ) -> tuple[SceneAnalysisResponse, str]:
        payload["duration_ms"] = duration_ms

        return (
            SceneAnalysisResponse.model_validate(payload),
            "demo",
        )

    monkeypatch.setattr(
        main_module,
        "probe_duration_ms",
        fake_probe,
    )
    monkeypatch.setattr(
        main_module,
        "normalize_video",
        fake_normalize,
    )
    monkeypatch.setattr(
        main_module,
        "analyze_video",
        fake_analyze,
    )

    response = client.post(
        "/api/v1/analyze-video",
        files={
            "file": (
                "clip.webm",
                b"synthetic-video-data",
                "video/webm",
            ),
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["source"] == "demo"
    assert len(body["analysis"]["events"]) == 3
