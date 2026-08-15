import type {
  AnalyzeVideoResponse,
  CapturedClip,
} from "../types/sceneAnalysis";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

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
    let message = "Scene analysis failed.";

    try {
      const payload = (await response.json()) as {
        detail?: string;
      };

      if (payload.detail) {
        message = payload.detail;
      }
    } catch {
      // Retain the safe default error.
    }

    throw new Error(message);
  }

  return (await response.json()) as AnalyzeVideoResponse;
}