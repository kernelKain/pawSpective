import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.contracts import SceneAnalysisResponse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PATH = PROJECT_ROOT / "examples" / "scene-analysis.example.json"


def load_example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def test_example_response_is_valid() -> None:
    result = SceneAnalysisResponse.model_validate(load_example())

    assert result.analysis_version == "1.0"
    assert result.duration_ms == 8000
    assert len(result.events) == 3
    assert result.events[0].object_label == "blue ball"


def test_rejects_inverted_bounding_box() -> None:
    payload = load_example()
    payload["events"][0]["bounding_box"]["x_min"] = 0.8
    payload["events"][0]["bounding_box"]["x_max"] = 0.2

    with pytest.raises(ValidationError, match="x_min must be smaller"):
        SceneAnalysisResponse.model_validate(payload)


def test_rejects_out_of_range_coordinate() -> None:
    payload = load_example()
    payload["events"][0]["bounding_box"]["y_max"] = 1.4

    with pytest.raises(ValidationError):
        SceneAnalysisResponse.model_validate(payload)


def test_rejects_timestamp_after_video_ends() -> None:
    payload = load_example()
    payload["events"][0]["timestamp_ms"] = 9000

    with pytest.raises(
        ValidationError,
        match="timestamps exceed video duration",
    ):
        SceneAnalysisResponse.model_validate(payload)


def test_rejects_duplicate_event_ids() -> None:
    payload = load_example()
    payload["events"][1]["event_id"] = payload["events"][0]["event_id"]

    with pytest.raises(ValidationError, match="event_id values must be unique"):
        SceneAnalysisResponse.model_validate(payload)


def test_rejects_unknown_fields() -> None:
    payload = load_example()
    payload["events"][0]["dog_is_watching"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SceneAnalysisResponse.model_validate(payload)


def test_rejects_invalid_category() -> None:
    payload = load_example()
    payload["events"][0]["category"] = "emotion"

    with pytest.raises(ValidationError):
        SceneAnalysisResponse.model_validate(payload)


def test_allows_empty_events_with_warning() -> None:
    payload = load_example()
    payload["events"] = []
    payload["warnings"] = [
        "No sufficiently clear objects were visible in the supplied frames."
    ]

    result = SceneAnalysisResponse.model_validate(payload)

    assert result.events == []
    assert len(result.warnings) == 1