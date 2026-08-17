import json
import logging
import re
from pathlib import Path
from typing import Callable, Literal

from google import genai

from backend.app.cancellable import run_cancellable_process
from backend.app.contracts import (
    StoryLine,
    StoryReelRequest,
    StoryScriptResponse,
)
from backend.app.settings import settings


PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "story_reel.txt"

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

FIRST_PERSON_PATTERN = re.compile(r"\b(?:i|i'm|i’ll|i've|me|my|mine)\b", re.IGNORECASE)


class StoryGenerationError(RuntimeError):
    pass


def validate_story_grounding(
    story: StoryScriptResponse,
    request: StoryReelRequest,
) -> None:
    """Reject stories that drift from corrected, visible clip evidence."""
    events_by_id = {event.event_id: event for event in request.events}

    if story.featured_event_id != request.featured_event_id:
        raise StoryGenerationError("The story changed the selected featured event.")

    narration = story.narration_text.lower()

    if not FIRST_PERSON_PATTERN.search(story.narration_text):
        raise StoryGenerationError("The story must use first-person dog narration.")

    if any(phrase in narration for phrase in PROHIBITED_PHRASES):
        raise StoryGenerationError("The generated story used prohibited language.")

    for line in story.lines:
        expected_labels: list[str] = []
        expected_motions = []

        for event_id in line.event_ids:
            event = events_by_id.get(event_id)
            if event is None:
                raise StoryGenerationError(
                    "The generated story referenced an unknown event."
                )
            expected_labels.append(event.object_label)
            expected_motions.append(event.motion_level)

        if line.object_labels != expected_labels:
            raise StoryGenerationError(
                "A story line declared unsupported object labels."
            )

        if line.motion_levels != expected_motions:
            raise StoryGenerationError(
                "A story line declared unsupported motion evidence."
            )

        for object_label in line.object_labels:
            if object_label.casefold() not in line.text.casefold():
                raise StoryGenerationError(
                    "A story line did not name its supporting object."
                )


def _motion_words(level: str) -> str:
    return {
        "none": "staying still",
        "low": "moving a little",
        "medium": "moving through the moment",
        "high": "moving quickly",
    }[level]


def _profile_description(request: StoryReelRequest) -> str:
    profile = request.profile
    age = profile.age.lower()
    article = "an" if age[0] in "aeiou" else "a"
    description = f"{article} {age}, {profile.size.lower()}"
    if profile.breed:
        description += f" {profile.breed}"
    else:
        description += " dog"

    if profile.personality_tags:
        description += " with a " + " and ".join(
            tag.lower() for tag in profile.personality_tags
        ) + " streak"

    return description


def _favorite_is_grounded(request: StoryReelRequest) -> bool:
    favorite = request.profile.favorite_interest.strip().casefold()
    if not favorite:
        return False

    singular = favorite.removesuffix("s")
    return any(
        favorite in event.object_label.casefold()
        or singular in event.object_label.casefold()
        for event in request.events
    )


def fallback_story(request: StoryReelRequest) -> StoryScriptResponse:
    """Create a short, upbeat internal monologue without a model call."""
    first = request.events[0]
    second = request.events[1] if len(request.events) > 1 else first
    dog_name = request.profile.dog_name
    variation = request.animation_seed % 3
    first_motion = _motion_words(first.motion_level.value)
    second_motion = _motion_words(second.motion_level.value)
    openings = (
        f"I'm {dog_name}; {first.object_label} is {first_motion}. Adventure underway.",
        f"I'm {dog_name}; {first.object_label} is {first_motion} with excellent timing.",
        f"My report: {first.object_label} is {first_motion}. Important business.",
    )
    middles = (
        f"{second.object_label} is {second_motion}, adding tasteful drama.",
        f"{second.object_label} is {second_motion}; the production improves.",
        f"{second.object_label} is {second_motion}. Naturally, I approve.",
    )
    endings = (
        f"I award {first.object_label} a cheerful finale.",
        f"I approve {first.object_label} and this very good afternoon.",
        f"I declare {first.object_label} a delightful success.",
    )

    lines = [
        StoryLine(
            event_ids=[first.event_id],
            object_labels=[first.object_label],
            motion_levels=[first.motion_level],
            text=openings[variation],
        ),
        StoryLine(
            event_ids=[second.event_id],
            object_labels=[second.object_label],
            motion_levels=[second.motion_level],
            text=middles[variation],
        ),
        StoryLine(
            event_ids=[first.event_id],
            object_labels=[first.object_label],
            motion_levels=[first.motion_level],
            text=endings[variation],
        ),
    ]

    story = StoryScriptResponse(
        story_version="1.0",
        style="nature_documentary",
        title=f"{dog_name}'s little adventure",
        featured_event_id=request.featured_event_id,
        voice_notice="Fictional dog voice based only on visible scene events.",
        lines=lines,
    )
    validate_story_grounding(story, request)
    return story


def _request_gemini_story(
    api_key: str,
    model: str,
    prompt: str,
    schema: dict[str, object],
) -> str:
    client = genai.Client(api_key=api_key)
    try:
        interaction = client.interactions.create(
            model=model,
            store=False,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
        )
        if not interaction.output_text:
            raise RuntimeError("The story service returned an empty result.")
        return interaction.output_text
    finally:
        client.close()


def _apply_server_grounding(
    generated: StoryScriptResponse,
    request: StoryReelRequest,
) -> StoryScriptResponse:
    """Keep model art direction while deriving every spoken claim on-server."""
    grounded = fallback_story(request)
    return grounded.model_copy(
        update={
            "animation_prompt": generated.animation_prompt,
        }
    )


def generate_story(
    request: StoryReelRequest,
    check_cancelled: Callable[[], None] | None = None,
) -> tuple[StoryScriptResponse, StorySource]:
    if settings.demo_mode:
        return fallback_story(request), "template"

    try:
        if not settings.gemini_api_key:
            raise StoryGenerationError("Story generation is not configured.")

        story_input = {
            "style": request.style,
            "variation_id": request.variation_id,
            "animation_seed": request.animation_seed,
            "profile": request.profile.model_dump(mode="json", exclude={"owner_name"}),
            "featured_event_id": request.featured_event_id,
            "events": [event.model_dump(mode="json") for event in request.events],
        }
        prompt = PROMPT_PATH.read_text(encoding="utf-8").replace(
            "{{STORY_INPUT}}", json.dumps(story_input, indent=2)
        )
        arguments = (
            settings.gemini_api_key,
            settings.gemini_model,
            prompt,
            StoryScriptResponse.model_json_schema(),
        )
        if check_cancelled is None:
            output_text = _request_gemini_story(*arguments)
        else:
            output_text = run_cancellable_process(
                _request_gemini_story,
                arguments,
                check_cancelled,
                timeout_seconds=60,
            )

        story = StoryScriptResponse.model_validate_json(output_text)
        story = _apply_server_grounding(story, request)
        validate_story_grounding(story, request)
        return story, "gemini"

    except Exception as error:
        if check_cancelled is not None:
            check_cancelled()
        logger.exception("Story generation failed")
        if settings.allow_demo_fallback:
            return fallback_story(request), "template"
        if isinstance(error, StoryGenerationError):
            raise
        raise StoryGenerationError("Story generation failed.") from error
