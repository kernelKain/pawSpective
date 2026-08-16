import json
import shutil
import subprocess

import pytest

from backend.app.story import fallback_story
from backend.app.story_render import (
    StoryRenderError,
    render_story_reel,
)
from backend.tests.test_story import story_request


requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None
    or shutil.which("ffprobe") is None,
    reason="FFmpeg is not installed in this environment.",
)


def run_checked(command: list[str]) -> None:
    subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=45,
        check=True,
    )


@requires_ffmpeg
def test_real_story_reel_is_vertical_h264_aac(
    tmp_path,
) -> None:
    video_path = tmp_path / "source.mp4"
    narration_path = tmp_path / "narration.mp3"
    output_path = tmp_path / "story-reel.mp4"

    run_checked(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x2D7D46:s=160x120:r=15",
            "-vf",
            "drawbox=x=32:y=30:w=48:h=36:color=0x2879D0:t=fill",
            "-t",
            "5.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
    )
    run_checked(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "3",
            "-c:a",
            "libmp3lame",
            str(narration_path),
        ],
    )

    request = story_request()
    story = fallback_story(request)

    render_story_reel(
        video_path,
        narration_path,
        request,
        story,
        output_path,
        5_200,
    )

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            (
                "stream=index,codec_name,codec_type,"
                "width,height,pix_fmt,display_aspect_ratio"
            ),
            "-of",
            "json",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    metadata = json.loads(probe.stdout)
    streams = {
        stream["codec_type"]: stream
        for stream in metadata["streams"]
    }
    duration = float(metadata["format"]["duration"])

    assert streams["video"]["codec_name"] == "h264"
    assert streams["video"]["width"] == 720
    assert streams["video"]["height"] == 1280
    assert streams["video"]["pix_fmt"] == "yuv420p"
    assert streams["video"]["display_aspect_ratio"] == "9:16"
    assert streams["audio"]["codec_name"] == "aac"
    assert 15 <= duration <= 25


def test_rejects_narration_over_reel_limit(
    monkeypatch,
    tmp_path,
) -> None:
    import backend.app.story_render as render_module

    monkeypatch.setattr(
        render_module.shutil,
        "which",
        lambda executable: executable,
    )
    monkeypatch.setattr(
        render_module,
        "probe_duration_ms",
        lambda _: 23_001,
    )

    request = story_request()

    with pytest.raises(
        StoryRenderError,
        match="too long",
    ):
        render_story_reel(
            tmp_path / "video.mp4",
            tmp_path / "narration.mp3",
            request,
            fallback_story(request),
            tmp_path / "output.mp4",
            5_200,
        )


def test_reports_missing_ffmpeg(
    monkeypatch,
    tmp_path,
) -> None:
    import backend.app.story_render as render_module

    monkeypatch.setattr(
        render_module.shutil,
        "which",
        lambda _: None,
    )

    request = story_request()

    with pytest.raises(
        StoryRenderError,
        match="FFmpeg or FFprobe",
    ):
        render_story_reel(
            tmp_path / "video.mp4",
            tmp_path / "narration.mp3",
            request,
            fallback_story(request),
            tmp_path / "output.mp4",
            5_200,
        )
