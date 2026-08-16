import type {
  AnalyzeVideoResponse,
  CapturedClip,
  ColorSimulationResponse,
  SceneEvent,
  StoryJobCreateResponse,
  StoryJobStatusResponse,
  StoryProfileInput,
  StoryReelResult,
  VisibilityAnalysisResponse,
  VisibilityScore,
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
    // Retain the safe fallback message.
  }

  return new Error(message);
}

function wait(
  milliseconds: number,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(
        new DOMException(
          "The request was aborted.",
          "AbortError",
        ),
      );
      return;
    }

    const handleAbort = () => {
      window.clearTimeout(timeout);

      reject(
        new DOMException(
          "The request was aborted.",
          "AbortError",
        ),
      );
    };

    const timeout = window.setTimeout(() => {
      signal?.removeEventListener(
        "abort",
        handleAbort,
      );

      resolve();
    }, milliseconds);

    signal?.addEventListener(
      "abort",
      handleAbort,
      { once: true },
    );
  });
}

export async function analyzeCapturedClip(
  clip: CapturedClip,
): Promise<AnalyzeVideoResponse> {
  const formData = new FormData();

  formData.append(
    "file",
    clip.file,
    clip.file.name,
  );

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

  return (
    await response.json()
  ) as AnalyzeVideoResponse;
}

export async function scoreCapturedClip(
  clip: CapturedClip,
  events: SceneEvent[],
  favoriteInterest: string,
  signal?: AbortSignal,
): Promise<VisibilityAnalysisResponse> {
  const formData = new FormData();

  formData.append(
    "file",
    clip.file,
    clip.file.name,
  );

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
      signal,
    },
  );

  if (!response.ok) {
    throw await readApiError(
      response,
      "Visibility scoring failed.",
    );
  }

  return (
    await response.json()
  ) as VisibilityAnalysisResponse;
}

export async function simulateCapturedObjectColors(
  clip: CapturedClip,
  event: SceneEvent,
  signal?: AbortSignal,
): Promise<ColorSimulationResponse> {
  const formData = new FormData();

  formData.append("file", clip.file, clip.file.name);
  formData.append(
    "payload",
    JSON.stringify({
      analysis_source: "gemini",
      event: {
        ...event,
        object_label: event.object_label.trim(),
      },
    }),
  );

  const response = await fetch(
    `${API_BASE_URL}/api/v1/simulate-object-colors`,
    {
      method: "POST",
      body: formData,
      signal,
    },
  );

  if (!response.ok) {
    throw await readApiError(
      response,
      "Toy Color Lab simulation failed.",
    );
  }

  return (await response.json()) as ColorSimulationResponse;
}

export async function renderCapturedStoryReel(
  clip: CapturedClip,
  events: SceneEvent[],
  scores: VisibilityScore[],
  featuredEventId: string,
  profile: StoryProfileInput,
  signal?: AbortSignal,
  onProgress?: (progress: number) => void,
): Promise<StoryReelResult> {
  const formData = new FormData();

  formData.append(
    "file",
    clip.file,
    clip.file.name,
  );

  formData.append(
    "payload",
    JSON.stringify({
      analysis_source: "gemini",
      style: "nature_documentary",
      profile,
      events,
      scores,
      featured_event_id: featuredEventId,
    }),
  );

  onProgress?.(0);

  const createResponse = await fetch(
    `${API_BASE_URL}/api/v1/story-jobs`,
    {
      method: "POST",
      body: formData,
      signal,
    },
  );

  if (!createResponse.ok) {
    throw await readApiError(
      createResponse,
      "Story Reel generation could not be started.",
    );
  }

  const created =
    (await createResponse.json()) as StoryJobCreateResponse;

  onProgress?.(1);

  const deadline = Date.now() + 120_000;

  while (Date.now() < deadline) {
    await wait(1_500, signal);

    const statusResponse = await fetch(
      `${API_BASE_URL}${created.status_url}`,
      {
        method: "GET",
        cache: "no-store",
        signal,
      },
    );

    if (!statusResponse.ok) {
      throw await readApiError(
        statusResponse,
        "Story Reel status could not be read.",
      );
    }

    const status =
      (await statusResponse.json()) as StoryJobStatusResponse;

    const normalizedProgress = Math.min(
      100,
      Math.max(0, status.progress),
    );

    onProgress?.(normalizedProgress);

    if (status.status === "failed") {
      throw new Error(
        status.error ??
          "Story Reel generation failed.",
      );
    }

    if (status.status === "expired") {
      throw new Error(
        "The Story Reel expired before download.",
      );
    }

    if (status.status === "completed") {
      if (!status.download_url) {
        throw new Error(
          "The completed Story Reel has no download URL.",
        );
      }

      const downloadResponse = await fetch(
        `${API_BASE_URL}${status.download_url}`,
        {
          method: "GET",
          cache: "no-store",
          signal,
        },
      );

      if (!downloadResponse.ok) {
        throw await readApiError(
          downloadResponse,
          "Story Reel download failed.",
        );
      }

      const video = await downloadResponse.blob();

      onProgress?.(100);

      return {
        video,
        source:
          status.story_source === "gemini"
            ? "gemini"
            : "template",
      };
    }
  }

  throw new Error(
    "Story Reel generation exceeded the two-minute limit.",
  );
}
