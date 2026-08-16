export type SceneEvent = {
  event_id: string;
  timestamp_ms: number;
  object_label: string;
  category:
    | "person"
    | "animal"
    | "toy"
    | "food"
    | "vehicle"
    | "environment"
    | "other";
  bounding_box: {
    x_min: number;
    y_min: number;
    x_max: number;
    y_max: number;
  };
  confidence: number;
  visible_evidence: string;
  motion_level: "none" | "low" | "medium" | "high";
};

export type SceneAnalysis = {
  analysis_version: "1.0";
  duration_ms: number;
  events: SceneEvent[];
  warnings: string[];
};

export type AnalyzeVideoResponse = {
  analysis: SceneAnalysis;
  source: "gemini" | "demo";
};

export type CapturedClip = {
  file: File;
  durationMs: number;
  source: "recording" | "upload";
};

export type SalienceLevel = "low" | "medium" | "high";

export type VisibilityScore = {
  event_id: string;
  identification_confidence: number;

  human_contrast_score: number;
  dog_contrast_score: number;
  contrast_change: number;

  motion_score: number;
  apparent_size_score: number;
  profile_relevance_score: number;

  salience_score: number;
  salience_level: SalienceLevel;

  human_object_color: string;
  human_background_color: string;
  dog_object_color: string;
  dog_background_color: string;

  explanation: string;
  why: string[];
};

export type VisibilityAnalysisResponse = {
  scoring_version: "1.0";
  method: "bbox-region-lab-v1";
  scores: VisibilityScore[];
  warnings: string[];
};

export type ToyColorId =
  | "blue"
  | "yellow"
  | "red"
  | "green"
  | "orange"
  | "purple";

export type ColorSimulationOption = {
  color_id: ToyColorId;
  label: string;
  human_color: string;
  dog_approx_color: string;
  human_contrast_score: number;
  dog_contrast_score: number;
  dog_contrast_gain: number;
  contrast_change: number;
  rank: number;
  explanation: string;
};

export type ColorSimulationResponse = {
  simulation_version: "1.0";
  method: "fixed-swatch-background-lab-v1";
  event_id: string;
  original_human_color: string;
  original_dog_color: string;
  human_background_color: string;
  dog_background_color: string;
  original_human_contrast_score: number;
  original_dog_contrast_score: number;
  recommended_color_id: ToyColorId;
  options: ColorSimulationOption[];
  disclaimer: "Screen-color simulation using a fixed palette and the measured nearby background. It is not exact canine vision, object segmentation, or a physical-product guarantee.";
};

export type StoryProfileInput = {
  owner_name: string;
  dog_name: string;
  breed: string;
  age: "Puppy" | "Adult" | "Senior";
  size: "Small" | "Medium" | "Large";
  personality_tags: string[];
  favorite_interest: string;
};

export type StoryReelSource = "gemini" | "template";

export type StoryReelResult = {
  video: Blob;
  source: StoryReelSource;
};

export type StoryJobCreateResponse = {
  job_id: string;
  status: "queued";
  status_url: string;
};

export type StoryJobStatusResponse = {
  job_id: string;
  status:
    | "queued"
    | "running"
    | "completed"
    | "failed"
    | "expired";
  progress: number;
  error: string | null;
  story_source: StoryReelSource | null;
  download_url: string | null;
};
