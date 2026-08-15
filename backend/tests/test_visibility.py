import numpy as np

from backend.app.contracts import SceneEvent
from backend.app.visibility import (
    canine_approximation,
    score_event_frame,
)


def make_event(
    *,
    label: str = "red ball",
    motion: str = "medium",
) -> SceneEvent:
    return SceneEvent.model_validate(
        {
            "event_id": "ball-1",
            "timestamp_ms": 1_000,
            "object_label": label,
            "category": "toy",
            "bounding_box": {
                "x_min": 0.35,
                "y_min": 0.35,
                "x_max": 0.65,
                "y_max": 0.65,
            },
            "confidence": 0.91,
            "visible_evidence": "A red ball is visible.",
            "motion_level": motion,
        },
    )


def make_red_on_green_frame() -> np.ndarray:
    frame = np.zeros((120, 160, 3), dtype=np.float32)
    frame[:, :] = [0.1, 0.75, 0.12]
    frame[42:78, 56:104] = [0.9, 0.08, 0.06]

    return frame


def test_canine_transform_stays_in_display_range() -> None:
    pixels = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )

    transformed = canine_approximation(pixels)

    assert transformed.shape == pixels.shape
    assert np.all(transformed >= 0.0)
    assert np.all(transformed <= 1.0)


def test_scores_are_bounded_and_explained() -> None:
    score = score_event_frame(
        make_red_on_green_frame(),
        make_event(),
        "Ball",
    )

    assert 0 <= score.human_contrast_score <= 100
    assert 0 <= score.dog_contrast_score <= 100
    assert 0 <= score.salience_score <= 100
    assert score.profile_relevance_score == 100
    assert score.explanation
    assert score.why


def test_profile_bonus_changes_salience_by_at_most_ten() -> None:
    frame = make_red_on_green_frame()
    event = make_event()

    matching = score_event_frame(frame, event, "Ball")
    unrelated = score_event_frame(frame, event, "Cats")

    assert matching.profile_relevance_score == 100
    assert unrelated.profile_relevance_score == 0
    assert matching.salience_score - unrelated.salience_score == 10


def test_sniffing_never_creates_visible_object_bonus() -> None:
    score = score_event_frame(
        make_red_on_green_frame(),
        make_event(),
        "Sniffing",
    )

    assert score.profile_relevance_score == 0