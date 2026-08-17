import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.analysis import analyze_video
from backend.app.contracts import StoryProfile, StoryReelRequest
from backend.app.demo_cache import (
    ANALYSIS_FILENAME,
    CLIP_FILENAME,
    MANIFEST_FILENAME,
    NARRATION_FILENAME,
    REEL_FILENAME,
    STORY_FILENAME,
    STORY_REQUEST_FILENAME,
    fingerprint,
)
from backend.app.media import normalize_video, probe_duration_ms
from backend.app.settings import settings
from backend.app.story import generate_story
from backend.app.story_render import music_track_id, render_story_reel
from backend.app.visibility import score_visibility_events
from backend.app.voice import synthesize_narration


DEFAULT_SOURCE = PROJECT_ROOT / "demo-source" / "controlled-demo-original.mp4"
DEFAULT_OUTPUT = PROJECT_ROOT / "demo_cache"
PROFILE_PATH = PROJECT_ROOT / "demo-profile.json"


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build(source: Path, output: Path, force: bool) -> None:
    if settings.demo_mode:
        raise RuntimeError(
            "Set PAWSPECTIVE_DEMO_MODE=false so the cache is grounded in real Gemini output."
        )

    if not source.is_file():
        raise FileNotFoundError(
            f"Record the controlled source clip first: {source}"
        )

    output.mkdir(parents=True, exist_ok=True)
    generated = [
        output / CLIP_FILENAME,
        output / ANALYSIS_FILENAME,
        output / STORY_REQUEST_FILENAME,
        output / NARRATION_FILENAME,
        output / REEL_FILENAME,
        output / STORY_FILENAME,
        output / MANIFEST_FILENAME,
    ]

    if not force and any(path.exists() for path in generated):
        raise RuntimeError("The demo cache already exists; pass --force to rebuild it.")

    # The manifest is the cache's completion marker. Remove an old one before
    # rebuilding so a failed rebuild can never appear ready.
    if force:
        (output / MANIFEST_FILENAME).unlink(missing_ok=True)

    clip_path = output / CLIP_FILENAME
    narration_path = output / NARRATION_FILENAME
    reel_path = output / REEL_FILENAME

    normalize_video(source, clip_path)
    duration_ms = probe_duration_ms(clip_path)

    if not 5_000 <= duration_ms <= settings.max_video_duration_seconds * 1000:
        raise RuntimeError("The controlled clip must be between 5 and 15 seconds.")

    analysis, analysis_source = analyze_video(clip_path, duration_ms)

    if analysis_source != "gemini":
        raise RuntimeError("The cache build requires successful real Gemini analysis.")

    labels = " ".join(event.object_label.lower() for event in analysis.events)

    if "red" not in labels or "blue" not in labels:
        raise RuntimeError(
            "Gemini must identify both the red and blue objects; adjust the clip or labels and rebuild."
        )

    if not any(
        event.motion_level.value in {"medium", "high"}
        for event in analysis.events
    ):
        raise RuntimeError("The controlled analysis needs one medium/high-motion event.")

    profile = StoryProfile.model_validate_json(
        PROFILE_PATH.read_text(encoding="utf-8")
    )
    visibility = score_visibility_events(
        clip_path,
        analysis.events,
        profile.favorite_interest,
        duration_ms,
    )

    if not visibility.scores:
        raise RuntimeError("The controlled clip produced no visibility scores.")

    featured = max(
        visibility.scores,
        key=lambda score: score.dog_contrast_score,
    )
    story_request = StoryReelRequest(
        analysis_source="controlled_demo",
        profile=profile,
        events=analysis.events,
        scores=visibility.scores,
        featured_event_id=featured.event_id,
    )
    story, story_source = generate_story(story_request)

    if story_source != "gemini":
        raise RuntimeError("The cache build requires a Gemini-generated story.")

    synthesize_narration(story.narration_text, narration_path)
    render_story_reel(
        clip_path,
        narration_path,
        story_request,
        story,
        reel_path,
        duration_ms,
    )

    write_json(output / ANALYSIS_FILENAME, analysis.model_dump(mode="json"))
    write_json(
        output / STORY_REQUEST_FILENAME,
        story_request.model_dump(mode="json"),
    )
    write_json(output / STORY_FILENAME, story.model_dump(mode="json"))
    write_json(
        output / MANIFEST_FILENAME,
        {
            "cache_version": "2.0",
            "provenance": "pawspective-controlled-demo-v2",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "clip_sha256": fingerprint(clip_path),
            "analysis_sha256": fingerprint(output / ANALYSIS_FILENAME),
            "story_request_sha256": fingerprint(output / STORY_REQUEST_FILENAME),
            "narration_sha256": fingerprint(narration_path),
            "reel_sha256": fingerprint(reel_path),
            "story_sha256": fingerprint(output / STORY_FILENAME),
            "variation_id": story_request.variation_id,
            "animation_seed": story_request.animation_seed,
            "music_track_id": music_track_id(story_request.animation_seed),
            "voice_source": "controlled_demo_cache",
            "analysis_source": analysis_source,
            "story_source": story_source,
            "profile": profile.model_dump(mode="json"),
        },
    )

    print(f"Controlled demo cache built in {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the PawSpective demo cache")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    build(arguments.source.resolve(), arguments.output.resolve(), arguments.force)


if __name__ == "__main__":
    main()
