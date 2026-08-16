import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from backend.app import demo_cache
from backend.app.contracts import SceneEvent, StoryReelRequest


EVENT = {
    "event_id": "red-toy",
    "timestamp_ms": 2_000,
    "object_label": "red toy",
    "category": "toy",
    "bounding_box": {
        "x_min": 0.1,
        "y_min": 0.2,
        "x_max": 0.4,
        "y_max": 0.6,
    },
    "confidence": 0.93,
    "visible_evidence": "A red toy is visible on green grass.",
    "motion_level": "medium",
}

SCORE = {
    "event_id": "red-toy",
    "identification_confidence": 0.93,
    "human_contrast_score": 62,
    "dog_contrast_score": 34,
    "contrast_change": -28,
    "motion_score": 65,
    "apparent_size_score": 40,
    "profile_relevance_score": 100,
    "salience_score": 67,
    "salience_level": "high",
    "human_object_color": "#CC3322",
    "human_background_color": "#338844",
    "dog_object_color": "#887744",
    "dog_background_color": "#777744",
    "explanation": "The toy remains visible but loses chromatic contrast.",
    "why": ["medium motion"],
}


def story_request() -> dict[str, object]:
    return {
        "analysis_source": "controlled_demo",
        "style": "nature_documentary",
        "profile": {
            "owner_name": "Demo handler",
            "dog_name": "Scout",
            "breed": "Mixed breed",
            "age": "Adult",
            "size": "Medium",
            "personality_tags": ["Curious"],
            "favorite_interest": "Ball",
        },
        "events": [EVENT],
        "scores": [SCORE],
        "featured_event_id": "red-toy",
    }


def build_cache(monkeypatch: pytest.MonkeyPatch, root: Path) -> Path:
    monkeypatch.setattr(
        demo_cache,
        "settings",
        replace(
            demo_cache.settings,
            controlled_demo_enabled=True,
            demo_cache_directory=root,
        ),
    )
    clip = root / demo_cache.CLIP_FILENAME
    clip.write_bytes(b"verified controlled clip")
    analysis = {
        "analysis_version": "1.0",
        "duration_ms": 8_000,
        "events": [EVENT],
        "warnings": [],
    }
    story = {
        "story_version": "1.0",
        "style": "nature_documentary",
        "title": "Scout on patrol",
        "lines": [
            {
                "event_ids": ["red-toy"],
                "object_labels": ["red toy"],
                "text": "Scout approaches the red toy while the grass frames a bright little expedition for our curious field observer today.",
            },
            {
                "event_ids": ["red-toy"],
                "object_labels": ["red toy"],
                "text": "A measured burst of motion turns this ordinary play session into a grand and carefully documented backyard discovery.",
            },
            {
                "event_ids": ["red-toy"],
                "object_labels": ["red toy"],
                "text": "The evidence ends with Scout ready for another joyful pass across the green stage and toward the waiting toy.",
            },
        ],
        "featured_event_id": "red-toy",
        "voice_notice": "Fictional dog voice based only on visible scene events.",
    }
    (root / demo_cache.ANALYSIS_FILENAME).write_text(json.dumps(analysis))
    (root / demo_cache.STORY_REQUEST_FILENAME).write_text(
        json.dumps(story_request())
    )
    (root / demo_cache.STORY_FILENAME).write_text(json.dumps(story))
    (root / demo_cache.NARRATION_FILENAME).write_bytes(b"audio")
    (root / demo_cache.REEL_FILENAME).write_bytes(b"reel")
    (root / demo_cache.MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "duration_ms": 8_000,
                "clip_sha256": hashlib.sha256(clip.read_bytes()).hexdigest(),
            }
        )
    )
    return clip


def test_clip_fingerprint_must_match_exactly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clip = build_cache(monkeypatch, tmp_path)
    assert demo_cache.available()
    assert demo_cache.matches_clip(clip)

    changed = tmp_path / "changed.mp4"
    changed.write_bytes(clip.read_bytes() + b"x")
    assert not demo_cache.matches_clip(changed)


def test_event_labels_can_change_but_evidence_cannot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    build_cache(monkeypatch, tmp_path)
    renamed = SceneEvent.model_validate({**EVENT, "object_label": "my toy"})
    demo_cache.validate_events([renamed])

    changed_box = renamed.model_copy(deep=True)
    changed_box.bounding_box.x_min = 0.2
    with pytest.raises(demo_cache.DemoCacheError):
        demo_cache.validate_events([changed_box])

    unknown = renamed.model_copy(update={"event_id": "unknown"})
    with pytest.raises(demo_cache.DemoCacheError):
        demo_cache.validate_events([unknown])


def test_cached_reel_requires_the_full_story_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    build_cache(monkeypatch, tmp_path)
    request = StoryReelRequest.model_validate(story_request())
    assert demo_cache.matches_story_request(request)

    changed = request.model_copy(deep=True)
    changed.profile.dog_name = "Another dog"
    assert not demo_cache.matches_story_request(changed)
