import json
from pathlib import Path
from shutil import copyfile

import pytest
from fastapi.testclient import TestClient

from backend.app.contracts import SceneAnalysisResponse
from backend.app.analysis import SceneAnalysisError
from backend.app.media import MediaValidationError
from backend.app.main import app
from backend.app.story import (
    StoryGenerationError,
    fallback_story,
)
from backend.app.story_render import StoryRenderError
from backend.app.voice import VoiceGenerationError
from backend.tests.test_story import story_request


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

def test_visibility_endpoint_scores_corrected_events(
    monkeypatch,
) -> None:
    import backend.app.main as main_module

    from backend.app.contracts import VisibilityAnalysisResponse

    payload = {
        "analysis_source": "gemini",
        "favorite_interest": "Ball",
        "events": [
            {
                "event_id": "ball-1",
                "timestamp_ms": 1_000,
                "object_label": "blue ball",
                "category": "toy",
                "bounding_box": {
                    "x_min": 0.2,
                    "y_min": 0.2,
                    "x_max": 0.5,
                    "y_max": 0.5,
                },
                "confidence": 0.92,
                "visible_evidence": "A blue ball is visible.",
                "motion_level": "medium",
            },
        ],
    }

    monkeypatch.setattr(main_module, "probe_duration_ms", lambda _: 8_000)
    monkeypatch.setattr(
        main_module,
        "normalize_video",
        lambda source, destination: copyfile(source, destination),
    )

    monkeypatch.setattr(
        main_module,
        "score_visibility_events",
        lambda *args: VisibilityAnalysisResponse.model_validate(
            {
                "scoring_version": "1.0",
                "method": "bbox-region-lab-v1",
                "warnings": [],
                "scores": [
                    {
                        "event_id": "ball-1",
                        "identification_confidence": 0.92,
                        "human_contrast_score": 70,
                        "dog_contrast_score": 84,
                        "contrast_change": 14,
                        "motion_score": 67,
                        "apparent_size_score": 60,
                        "profile_relevance_score": 100,
                        "salience_score": 75,
                        "salience_level": "high",
                        "human_object_color": "#2055D0",
                        "human_background_color": "#438A35",
                        "dog_object_color": "#3F6BC8",
                        "dog_background_color": "#8A813B",
                        "explanation": "The transformed regions remain distinct.",
                        "why": ["The transformed contrast is high."],
                    },
                ],
            },
        ),
    )

    response = client.post(
        "/api/v1/score-visibility",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
        data={"payload": json.dumps(payload)},
    )

    assert response.status_code == 200
    assert response.json()["scores"][0]["salience_score"] == 75


def test_visibility_endpoint_rejects_demo_events() -> None:
    response = client.post(
        "/api/v1/score-visibility",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
        data={
            "payload": json.dumps(
                {
                    "analysis_source": "demo",
                    "favorite_interest": "Ball",
                    "events": [],
                },
            ),
        },
    )

    assert response.status_code == 422


def story_payload() -> dict:
    return story_request().model_dump(mode="json")


def configure_story_pipeline(monkeypatch) -> None:
    import backend.app.main as main_module

    monkeypatch.setattr(
        main_module,
        "probe_duration_ms",
        lambda _: 8_000,
    )
    monkeypatch.setattr(
        main_module,
        "normalize_video",
        lambda source, destination: copyfile(source, destination),
    )
    monkeypatch.setattr(
        main_module,
        "generate_story",
        lambda request: (fallback_story(request), "template"),
    )
    monkeypatch.setattr(
        main_module,
        "synthesize_narration",
        lambda text, destination: destination.write_bytes(b"audio"),
    )
    monkeypatch.setattr(
        main_module,
        "render_story_reel",
        lambda *args: args[4].write_bytes(b"fake-story-mp4"),
    )


def test_story_endpoint_returns_downloadable_mp4(
    monkeypatch,
) -> None:
    configure_story_pipeline(monkeypatch)

    response = client.post(
        "/api/v1/render-story-reel",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
        data={"payload": json.dumps(story_payload())},
    )

    assert response.status_code == 200
    assert response.content == b"fake-story-mp4"
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["x-pawspective-story-source"] == "template"
    assert "Bruno-pawspective-reel.mp4" in response.headers[
        "content-disposition"
    ]
    assert response.headers["cache-control"] == "no-store"


def test_story_endpoint_rejects_unsupported_media() -> None:
    response = client.post(
        "/api/v1/render-story-reel",
        files={"file": ("clip.txt", b"text", "text/plain")},
        data={"payload": json.dumps(story_payload())},
    )

    assert response.status_code == 415


@pytest.mark.parametrize(
    ("duration_ms", "message"),
    [
        (4_999, "at least five seconds"),
        (15_001, "maximum accepted duration"),
    ],
)
def test_story_endpoint_rejects_invalid_duration(
    monkeypatch,
    duration_ms: int,
    message: str,
) -> None:
    import backend.app.main as main_module

    monkeypatch.setattr(
        main_module,
        "probe_duration_ms",
        lambda _: duration_ms,
    )

    response = client.post(
        "/api/v1/render-story-reel",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
        data={"payload": json.dumps(story_payload())},
    )

    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_story_endpoint_rejects_corrupt_video(
    monkeypatch,
) -> None:
    import backend.app.main as main_module

    monkeypatch.setattr(
        main_module,
        "probe_duration_ms",
        lambda _: (_ for _ in ()).throw(
            MediaValidationError(
                "The uploaded file is not a readable video.",
            ),
        ),
    )

    response = client.post(
        "/api/v1/render-story-reel",
        files={"file": ("clip.mp4", b"corrupt", "video/mp4")},
        data={"payload": json.dumps(story_payload())},
    )

    assert response.status_code == 422
    assert "not a readable video" in response.json()["detail"]


def test_story_endpoint_rejects_timestamp_after_video(
    monkeypatch,
) -> None:
    import backend.app.main as main_module

    payload = story_payload()
    payload["events"][0]["timestamp_ms"] = 8_001
    monkeypatch.setattr(
        main_module,
        "probe_duration_ms",
        lambda _: 8_000,
    )

    response = client.post(
        "/api/v1/render-story-reel",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
        data={"payload": json.dumps(payload)},
    )

    assert response.status_code == 422
    assert "timestamps exceed" in response.json()["detail"]


def test_story_endpoint_rejects_featured_event_without_score() -> None:
    payload = story_payload()
    payload["scores"] = [
        score
        for score in payload["scores"]
        if score["event_id"] != payload["featured_event_id"]
    ]

    response = client.post(
        "/api/v1/render-story-reel",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
        data={"payload": json.dumps(payload)},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "The Story Reel payload is invalid."


@pytest.mark.parametrize(
    ("dependency", "error", "status", "message"),
    [
        (
            "generate_story",
            StoryGenerationError("Gemini timed out"),
            502,
            "grounded story",
        ),
        (
            "synthesize_narration",
            VoiceGenerationError("ElevenLabs timed out"),
            502,
            "fictional dog voice",
        ),
        (
            "render_story_reel",
            StoryRenderError("FFmpeg is unavailable"),
            500,
            "FFmpeg is unavailable",
        ),
    ],
)
def test_story_endpoint_translates_pipeline_failures(
    monkeypatch,
    dependency: str,
    error: Exception,
    status: int,
    message: str,
) -> None:
    import backend.app.main as main_module

    configure_story_pipeline(monkeypatch)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(main_module, dependency, fail)

    response = client.post(
        "/api/v1/render-story-reel",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
        data={"payload": json.dumps(story_payload())},
    )

    assert response.status_code == status
    assert message in response.json()["detail"]
