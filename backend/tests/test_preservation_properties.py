import asyncio
import json
import shutil
import subprocess
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.datastructures import Headers

import backend.app.analysis as analysis_module
import backend.app.story as story_module
from backend.app.analysis import analyze_video
from backend.app.color_lab import PALETTE, simulate_event_frame
from backend.app.contracts import (
    ColorSimulationRequest,
    SceneEvent,
    VisibilityScoreRequest,
)
from backend.app.main import app
from backend.app.media import (
    ALLOWED_VIDEO_TYPES,
    normalize_video,
    probe_duration_ms,
    save_upload,
)
from backend.app.story import generate_story, validate_story_grounding
from backend.app.visibility import score_event_frame
from backend.tests.test_story import story_request


requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg is not installed in this environment.",
)

MEDIA_CASES = (
    ("video/mp4", ".mp4", 5.2, ("-c:v", "libx264", "-pix_fmt", "yuv420p")),
    ("video/webm", ".webm", 8.0, ("-c:v", "libvpx-vp9", "-b:v", "180k")),
    ("video/quicktime", ".mov", 12.0, ("-c:v", "libx264", "-pix_fmt", "yuv420p")),
    ("video/x-matroska", ".mkv", 15.0, ("-c:v", "libx264", "-pix_fmt", "yuv420p")),
)


def make_event(
    *,
    motion: str = "medium",
    bounding_box: dict[str, float] | None = None,
) -> SceneEvent:
    return SceneEvent.model_validate(
        {
            "event_id": "ball-1",
            "timestamp_ms": 1_000,
            "object_label": "red ball",
            "category": "toy",
            "bounding_box": bounding_box
            or {
                "x_min": 0.35,
                "y_min": 0.35,
                "x_max": 0.65,
                "y_max": 0.65,
            },
            "confidence": 0.91,
            "visible_evidence": "A red ball is visible.",
            "motion_level": motion,
        }
    )


def make_red_on_green_frame() -> np.ndarray:
    frame = np.zeros((120, 160, 3), dtype=np.float32)
    frame[:, :] = [0.1, 0.75, 0.12]
    frame[42:78, 56:104] = [0.9, 0.08, 0.06]
    return frame


# **Validates: Requirements 3.1, 3.2**
@pytest.mark.parametrize(
    ("mime_type", "extension", "duration_seconds", "codec_options"),
    MEDIA_CASES,
    ids=("mp4-5s", "webm-8s", "mov-12s", "mkv-15s"),
)
@requires_ffmpeg
def test_property_supported_media_preserves_semantic_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mime_type: str,
    extension: str,
    duration_seconds: float,
    codec_options: tuple[str, ...],
) -> None:
    generated = tmp_path / f"generated{extension}"
    uploaded = tmp_path / f"uploaded{extension}"
    normalized = tmp_path / f"normalized-{extension[1:]}.mp4"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x2F6BFF:s=160x120:r=15",
            "-t",
            str(duration_seconds),
            *codec_options,
            str(generated),
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=True,
    )

    generated_bytes = generated.read_bytes()
    upload = UploadFile(
        file=BytesIO(generated_bytes),
        filename=f"clip{extension}",
        headers=Headers({"content-type": mime_type}),
    )
    saved_bytes = asyncio.run(
        save_upload(upload, uploaded, maximum_bytes=30 * 1024 * 1024)
    )
    observed_duration_ms = probe_duration_ms(uploaded)
    normalize_video(uploaded, normalized)
    normalized_duration_ms = probe_duration_ms(normalized)

    monkeypatch.setattr(
        analysis_module,
        "settings",
        replace(
            analysis_module.settings,
            demo_mode=False,
            gemini_api_key="",
            allow_demo_fallback=True,
        ),
    )
    analysis, source = analyze_video(normalized, observed_duration_ms)

    expected_duration_ms = round(duration_seconds * 1_000)
    assert ALLOWED_VIDEO_TYPES[mime_type] == extension
    assert saved_bytes == len(generated_bytes)
    assert saved_bytes < 30 * 1024 * 1024
    assert abs(observed_duration_ms - expected_duration_ms) <= 250
    assert abs(normalized_duration_ms - observed_duration_ms) <= 250
    assert normalized.stat().st_size > 0
    assert source == "demo"
    assert analysis.duration_ms == observed_duration_ms
    assert analysis.events
    assert all(event.timestamp_ms <= analysis.duration_ms for event in analysis.events)
    assert any("cached demo detections" in warning for warning in analysis.warnings)


