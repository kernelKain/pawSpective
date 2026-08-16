from dataclasses import replace

import pytest
from pydantic import ValidationError

from backend.app.contracts import (
    StoryReelRequest,
    StoryScriptResponse,
)
from backend.app.story import (
    StoryGenerationError,
    fallback_story,
    validate_story_grounding,
)


def story_request() -> StoryReelRequest:
    return StoryReelRequest.model_validate(
        {
            "analysis_source": "gemini",
            "style": "nature_documentary",
            "profile": {
                "owner_name": "Kshitij",
                "dog_name": "Bruno",
                "breed": "Golden Retriever",
                "age": "Adult",
                "size": "Large",
                "personality_tags": [
                    "Foodie",
                    "Detective",
                ],
                "favorite_interest": "Ball",
            },
            "events": [
                {
                    "event_id": "ball",
                    "timestamp_ms": 1_000,
                    "object_label": "blue ball",
                    "category": "toy",
                    "bounding_box": {
                        "x_min": 0.2,
                        "y_min": 0.3,
                        "x_max": 0.5,
                        "y_max": 0.7,
                    },
                    "confidence": 0.93,
                    "visible_evidence": (
                        "A blue ball is visible."
                    ),
                    "motion_level": "medium",
                },
                {
                    "event_id": "tree",
                    "timestamp_ms": 3_000,
                    "object_label": "tree",
                    "category": "environment",
                    "bounding_box": {
                        "x_min": 0.55,
                        "y_min": 0.1,
                        "x_max": 0.9,
                        "y_max": 0.9,
                    },
                    "confidence": 0.88,
                    "visible_evidence": "A tree is visible.",
                    "motion_level": "none",
                },
            ],
            "scores": [
                {
                    "event_id": "ball",
                    "identification_confidence": 0.93,
                    "human_contrast_score": 72,
                    "dog_contrast_score": 86,
                    "contrast_change": 14,
                    "motion_score": 67,
                    "apparent_size_score": 60,
                    "profile_relevance_score": 100,
                    "salience_score": 75,
                    "salience_level": "high",
                    "human_object_color": "#2478D0",
                    "human_background_color": "#3B7A3A",
                    "dog_object_color": "#357DC4",
                    "dog_background_color": "#77743B",
                    "explanation": "The ball remains visible.",
                    "why": ["Contrast remains high."],
                },
                {
                    "event_id": "tree",
                    "identification_confidence": 0.88,
                    "human_contrast_score": 40,
                    "dog_contrast_score": 32,
                    "contrast_change": -8,
                    "motion_score": 0,
                    "apparent_size_score": 90,
                    "profile_relevance_score": 0,
                    "salience_score": 29,
                    "salience_level": "low",
                    "human_object_color": "#446B35",
                    "human_background_color": "#829071",
                    "dog_object_color": "#5A643B",
                    "dog_background_color": "#85856D",
                    "explanation": "The tree is less distinct.",
                    "why": ["The object is large."],
                },
            ],
            "featured_event_id": "ball",
        },
    )


def test_fallback_story_is_grounded_and_correct_length() -> None:
    request = story_request()
    story = fallback_story(request)

    validate_story_grounding(story, request)

    assert story.featured_event_id == "ball"
    assert 40 <= len(story.narration_text.split()) <= 60
    assert "blue ball" in story.narration_text
    assert "tree" in story.narration_text


def test_unknown_story_event_is_rejected() -> None:
    request = story_request()
    story = fallback_story(request)

    story.lines[0].event_ids = ["cat"]

    with pytest.raises(
        StoryGenerationError,
        match="unknown event",
    ):
        validate_story_grounding(story, request)


