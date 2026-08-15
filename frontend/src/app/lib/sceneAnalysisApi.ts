import type {
  AnalyzeVideoResponse,
  CapturedClip,
  SceneEvent,
  VisibilityAnalysisResponse,
} from "../types/sceneAnalysis";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

async function readApiError(
  response: Response,
  fallbackMessage: string,
): Promise<Error> {
  let message = fallbackMessage;

  try {
    const payload = (await response.json()) as {
      detail?: string;
    };

    if (payload.detail) {
      message = payload.detail;
    }
  } catch {
    // Retain the safe fallback.
  }

  return new Error(message);
}

export async function analyzeCapturedClip(
  clip: CapturedClip,
): Promise<AnalyzeVideoResponse> {
  const formData = new FormData();
  formData.append("file", clip.file, clip.file.name);

  const response = await fetch(
    `${API_BASE_URL}/api/v1/analyze-video`,
    {
      method: "POST",
      body: formData,
    },
  );

  if (!response.ok) {
    throw await readApiError(
      response,
      "Scene analysis failed.",
    );
  }

  return (await response.json()) as AnalyzeVideoResponse;
}

export async function scoreCapturedClip(
  clip: CapturedClip,
  events: SceneEvent[],
  favoriteInterest: string,
): Promise<VisibilityAnalysisResponse> {
  const formData = new FormData();

  formData.append("file", clip.file, clip.file.name);
  formData.append(
    "payload",
    JSON.stringify({
      analysis_source: "gemini",
      events,
      favorite_interest: favoriteInterest,
    }),
  );

  const response = await fetch(
    `${API_BASE_URL}/api/v1/score-visibility`,
    {
      method: "POST",
      body: formData,
    },
  );

  if (!response.ok) {
    throw await readApiError(
      response,
      "Visibility scoring failed.",
    );
  }

  return (await response.json()) as VisibilityAnalysisResponse;
}