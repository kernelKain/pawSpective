from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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