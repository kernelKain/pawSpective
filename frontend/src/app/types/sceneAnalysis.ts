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