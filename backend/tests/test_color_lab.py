import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.color_lab import (
    PALETTE,
    ColorSimulationError,
    hex_to_rgb,
    simulate_event_frame,
    simulate_object_colors,
)
from backend.app.contracts import ColorSimulationResponse, SceneEvent
from backend.app.main import app
from backend.app.media import normalize_video, probe_duration_ms


client = TestClient(app)


def make_event(
    *,
    timestamp_ms: int = 1_000,
    bounding_box: dict[str, float] | None = None,
) -> SceneEvent:
    return SceneEvent.model_validate(
        {
            "event_id": "toy-1",
            "timestamp_ms": timestamp_ms,
            "object_label": "red ball",
            "category": "toy",
            "bounding_box": bounding_box
            or {
                "x_min": 0.35,
                "y_min": 0.35,
                "x_max": 0.65,
                "y_max": 0.65,
            },
            "confidence": 0.92,
            "visible_evidence": "A red ball is visible.",
            "motion_level": "medium",
        }
    )


def make_red_on_green_frame() -> np.ndarray:
    frame = np.zeros((120, 160, 3), dtype=np.float32)
    frame[:, :] = [0.10, 0.75, 0.12]
    frame[42:78, 56:104] = [0.90, 0.08, 0.06]
    return frame


def test_hex_to_rgb() -> None:
    np.testing.assert_allclose(
        hex_to_rgb("#FF8000"),
        np.array([1.0, 128 / 255, 0.0], dtype=np.float32),
    )


def test_hex_to_rgb_rejects_invalid_digits() -> None:
    with pytest.raises(ValueError, match="six-digit"):
        hex_to_rgb("#GG0000")


def test_fixed_palette_is_complete() -> None:
    assert [color_id for color_id, _, _ in PALETTE] == [
        "blue",
        "yellow",
        "red",
        "green",
        "orange",
        "purple",
    ]


def test_simulation_ranks_all_colors_deterministically() -> None:
    frame = make_red_on_green_frame()
    event = make_event()
    first = simulate_event_frame(frame, event)
    second = simulate_event_frame(frame, event)

    assert first == second
    assert len(first.options) == 6
    assert len({option.color_id for option in first.options}) == 6
    assert [option.rank for option in first.options] == list(range(1, 7))
    assert first.recommended_color_id == first.options[0].color_id
    assert all(
        first.options[index].dog_contrast_score
        >= first.options[index + 1].dog_contrast_score
        for index in range(5)
    )


def test_tiny_region_is_rejected() -> None:
    event = make_event(
        bounding_box={
            "x_min": 0.35,
            "y_min": 0.35,
            "x_max": 0.351,
            "y_max": 0.351,
        }
    )

    with pytest.raises(ColorSimulationError, match="too small"):
        simulate_event_frame(make_red_on_green_frame(), event)


def test_timestamp_outside_video_duration_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ColorSimulationError, match="exceeds"):
        simulate_object_colors(
            tmp_path / "unused.mp4",
            make_event(timestamp_ms=5_001),
            5_000,
        )


def test_unreadable_video_is_rejected(tmp_path: Path) -> None:
    unreadable = tmp_path / "unreadable.mp4"
    unreadable.write_bytes(b"not a video")

    with pytest.raises(ColorSimulationError, match="could not be opened"):
        simulate_object_colors(unreadable, make_event(), 5_000)


def test_api_rejects_demo_source_and_invalid_mime() -> None:
    payload = {
        "analysis_source": "demo",
        "event": make_event().model_dump(mode="json"),
    }
    demo_response = client.post(
        "/api/v1/simulate-object-colors",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
        data={"payload": json.dumps(payload)},
    )
    mime_response = client.post(
        "/api/v1/simulate-object-colors",
        files={"file": ("clip.txt", b"video", "text/plain")},
        data={"payload": json.dumps(payload)},
    )

    assert demo_response.status_code == 422
    assert mime_response.status_code == 415


def test_api_removes_temporary_files(monkeypatch, tmp_path: Path) -> None:
    import backend.app.main as main_module

    tmp_path.mkdir(exist_ok=True)
    monkeypatch.setattr(
        main_module,
        "settings",
        replace(main_module.settings, media_directory=tmp_path),
    )
    monkeypatch.setattr(main_module, "probe_duration_ms", lambda _: 6_000)

    def fake_normalize(source: Path, target: Path) -> None:
        assert source.exists()
        target.write_bytes(b"normalized")

    expected = simulate_event_frame(make_red_on_green_frame(), make_event())

    def fake_simulate(path: Path, event: SceneEvent, duration: int):
        assert path.exists()
        assert event.event_id == "toy-1"
        assert duration == 6_000
        return expected

    monkeypatch.setattr(main_module, "normalize_video", fake_normalize)
    monkeypatch.setattr(main_module, "simulate_object_colors", fake_simulate)

    response = client.post(
        "/api/v1/simulate-object-colors",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
        data={
            "payload": json.dumps(
                {
                    "analysis_source": "gemini",
                    "event": make_event().model_dump(mode="json"),
                }
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["recommended_color_id"] == expected.recommended_color_id
    assert list(tmp_path.iterdir()) == []


def test_exported_schema_matches_model() -> None:
    project_root = Path(__file__).resolve().parents[2]
    schema_path = project_root / "contracts" / "color-simulation.schema.json"

    assert json.loads(schema_path.read_text(encoding="utf-8")) == (
        ColorSimulationResponse.model_json_schema()
    )


requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg is not installed in this environment.",
)


@requires_ffmpeg
def test_real_normalized_video_is_seeked_and_simulated(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    normalized = tmp_path / "normalized.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x1ABF1F:s=320x240:r=15",
            "-vf",
            "drawbox=x=112:y=84:w=96:h=72:color=0xE6140F:t=fill",
            "-t",
            "5.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    duration_ms = probe_duration_ms(source)
    normalize_video(source, normalized)

    result = simulate_object_colors(normalized, make_event(), duration_ms)

    assert result.event_id == "toy-1"
    assert len(result.options) == 6
