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
        "variation_id": "original",
        "animation_seed": 0,
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
    monkeypatch.setattr(
        demo_cache,
        "probe_duration_ms",
        lambda path: {
            demo_cache.CLIP_FILENAME: 8_000,
            demo_cache.NARRATION_FILENAME: 5_000,
            demo_cache.REEL_FILENAME: 15_000,
        }[path.name],
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
                "motion_levels": ["medium"],
                "text": "I meet the red toy against green grass, a clear landmark in this measured backyard scene.",
            },
            {
                "event_ids": ["red-toy"],
                "object_labels": ["red toy"],
                "motion_levels": ["medium"],
                "text": "My route keeps the red toy present while medium motion carries the visible moment through the frame.",
            },
            {
                "event_ids": ["red-toy"],
                "object_labels": ["red toy"],
                "motion_levels": ["medium"],
                "text": "I finish with the red toy still supporting this small evidence-based expedition across the familiar green stage.",
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
    reel = root / demo_cache.REEL_FILENAME
    reel.write_bytes(b"reel")
    (root / demo_cache.MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "cache_version": "2.0",
                "provenance": "pawspective-controlled-demo-v2",
                "duration_ms": 8_000,
                "clip_sha256": hashlib.sha256(clip.read_bytes()).hexdigest(),
                "analysis_sha256": hashlib.sha256(
                    (root / demo_cache.ANALYSIS_FILENAME).read_bytes()
                ).hexdigest(),
                "story_request_sha256": hashlib.sha256(
                    (root / demo_cache.STORY_REQUEST_FILENAME).read_bytes()
                ).hexdigest(),
                "narration_sha256": hashlib.sha256(
                    (root / demo_cache.NARRATION_FILENAME).read_bytes()
                ).hexdigest(),
                "reel_sha256": hashlib.sha256(reel.read_bytes()).hexdigest(),
                "story_sha256": hashlib.sha256(
                    (root / demo_cache.STORY_FILENAME).read_bytes()
                ).hexdigest(),
                "variation_id": "original",
                "animation_seed": 0,
                "music_track_id": "sunny-paws",
                "voice_source": "controlled_demo_cache",
                "analysis_source": "gemini",
                "story_source": "gemini",
                "profile": story_request()["profile"],
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


def test_cached_reel_hash_must_match_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    build_cache(monkeypatch, tmp_path)
    assert demo_cache.available()

    (tmp_path / demo_cache.REEL_FILENAME).write_bytes(b"tampered reel")

    assert not demo_cache.available()
    with pytest.raises(demo_cache.DemoCacheError, match="incomplete"):
        demo_cache.copy_reel_to(tmp_path / "copy.mp4")


def test_cached_request_is_integrity_bound_to_reel_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    build_cache(monkeypatch, tmp_path)
    assert demo_cache.available()

    request_path = tmp_path / demo_cache.STORY_REQUEST_FILENAME
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    payload["animation_seed"] = 2
    payload["variation_id"] = "tampered"
    request_path.write_text(json.dumps(payload), encoding="utf-8")

    assert not demo_cache.available()


@pytest.mark.parametrize("filename", tuple(demo_cache.HASH_FIELDS))
def test_every_cached_artifact_is_hash_bound(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    filename: str,
) -> None:
    build_cache(monkeypatch, tmp_path)
    assert demo_cache.available()

    artifact = tmp_path / filename
    artifact.write_bytes(artifact.read_bytes() + b" tampered")

    assert not demo_cache.available()


def rewrite_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def update_manifest_hash(root: Path, filename: str) -> None:
    manifest_path = root / demo_cache.MANIFEST_FILENAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload[demo_cache.HASH_FIELDS[filename]] = hashlib.sha256(
        (root / filename).read_bytes()
    ).hexdigest()
    rewrite_json(manifest_path, payload)


def tamper_cache_relationship(root: Path, relationship: str) -> None:
    manifest_path = root / demo_cache.MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_changes = {
        "cache_version": ("cache_version", "1.0"),
        "provenance": ("provenance", "unverified-cache"),
        "duration": ("duration_ms", 8_001),
        "variation": ("variation_id", "different-variation"),
        "animation_seed": ("animation_seed", 1),
        "music": ("music_track_id", "curious-steps"),
        "voice_source": ("voice_source", "elevenlabs"),
        "analysis_source": ("analysis_source", "controlled_demo"),
        "story_source": ("story_source", "template"),
        "profile": (
            "profile",
            {**manifest["profile"], "dog_name": "Another dog"},
        ),
    }
    if relationship in manifest_changes:
        field, value = manifest_changes[relationship]
        manifest[field] = value
        rewrite_json(manifest_path, manifest)
        return

    if relationship == "request_analysis_source":
        request_path = root / demo_cache.STORY_REQUEST_FILENAME
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request["analysis_source"] = "gemini"
        rewrite_json(request_path, request)
        update_manifest_hash(root, demo_cache.STORY_REQUEST_FILENAME)
        return

    if relationship == "events":
        analysis_path = root / demo_cache.ANALYSIS_FILENAME
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        analysis["events"][0]["visible_evidence"] = (
            "Different evidence remains schema-valid."
        )
        rewrite_json(analysis_path, analysis)
        update_manifest_hash(root, demo_cache.ANALYSIS_FILENAME)
        return

    if relationship == "story_grounding":
        story_path = root / demo_cache.STORY_FILENAME
        story = json.loads(story_path.read_text(encoding="utf-8"))
        story["featured_event_id"] = "unrelated-event"
        rewrite_json(story_path, story)
        update_manifest_hash(root, demo_cache.STORY_FILENAME)
        return

    raise AssertionError(f"Unknown relationship: {relationship}")


@pytest.mark.parametrize(
    "relationship",
    (
        "cache_version",
        "provenance",
        "request_analysis_source",
        "events",
        "duration",
        "variation",
        "animation_seed",
        "music",
        "voice_source",
        "analysis_source",
        "story_source",
        "profile",
        "story_grounding",
    ),
)
def test_every_cache_relationship_is_integrity_bound(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relationship: str,
) -> None:
    build_cache(monkeypatch, tmp_path)
    assert demo_cache.available()

    tamper_cache_relationship(tmp_path, relationship)

    assert not demo_cache.available()


@pytest.mark.parametrize(
    "filename",
    (
        demo_cache.CLIP_FILENAME,
        demo_cache.NARRATION_FILENAME,
        demo_cache.REEL_FILENAME,
    ),
)
def test_rehashed_unreadable_media_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    filename: str,
) -> None:
    build_cache(monkeypatch, tmp_path)
    assert demo_cache.available()

    artifact = tmp_path / filename
    artifact.write_bytes(b"hash-consistent but unreadable")
    update_manifest_hash(tmp_path, filename)
    working_probe = demo_cache.probe_duration_ms

    def reject_unreadable(path: Path) -> int:
        if path.name == filename:
            raise ValueError("unreadable media")
        return working_probe(path)

    monkeypatch.setattr(demo_cache, "probe_duration_ms", reject_unreadable)

    assert not demo_cache.available()


@pytest.mark.parametrize(
    ("filename", "duration_ms"),
    (
        (demo_cache.CLIP_FILENAME, 8_001),
        (demo_cache.NARRATION_FILENAME, 23_001),
        (demo_cache.REEL_FILENAME, 14_999),
        (demo_cache.REEL_FILENAME, 25_001),
    ),
)
def test_cached_media_duration_must_match_artifact_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    filename: str,
    duration_ms: int,
) -> None:
    build_cache(monkeypatch, tmp_path)
    working_probe = demo_cache.probe_duration_ms

    monkeypatch.setattr(
        demo_cache,
        "probe_duration_ms",
        lambda path: duration_ms if path.name == filename else working_probe(path),
    )

    assert not demo_cache.available()