@pytest.mark.parametrize(
    "claim",
    [
        "Bruno thinks the blue ball is suspicious.",
        "Bruno knows the blue ball is suspicious.",
        "Bruno feels the blue ball is suspicious.",
        "Bruno smells the blue ball nearby.",
        "Bruno wants the blue ball.",
        "Bruno is looking at the blue ball.",
        "Bruno decides the blue ball is evidence.",
        "Bruno believes the blue ball is evidence.",
    ],
)
def test_prohibited_claim_is_rejected(claim: str) -> None:
    request = story_request()
    story = fallback_story(request)

    story.lines[0].text = claim

    with pytest.raises(
        StoryGenerationError,
        match="prohibited language",
    ):
        validate_story_grounding(story, request)


def test_unsupported_object_label_is_rejected() -> None:
    request = story_request()
    story = fallback_story(request)

    story.lines[0].object_labels = ["cat"]

    with pytest.raises(
        StoryGenerationError,
        match="unsupported object labels",
    ):
        validate_story_grounding(story, request)


def test_changed_featured_event_is_rejected() -> None:
    request = story_request()
    story = fallback_story(request)

    story.featured_event_id = "tree"

    with pytest.raises(
        StoryGenerationError,
        match="changed the selected featured event",
    ):
        validate_story_grounding(story, request)


@pytest.mark.parametrize("word_count", [39, 61])
def test_story_contract_rejects_invalid_word_count(
    word_count: int,
) -> None:
    payload = fallback_story(story_request()).model_dump(
        mode="json",
    )
    words = ["word"] * word_count
    first_end = word_count // 3
    second_end = first_end * 2

    payload["lines"][0]["text"] = " ".join(words[:first_end])
    payload["lines"][1]["text"] = " ".join(
        words[first_end:second_end],
    )
    payload["lines"][2]["text"] = " ".join(words[second_end:])

    with pytest.raises(
        ValidationError,
        match="40 to 60 words",
    ):
        StoryScriptResponse.model_validate(payload)


def test_story_contract_requires_fictional_voice_notice() -> None:
    payload = fallback_story(story_request()).model_dump(
        mode="json",
    )
    payload.pop("voice_notice")

    with pytest.raises(ValidationError):
        StoryScriptResponse.model_validate(payload)


def test_story_contract_rejects_unexpected_fields() -> None:
    payload = fallback_story(story_request()).model_dump(
        mode="json",
    )
    payload["dog_emotion"] = "excited"

    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        StoryScriptResponse.model_validate(payload)


def test_story_request_requires_a_score_for_featured_event() -> None:
    payload = story_request().model_dump(mode="json")
    payload["scores"] = [
        score
        for score in payload["scores"]
        if score["event_id"] != payload["featured_event_id"]
    ]

    with pytest.raises(
        ValidationError,
        match="featured event must have a visibility score",
    ):
        StoryReelRequest.model_validate(payload)


class FailingInteractions:
    def create(self, **kwargs):
        raise TimeoutError("Gemini timed out")


class FailingGeminiClient:
    interactions = FailingInteractions()

    def close(self) -> None:
        pass


def test_gemini_timeout_uses_safe_template_fallback(
    monkeypatch,
) -> None:
    import backend.app.story as story_module

    monkeypatch.setattr(
        story_module,
        "settings",
        replace(
            story_module.settings,
            demo_mode=False,
            allow_demo_fallback=True,
            gemini_api_key="configured-test-key",
        ),
    )
    monkeypatch.setattr(
        story_module.genai,
        "Client",
        lambda **kwargs: FailingGeminiClient(),
    )

    story, source = story_module.generate_story(
        story_request(),
    )

    assert source == "template"
    assert "blue ball" in story.narration_text


def test_gemini_timeout_returns_safe_error_without_fallback(
    monkeypatch,
) -> None:
    import backend.app.story as story_module

    monkeypatch.setattr(
        story_module,
        "settings",
        replace(
            story_module.settings,
            demo_mode=False,
            allow_demo_fallback=False,
            gemini_api_key="configured-test-key",
        ),
    )
    monkeypatch.setattr(
        story_module.genai,
        "Client",
        lambda **kwargs: FailingGeminiClient(),
    )

    with pytest.raises(
        StoryGenerationError,
        match="Story generation failed",
    ):
        story_module.generate_story(story_request())