# **Validates: Requirements 3.2, 3.7, 3.10**
@pytest.mark.parametrize("duration_ms", (5_000, 8_000, 15_000))
def test_property_generic_demo_fallback_remains_labeled_and_isolated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    duration_ms: int,
) -> None:
    monkeypatch.setattr(
        analysis_module,
        "settings",
        replace(
            analysis_module.settings,
            demo_mode=False,
            gemini_api_key="",
            allow_demo_fallback=True,
        ),
    )
    video = tmp_path / "normalized.mp4"
    video.write_bytes(b"normalized-video-placeholder")

    analysis, source = analyze_video(video, duration_ms)
    event = analysis.events[0]

    assert source == "demo"
    assert analysis.duration_ms == duration_ms
    assert any("cached demo detections" in warning for warning in analysis.warnings)

    with pytest.raises(ValidationError):
        VisibilityScoreRequest.model_validate(
            {
                "analysis_source": source,
                "events": [event.model_dump(mode="json")],
                "favorite_interest": "Ball",
            }
        )

    with pytest.raises(ValidationError):
        ColorSimulationRequest.model_validate(
            {
                "analysis_source": source,
                "event": event.model_dump(mode="json"),
            }
        )


# **Validates: Requirements 3.4, 3.10**
@pytest.mark.parametrize(
    ("motion", "favorite", "expected_motion", "expected_salience", "expected_level"),
    (
        ("none", "Ball", 0, 27, "low"),
        ("low", "Ball", 33, 39, "medium"),
        ("medium", "Ball", 67, 51, "medium"),
        ("high", "Ball", 100, 62, "medium"),
        ("medium", "Cats", 67, 41, "medium"),
    ),
)
def test_property_scientific_score_snapshot_is_exact(
    motion: str,
    favorite: str,
    expected_motion: int,
    expected_salience: int,
    expected_level: str,
) -> None:
    score = score_event_frame(
        make_red_on_green_frame(),
        make_event(motion=motion),
        favorite,
    )

    assert score.model_dump(mode="json") == {
        "event_id": "ball-1",
        "identification_confidence": 0.91,
        "human_contrast_score": 100,
        "dog_contrast_score": 15,
        "contrast_change": -85,
        "motion_score": expected_motion,
        "apparent_size_score": 60,
        "profile_relevance_score": 100 if favorite == "Ball" else 0,
        "salience_score": expected_salience,
        "salience_level": expected_level,
        "human_object_color": "#E6140F",
        "human_background_color": "#1ABF1F",
        "dog_object_color": "#928100",
        "dog_background_color": "#B3A035",
        "explanation": (
            "The object loses separation from its nearby background after the "
            "canine-vision approximation."
        ),
        "why": [
            *(
                ["The AI-inferred motion label increased the cue score."]
                if expected_motion >= 67
                else []
            ),
            "The transformed object/background contrast is low.",
            "The object occupies a prominent part of the frame.",
            *(
                ["The profile favorite added a small Curiosity Mode bonus."]
                if favorite == "Ball"
                else []
            ),
        ][:4],
    }


