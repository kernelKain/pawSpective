import type {
  AnalysisSource,
  AnalyzeVideoResponse,
  CapturedClip,
  ColorSimulationResponse,
  ControlledDemoBundle,
  ControlledDemoStatus,
  SceneEvent,
  StoryJobCreateResponse,
  StoryJobStatusResponse,
  StoryProfileInput,
  AnimationProvider,
  StoryReelResult,
  StoryVariation,
  VisibilityAnalysisResponse,
  VisibilityScore,
} from "../types/sceneAnalysis";

const API_BASE_URL =
  (
    process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
    "http://localhost:8000"
  ).replace(/\/+$/, "");

const unsafeErrorPattern =
  /(?:[a-z]:\\|\/(?:users|home|tmp)\/|api[_-]?key|secret|traceback|stack trace)/i;

const backendConnectionErrorMessage =
  "PawSpective could not reach the analysis service. Check the deployed API URL and allowed frontend origin, then try again.";

async function fetchApi(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (error) {
    if (
      error instanceof DOMException &&
      error.name === "AbortError"
    ) {
      throw error;
    }

    throw new Error(
      backendConnectionErrorMessage,
      { cause: error },
    );
  }
}

async function readApiError(
  response: Response,
  fallbackMessage: string,
): Promise<Error> {
  let message = fallbackMessage;

  try {
    const payload = (await response.json()) as {
      detail?: string;
    };

    if (
      typeof payload.detail === "string" &&
      payload.detail.length <= 240 &&
      !unsafeErrorPattern.test(payload.detail)
    ) {
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

  const response = await fetchApi(
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

export async function loadControlledDemo(): Promise<ControlledDemoBundle> {
  const statusResponse = await fetchApi(
    `${API_BASE_URL}/api/v1/demo/status`,
    { method: "GET", cache: "no-store" },
  );

  if (!statusResponse.ok) {
    throw await readApiError(
      statusResponse,
      "The rehearsal demo status is unavailable.",
    );
  }

  const status = (await statusResponse.json()) as ControlledDemoStatus;

  if (
    !status.available ||
    !status.clip_url ||
    !status.duration_ms ||
    !status.profile
  ) {
    throw new Error(
      "The controlled rehearsal demo has not been built on this server.",
    );
  }

  const clipResponse = await fetchApi(`${API_BASE_URL}${status.clip_url}`);

  if (!clipResponse.ok) {
    throw await readApiError(
      clipResponse,
      "The rehearsal demo clip is unavailable.",
    );
  }

  const video = await clipResponse.blob();

  return {
    clip: {
      file: new File([video], "controlled-demo.mp4", {
        type: "video/mp4",
      }),
      durationMs: status.duration_ms,
      source: "controlled_demo",
    },
    profile: status.profile,
  };
}

export async function scoreCapturedClip(
  clip: CapturedClip,
  events: SceneEvent[],
  favoriteInterest: string,
  signal?: AbortSignal,
  analysisSource: AnalysisSource = "gemini",
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
      analysis_source:
        analysisSource === "controlled_demo"
          ? "controlled_demo"
          : "gemini",
      events,
      favorite_interest: favoriteInterest,
    }),
  );

  const response = await fetchApi(
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
  analysisSource: AnalysisSource = "gemini",
): Promise<ColorSimulationResponse> {
  const formData = new FormData();

  formData.append("file", clip.file, clip.file.name);
  formData.append(
    "payload",
    JSON.stringify({
      analysis_source:
        analysisSource === "controlled_demo"
          ? "controlled_demo"
          : "gemini",
      event: {
        ...event,
        object_label: event.object_label.trim(),
      },
    }),
  );

  const response = await fetchApi(
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
  analysisSource: AnalysisSource = "gemini",
  variation: StoryVariation = {
    variationId: "original",
    animationSeed: 0,
  },
  animationProvider: AnimationProvider = "gemini_omni",
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
      analysis_source:
        analysisSource === "controlled_demo"
          ? "controlled_demo"
          : "gemini",
      style: "nature_documentary",
      variation_id: variation.variationId,
      animation_seed: variation.animationSeed,
      animation_provider: animationProvider,
      reel_mode: "animated_dog_pov",
      profile,
      events,
      scores,
      featured_event_id: featuredEventId,
    }),
  );

  onProgress?.(0);

  const createResponse = await fetchApi(
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

  // Remove the legacy write-only reference. Story jobs now follow an explicit
  // cancellation-on-leave policy rather than claiming browser resumption.
  window.localStorage.removeItem("pawspective-story-job-id");
  let cancellationSent = false;
  const cancelJob = () => {
    if (cancellationSent) return;
    cancellationSent = true;
    void fetchApi(`${API_BASE_URL}${created.status_url}`, {
      method: "DELETE",
      cache: "no-store",
      keepalive: true,
    }).catch(() => undefined);
  };
  signal?.addEventListener("abort", cancelJob, { once: true });

  if (signal?.aborted) {
    cancelJob();
    throw new DOMException("Aborted", "AbortError");
  }

  onProgress?.(1);
  let reachedTerminalState = false;

  try {
    while (true) {
      await wait(1_500, signal);

      const statusResponse = await fetchApi(
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

      if (status.status === "failed" || status.status === "cancelled") {
        reachedTerminalState = true;
        throw new Error(
          status.error ??
            (status.status === "cancelled"
              ? "Story Reel rendering was cancelled."
              : "Story Reel generation failed."),
        );
      }

      if (status.status === "expired") {
        reachedTerminalState = true;
        throw new Error("The Story Reel expired before download.");
      }

      if (status.status !== "completed") continue;

      if (!status.download_url) {
        throw new Error("The completed Story Reel has no download URL.");
      }
      if (
        !status.story_source ||
        !status.artifact_source ||
        !status.visual_source ||
        !status.voice_source ||
        !status.variation_id ||
        status.animation_seed === null ||
        !status.music_track_id
      ) {
        throw new Error(
          "The completed Story Reel is missing verified artifact details.",
        );
      }

      const downloadResponse = await fetchApi(
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
      reachedTerminalState = true;

      return {
        video,
        source: status.story_source,
        artifactSource: status.artifact_source,
        visualSource: status.visual_source,
        visualModel: status.visual_model,
        voiceSource: status.voice_source,
        variationId: status.variation_id,
        animationSeed: status.animation_seed,
        musicTrackId: status.music_track_id,
      };
    }
  } finally {
    signal?.removeEventListener("abort", cancelJob);
    if (!reachedTerminalState) cancelJob();
  }
}
