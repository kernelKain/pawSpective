import json
import logging
from pathlib import Path
from typing import Literal

from google import genai

from backend.app.contracts import (
    StoryLine,
    StoryReelRequest,
    StoryScriptResponse,
)
from backend.app.settings import settings


PROMPT_PATH = (
    Path(__file__).resolve().parent
    / "prompts"
    / "story_reel.txt"
)

StorySource = Literal["gemini", "template", "demo_cache"]

logger = logging.getLogger(__name__)

PROHIBITED_PHRASES = (
    "looking at",
    "looks at",
    "watching",
    "gaze",
    "thinks",
    "thought",
    "knows",
    "knew",
    "feels",
    "felt",
    "smells",
    "smelled",
    "wants",
    "wanted",
    "intends",
    "decides",
    "believes",
    "exactly how",
)


class StoryGenerationError(RuntimeError):
    pass


def validate_story_grounding(
    story: StoryScriptResponse,
    request: StoryReelRequest,
) -> None:
    events_by_id = {
        event.event_id: event
        for event in request.events
    }

    if story.featured_event_id != request.featured_event_id:
        raise StoryGenerationError(
            "Gemini changed the selected featured event.",
        )

    narration = story.narration_text.lower()

    prohibited = [
        phrase
        for phrase in PROHIBITED_PHRASES
        if phrase in narration
    ]

    if prohibited:
        raise StoryGenerationError(
            "The generated story used prohibited language.",
        )

    for line in story.lines:
        expected_labels: list[str] = []

        for event_id in line.event_ids:
            event = events_by_id.get(event_id)

            if event is None:
                raise StoryGenerationError(
                    "The generated story referenced an unknown event.",
                )

            expected_labels.append(event.object_label)

        if line.object_labels != expected_labels:
            raise StoryGenerationError(
                "A story line declared unsupported object labels.",
            )

        for object_label in line.object_labels:
            if object_label.lower() not in line.text.lower():
                raise StoryGenerationError(
                    "A story line did not name its supporting object.",
                )


def fallback_story(
    request: StoryReelRequest,
) -> StoryScriptResponse:
    first = request.events[0]
    second = (
        request.events[1]
        if len(request.events) > 1
        else first
    )
    dog_name = request.profile.dog_name

    story = StoryScriptResponse(
        story_version="1.0",
        style="nature_documentary",
        title=f"{dog_name}'s field report",
        featured_event_id=request.featured_event_id,
        voice_notice=(
            "Fictional dog voice based only on visible scene events."
        ),
        lines=[
            StoryLine(
                event_ids=[first.event_id],
                object_labels=[first.object_label],
                text=(
                    f"Field report: {dog_name} entered a recorded "
                    f"scene where {first.object_label} appeared in "
                    "the visible evidence."
                ),
            ),
            StoryLine(
                event_ids=(
                    [second.event_id, first.event_id]
                    if second.event_id != first.event_id
                    else [first.event_id]
                ),
                object_labels=(
                    [second.object_label, first.object_label]
                    if second.event_id != first.event_id
                    else [first.object_label]
                ),
                text=(
                    f"Soon, {second.object_label} joined the frame, "
                    f"while {first.object_label} remained part of "
                    "this unusually serious nature documentary."
                ),
            ),
            StoryLine(
                event_ids=[first.event_id],
                object_labels=[first.object_label],
                text=(
                    f"With {first.object_label} still in the evidence "
                    "log, the final report remains playful fiction: "
                    "an ordinary moment transformed through "
                    "PawSpective's canine-vision approximation."
                ),
            ),
        ],
    )

    validate_story_grounding(story, request)
    return story


def generate_story(
    request: StoryReelRequest,
) -> tuple[StoryScriptResponse, StorySource]:
    if settings.demo_mode:
        return fallback_story(request), "template"

    client = None

    try:
        if not settings.gemini_api_key:
            raise StoryGenerationError(
                "GEMINI_API_KEY is not configured.",
            )

        story_input = {
            "style": request.style,
            "profile": request.profile.model_dump(mode="json"),
            "featured_event_id": request.featured_event_id,
            "events": [
                event.model_dump(mode="json")
                for event in request.events
            ],
        }

        prompt = PROMPT_PATH.read_text(
            encoding="utf-8",
        ).replace(
            "{{STORY_INPUT}}",
            json.dumps(story_input, indent=2),
        )

        client = genai.Client(
            api_key=settings.gemini_api_key,
        )

        interaction = client.interactions.create(
            model=settings.gemini_model,
            store=False,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": StoryScriptResponse.model_json_schema(),
            },
        )

        if not interaction.output_text:
            raise StoryGenerationError(
                "Gemini returned an empty story.",
            )

        story = StoryScriptResponse.model_validate_json(
            interaction.output_text,
        )

        validate_story_grounding(story, request)
        return story, "gemini"

    except Exception as error:
        logger.exception("Gemini story generation failed")

        if settings.allow_demo_fallback:
            return fallback_story(request), "template"

        if isinstance(error, StoryGenerationError):
            raise

        raise StoryGenerationError(
            "Story generation failed.",
        ) from error

    finally:
        if client is not None:
            client.close()
