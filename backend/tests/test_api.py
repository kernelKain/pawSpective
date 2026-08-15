import json
from pathlib import Path
from shutil import copyfile

from fastapi.testclient import TestClient

from backend.app.contracts import SceneAnalysisResponse
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