import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.analysis as analysis_module
from backend.app.analysis import (
    MAXIMUM_INLINE_VIDEO_BYTES,
    SceneAnalysisError,
    analyze_video,
    load_demo_analysis,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PATH = PROJECT_ROOT / "examples" / "scene-analysis.example.json"


def configure(
    monkeypatch: pytest.MonkeyPatch,
    *,
    api_key: str = "test-key",
    demo_mode: bool = False,
    allow_fallback: bool = True,
    analysis_fallback_model: str = "",
    gemini_model: str = "gemini-test-primary",
) -> None:
    monkeypatch.setattr(
        analysis_module,
        "settings",
        replace(
            analysis_module.settings,
            gemini_api_key=api_key,
            demo_mode=demo_mode,
            allow_demo_fallback=allow_fallback,
            gemini_analysis_fallback_model=analysis_fallback_model,
            gemini_model=gemini_model,
        ),
    )


def write_video(tmp_path: Path) -> Path:
    path = tmp_path / "normalized.mp4"
    path.write_bytes(b"video")
    return path


def test_missing_api_key_uses_allowed_demo_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, api_key="", allow_fallback=True)

    result, source = analyze_video(write_video(tmp_path), 8_000)

    assert source == "demo"
    assert result.duration_ms == 8_000
    assert any("Gemini was unavailable" in item for item in result.warnings)


def test_missing_api_key_fails_when_fallback_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, api_key="", allow_fallback=False)

    with pytest.raises(SceneAnalysisError, match="scene analysis failed"):
        analyze_video(write_video(tmp_path), 8_000)


def test_client_creation_failure_uses_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch)

    def fail_client(**kwargs):
        raise RuntimeError("client initialization failed")

    monkeypatch.setattr(analysis_module.genai, "Client", fail_client)

    result, source = analyze_video(write_video(tmp_path), 8_000)

    assert source == "demo"
    assert result.events


def test_valid_gemini_response_is_validated_and_client_is_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch)
    payload = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    payload["duration_ms"] = 1
    calls: list[dict] = []

    class FakeClient:
        def __init__(self) -> None:
            self.interactions = SimpleNamespace(create=self.create)
            self.closed = False

        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text=json.dumps(payload))

        def close(self) -> None:
            self.closed = True

    client = FakeClient()
    monkeypatch.setattr(
        analysis_module.genai,
        "Client",
        lambda **kwargs: client,
    )

    result, source = analyze_video(write_video(tmp_path), 8_000)

    assert source == "gemini"
    assert result.duration_ms == 8_000
    assert calls[0]["model"] == analysis_module.settings.gemini_model
    assert calls[0]["store"] is False
    assert calls[0]["response_format"]["mime_type"] == "application/json"
    assert client.closed


def test_quota_failure_uses_configured_analysis_model_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(
        monkeypatch,
        analysis_fallback_model="gemini-3.1-flash-lite",
    )
    payload = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    calls: list[str] = []

    class FakeClient:
        def __init__(self) -> None:
            self.interactions = SimpleNamespace(create=self.create)

        def create(self, **kwargs):
            calls.append(kwargs["model"])
            if len(calls) == 1:
                raise RuntimeError("Error code: 429 - quota exceeded")
            return SimpleNamespace(output_text=json.dumps(payload))

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        analysis_module.genai,
        "Client",
        lambda **kwargs: FakeClient(),
    )

    result, source = analyze_video(write_video(tmp_path), 8_000)

    assert source == "gemini"
    assert calls == [
        analysis_module.settings.gemini_model,
        "gemini-3.1-flash-lite",
    ]
    assert any("fallback model" in warning for warning in result.warnings)


def test_invalid_gemini_response_uses_fallback_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch)

    class FakeClient:
        def __init__(self) -> None:
            self.interactions = SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    output_text='{"unexpected": true}',
                ),
            )
            self.closed = False

        def close(self) -> None:
            self.closed = True

    client = FakeClient()
    monkeypatch.setattr(
        analysis_module.genai,
        "Client",
        lambda **kwargs: client,
    )

    result, source = analyze_video(write_video(tmp_path), 8_000)

    assert source == "demo"
    assert result.events
    assert client.closed


def test_malformed_gemini_uses_verified_controlled_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch)

    class FakeClient:
        def __init__(self) -> None:
            self.interactions = SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    output_text='{"unexpected": true}',
                ),
            )

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        analysis_module.genai,
        "Client",
        lambda **kwargs: FakeClient(),
    )
    controlled = load_demo_analysis(8_000)
    result, source = analyze_video(
        write_video(tmp_path),
        8_000,
        controlled,
    )

    assert source == "controlled_demo"
    assert result.events
    assert any("verified controlled-demo" in item for item in result.warnings)


def test_oversized_inline_video_never_calls_gemini(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch)
    video_path = tmp_path / "large.mp4"

    with video_path.open("wb") as video:
        video.seek(MAXIMUM_INLINE_VIDEO_BYTES)
        video.write(b"x")

    client_was_created = False

    def unexpected_client(**kwargs):
        nonlocal client_was_created
        client_was_created = True
        raise AssertionError("Gemini client should not be created")

    monkeypatch.setattr(analysis_module.genai, "Client", unexpected_client)

    result, source = analyze_video(video_path, 8_000)

    assert source == "demo"
    assert result.events
    assert not client_was_created
