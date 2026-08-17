from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    """Base model that rejects unexpected AI-generated fields."""

    model_config = ConfigDict(extra="forbid")


class ObjectCategory(str, Enum):
    PERSON = "person"
    ANIMAL = "animal"
    TOY = "toy"
    FOOD = "food"
    VEHICLE = "vehicle"
    ENVIRONMENT = "environment"
    OTHER = "other"


class MotionLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class NormalizedBoundingBox(StrictModel):
    """Bounding box coordinates expressed from 0.0 to 1.0."""

    x_min: float = Field(ge=0.0, le=1.0)
    y_min: float = Field(ge=0.0, le=1.0)
    x_max: float = Field(ge=0.0, le=1.0)
    y_max: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_axis_order(self) -> "NormalizedBoundingBox":
        if self.x_min >= self.x_max:
            raise ValueError("x_min must be smaller than x_max")

        if self.y_min >= self.y_max:
            raise ValueError("y_min must be smaller than y_max")

        return self


class SceneEvent(StrictModel):
    event_id: str = Field(
        min_length=1,
        max_length=50,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    timestamp_ms: int = Field(ge=0)
    object_label: str = Field(min_length=1, max_length=80)
    category: ObjectCategory
    bounding_box: NormalizedBoundingBox
    confidence: float = Field(ge=0.0, le=1.0)
    visible_evidence: str = Field(min_length=1, max_length=240)
    motion_level: MotionLevel


class SceneAnalysisResponse(StrictModel):
    analysis_version: Literal["1.0"]
    duration_ms: int = Field(gt=0, le=15_000)
    events: list[SceneEvent] = Field(default_factory=list, max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_scene_timeline(self) -> "SceneAnalysisResponse":
        event_ids = [event.event_id for event in self.events]

        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event_id values must be unique")

        invalid_timestamps = [
            event.event_id
            for event in self.events
            if event.timestamp_ms > self.duration_ms
        ]

        if invalid_timestamps:
            invalid = ", ".join(invalid_timestamps)
            raise ValueError(
                f"Event timestamps exceed video duration: {invalid}"
            )

        return self

class SalienceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VisibilityScoreRequest(StrictModel):
    # Demo boxes belong to the cached example and must not be scored against
    # an unrelated uploaded video.
    analysis_source: Literal["gemini", "controlled_demo"]
    events: list[SceneEvent] = Field(min_length=1, max_length=12)
    favorite_interest: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def validate_event_ids(self) -> "VisibilityScoreRequest":
        event_ids = [event.event_id for event in self.events]

        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event_id values must be unique")

        return self


class VisibilityScore(StrictModel):
    event_id: str
    identification_confidence: float = Field(ge=0.0, le=1.0)

    human_contrast_score: int = Field(ge=0, le=100)
    dog_contrast_score: int = Field(ge=0, le=100)
    contrast_change: int = Field(ge=-100, le=100)

    motion_score: int = Field(ge=0, le=100)
    apparent_size_score: int = Field(ge=0, le=100)
    profile_relevance_score: int = Field(ge=0, le=100)

    salience_score: int = Field(ge=0, le=100)
    salience_level: SalienceLevel

    human_object_color: str = Field(pattern=r"^#[0-9A-F]{6}$")
    human_background_color: str = Field(pattern=r"^#[0-9A-F]{6}$")
    dog_object_color: str = Field(pattern=r"^#[0-9A-F]{6}$")
    dog_background_color: str = Field(pattern=r"^#[0-9A-F]{6}$")

    explanation: str = Field(min_length=1, max_length=400)
    why: list[str] = Field(default_factory=list, max_length=4)


class VisibilityAnalysisResponse(StrictModel):
    scoring_version: Literal["1.0"]
    method: Literal["bbox-region-lab-v1"]
    scores: list[VisibilityScore] = Field(max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=12)


ToyColorId = Literal[
    "blue",
    "yellow",
    "red",
    "green",
    "orange",
    "purple",
]


class ColorSimulationRequest(StrictModel):
    # Cached demo boxes must never be applied to an unrelated clip.
    analysis_source: Literal["gemini", "controlled_demo"]
    event: SceneEvent


class ColorSimulationOption(StrictModel):
    color_id: ToyColorId
    label: str = Field(min_length=1, max_length=30)
    human_color: str = Field(pattern=r"^#[0-9A-F]{6}$")
    dog_approx_color: str = Field(pattern=r"^#[0-9A-F]{6}$")
    human_contrast_score: int = Field(ge=0, le=100)
    dog_contrast_score: int = Field(ge=0, le=100)
    dog_contrast_gain: int = Field(ge=-100, le=100)
    contrast_change: int = Field(ge=-100, le=100)
    rank: int = Field(ge=1, le=6)
    explanation: str = Field(min_length=1, max_length=300)


class ColorSimulationResponse(StrictModel):
    simulation_version: Literal["1.0"]
    method: Literal["fixed-swatch-background-lab-v1"]
    event_id: str
    original_human_color: str = Field(pattern=r"^#[0-9A-F]{6}$")
    original_dog_color: str = Field(pattern=r"^#[0-9A-F]{6}$")
    human_background_color: str = Field(pattern=r"^#[0-9A-F]{6}$")
    dog_background_color: str = Field(pattern=r"^#[0-9A-F]{6}$")
    original_human_contrast_score: int = Field(ge=0, le=100)
    original_dog_contrast_score: int = Field(ge=0, le=100)
    recommended_color_id: ToyColorId
    options: list[ColorSimulationOption] = Field(min_length=6, max_length=6)
    disclaimer: Literal[
        "Screen-color simulation using a fixed palette and the measured "
        "nearby background. It is not exact canine vision, object "
        "segmentation, or a physical-product guarantee."
    ]

class StoryProfile(StrictModel):
    owner_name: str = Field(default="", max_length=60)
    dog_name: str = Field(min_length=1, max_length=40)
    breed: str = Field(default="", max_length=80)
    age: Literal["Puppy", "Adult", "Senior"]
    size: Literal["Small", "Medium", "Large"]
    personality_tags: list[str] = Field(
        default_factory=list,
        max_length=2,
    )
    favorite_interest: str = Field(default="", max_length=40)

    @field_validator(
        "owner_name",
        "dog_name",
        "breed",
        "favorite_interest",
        mode="before",
    )
    @classmethod
    def sanitize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return " ".join(value.replace("\x00", "").split())

    @field_validator("personality_tags", mode="before")
    @classmethod
    def sanitize_tags(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [
            " ".join(tag.replace("\x00", "").split())[:40]
            if isinstance(tag, str)
            else tag
            for tag in value
        ]


class StoryLine(StrictModel):
    event_ids: list[str] = Field(min_length=1, max_length=3)
    object_labels: list[str] = Field(min_length=1, max_length=3)
    motion_levels: list[MotionLevel] = Field(min_length=1, max_length=3)
    text: str = Field(min_length=1, max_length=220)


class StoryScriptResponse(StrictModel):
    story_version: Literal["1.0"]
    style: Literal["nature_documentary"]
    title: str = Field(min_length=1, max_length=80)
    lines: list[StoryLine] = Field(min_length=3, max_length=4)
    featured_event_id: str
    voice_notice: Literal[
        "Fictional dog voice based only on visible scene events."
    ]

    @property
    def narration_text(self) -> str:
        return " ".join(line.text.strip() for line in self.lines)

    @model_validator(mode="after")
    def validate_story_length(self) -> "StoryScriptResponse":
        word_count = len(self.narration_text.split())

        if word_count < 40 or word_count > 60:
            raise ValueError(
                "Story narration must contain 40 to 60 words"
            )

        return self


class StoryReelRequest(StrictModel):
    analysis_source: Literal["gemini", "controlled_demo"]
    style: Literal["nature_documentary"] = "nature_documentary"
    variation_id: str = Field(
        default="original",
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    animation_seed: int = Field(default=0, ge=0, le=2_147_483_647)
    profile: StoryProfile
    events: list[SceneEvent] = Field(min_length=1, max_length=12)
    scores: list[VisibilityScore] = Field(min_length=1, max_length=12)
    featured_event_id: str

    @model_validator(mode="after")
    def validate_story_inputs(self) -> "StoryReelRequest":
        event_ids = [event.event_id for event in self.events]
        score_ids = [score.event_id for score in self.scores]

        if len(event_ids) != len(set(event_ids)):
            raise ValueError("Story event IDs must be unique")

        if len(score_ids) != len(set(score_ids)):
            raise ValueError("Story score IDs must be unique")

        unknown_scores = set(score_ids) - set(event_ids)

        if unknown_scores:
            raise ValueError(
                "Every visibility score must reference a corrected event"
            )

        if self.featured_event_id not in event_ids:
            raise ValueError(
                "The featured event must exist in the corrected timeline"
            )

        if self.featured_event_id not in score_ids:
            raise ValueError(
                "The featured event must have a visibility score"
            )

        return self

class StoryJobCreateResponse(StrictModel):
    job_id: str = Field(
        pattern=r"^[a-f0-9]{32}$",
    )
    status: Literal["queued"]
    status_url: str
    variation_id: str
    animation_seed: int
    music_track_id: Literal[
        "sunny-paws",
        "curious-steps",
        "cozy-walk",
    ]


class StoryJobStatusResponse(StrictModel):
    job_id: str = Field(
        pattern=r"^[a-f0-9]{32}$",
    )
    status: Literal[
        "queued",
        "running",
        "completed",
        "failed",
        "cancelled",
        "expired",
    ]
    progress: int = Field(ge=0, le=100)
    error: str | None = Field(
        default=None,
        max_length=240,
    )
    story_source: Literal[
        "gemini",
        "template",
        "demo_cache",
    ] | None = None
    artifact_source: Literal[
        "live_render",
        "controlled_demo_cache",
    ] | None = None
    voice_source: Literal[
        "elevenlabs",
        "controlled_demo_cache",
    ] | None = None
    variation_id: str | None = None
    animation_seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    music_track_id: Literal[
        "sunny-paws",
        "curious-steps",
        "cozy-walk",
    ] | None = None
    download_url: str | None = None