# **Validates: Requirements 3.4**
def test_property_ties_to_even_and_profile_bonus_remain_bounded() -> None:
    tie_box = {
        "x_min": 0.34375,
        "y_min": 0.34375,
        "x_max": 0.65625,
        "y_max": 0.65625,
    }
    matching = score_event_frame(
        make_red_on_green_frame(), make_event(bounding_box=tie_box), "Ball"
    )
    unrelated = score_event_frame(
        make_red_on_green_frame(), make_event(bounding_box=tie_box), "Cats"
    )

    assert matching.apparent_size_score == 62  # round(62.5), ties to even
    assert matching.profile_relevance_score == 100
    assert unrelated.profile_relevance_score == 0
    assert matching.salience_score - unrelated.salience_score == 10


# **Validates: Requirements 3.4, 3.10**
def test_property_six_color_palette_snapshot_is_exact() -> None:
    result = simulate_event_frame(make_red_on_green_frame(), make_event())

    assert [color_id for color_id, _, _ in PALETTE] == [
        "blue",
        "yellow",
        "red",
        "green",
        "orange",
        "purple",
    ]
    assert result.recommended_color_id == "blue"
    assert [
        (
            option.rank,
            option.color_id,
            option.human_contrast_score,
            option.dog_contrast_score,
            option.dog_contrast_gain,
        )
        for option in result.options
    ] == [
        (1, "blue", 100, 100, 85),
        (2, "purple", 100, 100, 85),
        (3, "yellow", 90, 36, 21),
        (4, "green", 37, 26, 11),
        (5, "red", 100, 23, 8),
        (6, "orange", 100, 16, 1),
    ]
    assert "not exact canine vision" in result.disclaimer
    assert "physical-product guarantee" in result.disclaimer


# **Validates: Requirements 3.6, 3.10**
def test_property_grounded_story_disclosures_remain_semantically_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = story_request()
    monkeypatch.setattr(
        story_module,
        "settings",
        replace(story_module.settings, demo_mode=True),
    )

    story, source = generate_story(request)
    validate_story_grounding(story, request)

    assert source == "template"
    assert story.featured_event_id == request.featured_event_id
    assert 16 <= len(story.narration_text.split()) <= 28
    assert story.voice_notice == (
        "Fictional dog voice based only on visible scene events."
    )
    assert {label for line in story.lines for label in line.object_labels} <= {
        event.object_label for event in request.events
    }


# **Validates: Requirements 3.7, 3.8**
def test_property_route_status_and_security_semantics_are_stable() -> None:
    with TestClient(app) as client:
        health = client.get(
            "/api/v1/health",
            headers={"X-Request-ID": "preservation-check"},
        )
        liveness = client.get("/api/v1/health/live")
        unknown_job = client.get(f"/api/v1/story-jobs/{'0' * 32}")
        invalid_media = client.post(
            "/api/v1/analyze-video",
            files={"file": ("clip.txt", b"not-video", "text/plain")},
        )

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert liveness.status_code == 200
    assert liveness.json() == {"status": "alive"}
    assert unknown_job.status_code == 404
    assert unknown_job.json()["detail"] == "Story job not found or expired."
    assert invalid_media.status_code == 415
    assert "Unsupported video type" in invalid_media.json()["detail"]

    assert health.headers["x-request-id"] == "preservation-check"
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["referrer-policy"] == "no-referrer"
    assert health.headers["x-frame-options"] == "DENY"


# **Validates: Requirements 3.8, 3.9**
def test_property_container_security_contract_remains_non_root() -> None:
    project_root = Path(__file__).resolve().parents[2]
    backend_dockerfile = (project_root / "Dockerfile.backend").read_text(
        encoding="utf-8"
    )
    frontend_dockerfile = (project_root / "frontend" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    compose = (project_root / "compose.yaml").read_text(encoding="utf-8")

    assert "USER pawspective" in backend_dockerfile
    assert "USER nextjs" in frontend_dockerfile
    assert "condition: service_healthy" in compose
    assert "X-Content-Type-Options" in (project_root / "backend" / "app" / "main.py").read_text(
        encoding="utf-8"
    )
