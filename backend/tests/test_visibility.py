import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from backend.app.contracts import SceneEvent
from backend.app.media import normalize_video, probe_duration_ms
from backend.app.visibility import (
    AI_MOTION_SCORES,
    APPARENT_SIZE_WEIGHT,
    CANINE_MATRIX,
    DOG_CONTRAST_WEIGHT,
    MOTION_WEIGHT,
    PROFILE_RELEVANCE_WEIGHT,
    VisibilityScoringError,
    canine_approximation,
    score_event_frame,
    score_visibility_events,
)


def make_event(
    *,
    event_id: str = "ball-1",
    label: str = "red ball",
    motion: str = "medium",
    timestamp_ms: int = 1_000,
    bounding_box: dict[str, float] | None = None,
) -> SceneEvent:
    return SceneEvent.model_validate(
        {
            "event_id": event_id,
            "timestamp_ms": timestamp_ms,
            "object_label": label,
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


def test_canine_transform_matches_golden_rgb_values() -> None:
    pixels = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.25, 0.50, 0.75],
            [1.0, 1.0, 1.0],
        ],
        dtype=np.float32,
    )
    expected = np.array(
        [
            [0.63429904, 0.56074846, 0.0],
            [0.93406004, 0.83498490, 0.23909673],
            [0.0, 0.25011238, 0.98573300],
            [0.32374330, 0.46418370, 0.74501120],
            [1.0, 0.99999960, 1.0],
        ],
        dtype=np.float32,
    )

    np.testing.assert_allclose(
        canine_approximation(pixels),
        expected,
        atol=2e-6,
    )


def test_backend_matrix_matches_frontend_shader() -> None:
    project_root = Path(__file__).resolve().parents[2]
    shader_source = (
        project_root
        / "frontend"
        / "src"
        / "app"
        / "lib"
        / "canineVisionRenderer.ts"
    ).read_text(encoding="utf-8")
    transformed_block = re.search(
        r"vec3 transformed = vec3\((.*?)\);",
        shader_source,
        re.DOTALL,
    )

    assert transformed_block is not None

    terms = re.findall(
        r"([+-]?)\s*(\d+\.\d+)\s*\*\s*linearColor\.[rgb]",
        transformed_block.group(1),
    )
    coefficients = [
        -float(value) if operator == "-" else float(value)
        for operator, value in terms
    ]

    np.testing.assert_allclose(
        np.array(coefficients, dtype=np.float32).reshape(3, 3),
        CANINE_MATRIX,
        atol=1e-7,
    )


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


def test_known_red_on_green_frame_has_regression_scores() -> None:
    score = score_event_frame(
        make_red_on_green_frame(),
        make_event(),
        "Ball",
    )

    assert score.human_contrast_score == 100
    assert score.dog_contrast_score == 15
    assert score.contrast_change == -85
    assert score.apparent_size_score == 60
    assert score.salience_score == 51
    assert score.human_object_color == "#E6140F"
    assert score.human_background_color == "#1ABF1F"
    assert score.dog_object_color == "#928100"
    assert score.dog_background_color == "#B3A035"


@pytest.mark.parametrize(
    ("motion", "expected_motion", "expected_salience"),
    [
        ("none", 0, 27),
        ("low", 33, 39),
        ("medium", 67, 51),
        ("high", 100, 62),
    ],
)
def test_ai_motion_mapping_and_final_rounding(
    motion: str,
    expected_motion: int,
    expected_salience: int,
) -> None:
    score = score_event_frame(
        make_red_on_green_frame(),
        make_event(motion=motion),
        "Ball",
    )

    assert score.motion_score == expected_motion
    assert score.salience_score == expected_salience


def test_weight_constants_and_apparent_size_regression() -> None:
    assert set(AI_MOTION_SCORES.values()) == {0, 33, 67, 100}
    assert (
        MOTION_WEIGHT
        + DOG_CONTRAST_WEIGHT
        + APPARENT_SIZE_WEIGHT
        + PROFILE_RELEVANCE_WEIGHT
    ) == pytest.approx(1.0)

    score = score_event_frame(
        make_red_on_green_frame(),
        make_event(
            bounding_box={
                "x_min": 0.25,
                "y_min": 0.25,
                "x_max": 0.75,
                "y_max": 0.75,
            },
        ),
        "Cats",
    )

    assert score.apparent_size_score == 100
    assert score.salience_score == round(
        MOTION_WEIGHT * score.motion_score
        + DOG_CONTRAST_WEIGHT * score.dog_contrast_score
        + APPARENT_SIZE_WEIGHT * score.apparent_size_score
    )


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


requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg is not installed in this environment.",
)


@pytest.fixture(scope="module")
def normalized_visibility_video(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, int]:
    temporary_directory = tmp_path_factory.mktemp("visibility-video")
    source = temporary_directory / "source.mp4"
    normalized = temporary_directory / "normalized.mp4"

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

    return normalized, duration_ms


@requires_ffmpeg
def test_real_video_is_normalized_opened_seeked_and_scored(
    normalized_visibility_video: tuple[Path, int],
) -> None:
    video_path, duration_ms = normalized_visibility_video

    result = score_visibility_events(
        video_path,
        [make_event()],
        "Ball",
        duration_ms,
    )

    assert result.method == "bbox-region-lab-v1"
    assert len(result.scores) == 1
    assert result.scores[0].event_id == "ball-1"
    assert result.scores[0].human_contrast_score > 0
    assert result.warnings == []


@requires_ffmpeg
def test_real_video_returns_partial_warnings(
    normalized_visibility_video: tuple[Path, int],
) -> None:
    video_path, duration_ms = normalized_visibility_video
    tiny_box = {
        "x_min": 0.35,
        "y_min": 0.35,
        "x_max": 0.351,
        "y_max": 0.351,
    }

    result = score_visibility_events(
        video_path,
        [
            make_event(),
            make_event(event_id="tiny", bounding_box=tiny_box),
            make_event(
                event_id="late-frame",
                timestamp_ms=duration_ms + 2_000,
            ),
        ],
        "Ball",
        duration_ms + 3_000,
    )

    assert [score.event_id for score in result.scores] == ["ball-1"]
    assert any("tiny: object region is too small" in item for item in result.warnings)
    assert any("late-frame: its video frame could not be read" in item for item in result.warnings)


@requires_ffmpeg
def test_real_video_rejects_invalid_event_timestamps(
    normalized_visibility_video: tuple[Path, int],
) -> None:
    video_path, duration_ms = normalized_visibility_video

    with pytest.raises(
        VisibilityScoringError,
        match="timestamps exceed the video duration",
    ):
        score_visibility_events(
            video_path,
            [
                make_event(
                    event_id="outside-duration",
                    timestamp_ms=duration_ms + 1,
                ),
            ],
            "Ball",
            duration_ms,
        )


@requires_ffmpeg
def test_real_video_reports_when_all_events_fail(
    normalized_visibility_video: tuple[Path, int],
) -> None:
    video_path, duration_ms = normalized_visibility_video

    with pytest.raises(
        VisibilityScoringError,
        match="No corrected event could be scored",
    ):
        score_visibility_events(
            video_path,
            [
                make_event(
                    event_id="unreadable",
                    timestamp_ms=duration_ms + 2_000,
                ),
            ],
            "Ball",
            duration_ms + 3_000,
        )


def test_unreadable_video_is_rejected(tmp_path: Path) -> None:
    unreadable = tmp_path / "unreadable.mp4"
    unreadable.write_bytes(b"not a video")

    with pytest.raises(
        VisibilityScoringError,
        match="could not be opened",
    ):
        score_visibility_events(
            unreadable,
            [make_event()],
            "Ball",
            5_000,
        )
