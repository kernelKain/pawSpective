import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import type {
  CapturedClip,
  SceneEvent,
  StoryProfileInput,
  VisibilityScore,
} from "../types/sceneAnalysis";
import {
  analyzeCapturedClip,
  loadControlledDemo,
  renderCapturedStoryReel,
  simulateCapturedObjectColors,
} from "./sceneAnalysisApi";

const fetchMock = vi.fn<typeof fetch>();

const clip = {
  file: new File(
    ["fake-video-content"],
    "bruno-walk.mp4",
    {
      type: "video/mp4",
    },
  ),
} as CapturedClip;

const events = [
  {
    id: "event-1",
    label: "Red ball",
    start_seconds: 1,
    end_seconds: 3,
  },
] as unknown as SceneEvent[];

const colorEvent: SceneEvent = {
  event_id: "event-1",
  timestamp_ms: 1_000,
  object_label: "  Red ball  ",
  category: "toy",
  bounding_box: {
    x_min: 0.2,
    y_min: 0.2,
    x_max: 0.5,
    y_max: 0.5,
  },
  confidence: 0.9,
  visible_evidence: "A red ball is visible.",
  motion_level: "medium",
};

const scores = [
  {
    event_id: "event-1",
    visibility_score: 82,
  },
] as unknown as VisibilityScore[];

const profile = {
  owner_name: "Alex",
  dog_name: "Bruno",
  breed: "Labrador",
  age: "Adult",
  size: "Large",
  personality_tags: [
    "Curious",
    "Playful",
  ],
  favorite_interest: "Balls",
} as StoryProfileInput;

function jsonResponse(
  payload: unknown,
  ok = true,
): Response {
  return {
    ok,
    json: vi.fn().mockResolvedValue(payload),
  } as unknown as Response;
}

function videoResponse(
  video: Blob,
  ok = true,
): Response {
  return {
    ok,
    blob: vi.fn().mockResolvedValue(video),
    json: vi.fn().mockResolvedValue({}),
  } as unknown as Response;
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.resetAllMocks();
});

describe("sceneAnalysisApi", () => {
  it("explains backend connectivity failures during scene analysis", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(
      analyzeCapturedClip(clip),
    ).rejects.toThrow(
      "PawSpective could not reach the analysis service. Check the deployed API URL and allowed frontend origin, then try again.",
    );
  });

  it("loads the verified controlled demo bundle", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          available: true,
          duration_ms: 8_000,
          clip_url: "/api/v1/demo/clip",
          profile,
        }),
      )
      .mockResolvedValueOnce(
        videoResponse(new Blob(["demo"], { type: "video/mp4" })),
      );

    const demo = await loadControlledDemo();

    expect(demo.clip.source).toBe("controlled_demo");
    expect(demo.clip.durationMs).toBe(8_000);
    expect(demo.clip.file.name).toBe("controlled-demo.mp4");
    expect(demo.profile.dog_name).toBe("Bruno");
  });

  it(
    "exports the background Story Reel client",
    () => {
      expect(
        renderCapturedStoryReel,
      ).toBeTypeOf("function");
    },
  );

  it("submits a trimmed Gemini event to Toy Color Lab", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        simulation_version: "1.0",
        method: "fixed-swatch-background-lab-v1",
        event_id: "event-1",
        recommended_color_id: "blue",
        options: [],
      }),
    );
    const abortController = new AbortController();

    await simulateCapturedObjectColors(
      clip,
      colorEvent,
      abortController.signal,
    );

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/simulate-object-colors");
    expect(options.signal).toBe(abortController.signal);
    const formData = options.body as FormData;
    const uploadedFile = formData.get("file") as File;
    expect(uploadedFile.name).toBe(clip.file.name);
    expect(uploadedFile.type).toBe(clip.file.type);
    expect(JSON.parse(String(formData.get("payload")))).toMatchObject({
      analysis_source: "gemini",
      event: {
        event_id: "event-1",
        object_label: "Red ball",
      },
    });
  });

  it("uses the Toy Color Lab API error and forwards abort failures", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: "The selected frame could not be read." }, false),
    );

    await expect(
      simulateCapturedObjectColors(clip, colorEvent),
    ).rejects.toThrow("The selected frame could not be read.");

    fetchMock.mockRejectedValueOnce(new DOMException("Aborted", "AbortError"));
    await expect(
      simulateCapturedObjectColors(
        clip,
        colorEvent,
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ name: "AbortError" });
  });

  it(
    "creates a multipart job, polls it, downloads the result, and reports progress",
    async () => {
      const renderedVideo = new Blob(
        ["rendered-mp4"],
        {
          type: "video/mp4",
        },
      );

      fetchMock
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-1",
            status: "queued",
            status_url:
              "/api/v1/story-jobs/job-1",
          }),
        )
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-1",
            status: "running",
            progress: 25,
            error: null,
            download_url: null,
            story_source: null,
          }),
        )
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-1",
            status: "completed",
            progress: 90,
            error: null,
            download_url:
              "/api/v1/story-jobs/job-1/download",
            story_source: "gemini",
            artifact_source: "live_render",
            voice_source: "elevenlabs",
            variation_id: "original",
            animation_seed: 0,
            music_track_id: "sunny-paws",
            visual_source: "gemini_omni",
            visual_model: "gemini-omni-flash-preview",
          }),
        )
        .mockResolvedValueOnce(
          videoResponse(renderedVideo),
        );

      const onProgress = vi.fn();

      const resultPromise =
        renderCapturedStoryReel(
          clip,
          events,
          scores,
          "event-1",
          profile,
          undefined,
          onProgress,
        );

      await vi.advanceTimersByTimeAsync(
        1_500,
      );

      await vi.advanceTimersByTimeAsync(
        1_500,
      );

      const result = await resultPromise;

      expect(fetchMock).toHaveBeenCalledTimes(4);

      const [
        createUrl,
        createOptions,
      ] = fetchMock.mock.calls[0] as [
        string,
        RequestInit,
      ];

      expect(createUrl).toContain(
        "/api/v1/story-jobs",
      );

      expect(createOptions.method).toBe(
        "POST",
      );

      expect(
        createOptions.body,
      ).toBeInstanceOf(FormData);

      const formData =
        createOptions.body as FormData;

      const uploadedFile = formData.get(
        "file",
      ) as File;

      expect(uploadedFile.name).toBe(
        "bruno-walk.mp4",
      );

      expect(uploadedFile.type).toBe(
        "video/mp4",
      );

      const payloadValue =
        formData.get("payload");

      expect(typeof payloadValue).toBe(
        "string",
      );

      const payload = JSON.parse(
        payloadValue as string,
      ) as {
        analysis_source: string;
        style: string;
        variation_id: string;
        animation_seed: number;
        profile: StoryProfileInput;
        events: SceneEvent[];
        scores: VisibilityScore[];
        featured_event_id: string;
      };

      expect(payload).toMatchObject({
        analysis_source: "gemini",
        style: "nature_documentary",
        variation_id: "original",
        animation_seed: 0,
        featured_event_id: "event-1",
        profile,
      });

      expect(payload.events).toEqual(events);
      expect(payload.scores).toEqual(scores);

      const [
        firstStatusUrl,
        firstStatusOptions,
      ] = fetchMock.mock.calls[1] as [
        string,
        RequestInit,
      ];

      expect(firstStatusUrl).toContain(
        "/api/v1/story-jobs/job-1",
      );

      expect(firstStatusOptions).toMatchObject({
        method: "GET",
        cache: "no-store",
      });

      const [
        downloadUrl,
        downloadOptions,
      ] = fetchMock.mock.calls[3] as [
        string,
        RequestInit,
      ];

      expect(downloadUrl).toContain(
        "/api/v1/story-jobs/job-1/download",
      );

      expect(downloadOptions).toMatchObject({
        method: "GET",
        cache: "no-store",
      });

      expect(result.video).toBe(
        renderedVideo,
      );

      expect(result).toMatchObject({
        source: "gemini",
        artifactSource: "live_render",
        voiceSource: "elevenlabs",
        variationId: "original",
        animationSeed: 0,
        musicTrackId: "sunny-paws",
      });

      expect(
        onProgress.mock.calls.map(
          ([progress]) => progress,
        ),
      ).toEqual([
        0,
        1,
        25,
        90,
        100,
      ]);
    },
  );

  it(
    "clamps progress values returned by the backend",
    async () => {
      const renderedVideo = new Blob(
        ["rendered-mp4"],
        {
          type: "video/mp4",
        },
      );

      fetchMock
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-clamped",
            status: "queued",
            status_url:
              "/api/v1/story-jobs/job-clamped",
          }),
        )
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-clamped",
            status: "running",
            progress: 150,
            error: null,
            download_url: null,
            story_source: null,
          }),
        )
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-clamped",
            status: "completed",
            progress: -20,
            error: null,
            download_url:
              "/api/v1/story-jobs/job-clamped/download",
            story_source: "template",
            artifact_source: "live_render",
            voice_source: "elevenlabs",
            variation_id: "original",
            animation_seed: 0,
            music_track_id: "sunny-paws",
            visual_source: "local_animation_fallback",
            visual_model: null,
          }),
        )
        .mockResolvedValueOnce(
          videoResponse(renderedVideo),
        );

      const onProgress = vi.fn();

      const resultPromise =
        renderCapturedStoryReel(
          clip,
          events,
          scores,
          "event-1",
          profile,
          undefined,
          onProgress,
        );

      await vi.advanceTimersByTimeAsync(
        3_000,
      );

      const result = await resultPromise;

      expect(result.source).toBe("template");

      expect(
        onProgress.mock.calls.map(
          ([progress]) => progress,
        ),
      ).toEqual([
        0,
        1,
        100,
        0,
        100,
      ]);
    },
  );

  it(
    "reports a failed Story Reel job",
    async () => {
      fetchMock
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-failed",
            status: "queued",
            status_url:
              "/api/v1/story-jobs/job-failed",
          }),
        )
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-failed",
            status: "failed",
            progress: 55,
            error:
              "The fictional voice could not be generated.",
            download_url: null,
            story_source: null,
          }),
        );

      const resultPromise =
        renderCapturedStoryReel(
          clip,
          events,
          scores,
          "event-1",
          profile,
        );

      const rejection = expect(
        resultPromise,
      ).rejects.toThrow(
        "The fictional voice could not be generated.",
      );

      await vi.advanceTimersByTimeAsync(
        1_500,
      );

      await rejection;

      expect(fetchMock).toHaveBeenCalledTimes(2);
    },
  );

  it(
    "rejects completed jobs without a download URL",
    async () => {
      fetchMock
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-no-download",
            status: "queued",
            status_url:
              "/api/v1/story-jobs/job-no-download",
          }),
        )
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-no-download",
            status: "completed",
            progress: 100,
            error: null,
            download_url: null,
            story_source: "gemini",
            artifact_source: "live_render",
            voice_source: "elevenlabs",
            variation_id: "original",
            animation_seed: 0,
            music_track_id: "sunny-paws",
          }),
        )
        .mockResolvedValueOnce(jsonResponse({}));

      const resultPromise =
        renderCapturedStoryReel(
          clip,
          events,
          scores,
          "event-1",
          profile,
        );

      const rejection = expect(
        resultPromise,
      ).rejects.toThrow(
        "The completed Story Reel has no download URL.",
      );

      await vi.advanceTimersByTimeAsync(
        1_500,
      );

      await rejection;

      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining("/api/v1/story-jobs/job-no-download"),
        expect.objectContaining({ method: "DELETE" }),
      );
    },
  );

  it(
    "reports an expired Story Reel job",
    async () => {
      fetchMock
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-expired",
            status: "queued",
            status_url:
              "/api/v1/story-jobs/job-expired",
          }),
        )
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-expired",
            status: "expired",
            progress: 100,
            error: null,
            download_url: null,
            story_source: null,
          }),
        );

      const resultPromise =
        renderCapturedStoryReel(
          clip,
          events,
          scores,
          "event-1",
          profile,
        );

      const rejection = expect(
        resultPromise,
      ).rejects.toThrow(
        "The Story Reel expired before download.",
      );

      await vi.advanceTimersByTimeAsync(
        1_500,
      );

      await rejection;
    },
  );

  it(
    "continues polling beyond two minutes until aborted",
    async () => {
      fetchMock
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-timeout",
            status: "queued",
            status_url:
              "/api/v1/story-jobs/job-timeout",
          }),
        )
        .mockImplementation(async () =>
          jsonResponse({
            job_id: "job-timeout",
            status: "running",
            progress: 50,
            error: null,
            download_url: null,
            story_source: null,
          }),
        );

      const controller = new AbortController();
      const resultPromise =
        renderCapturedStoryReel(
          clip,
          events,
          scores,
          "event-1",
          profile,
          controller.signal,
        );

      const rejection = expect(
        resultPromise,
      ).rejects.toMatchObject({
        name: "AbortError",
      });

      await vi.advanceTimersByTimeAsync(
        120_000,
      );

      expect(
        fetchMock.mock.calls.length,
      ).toBeGreaterThan(1);

      controller.abort();
      await rejection;
    },
  );

  it(
    "cancels Story Reel polling with an AbortSignal",
    async () => {
      fetchMock
        .mockResolvedValueOnce(
          jsonResponse({
            job_id: "job-cancelled",
            status: "queued",
            status_url:
              "/api/v1/story-jobs/job-cancelled",
          }),
        )
        .mockResolvedValueOnce(jsonResponse({}));

      const controller =
        new AbortController();

      const resultPromise =
        renderCapturedStoryReel(
          clip,
          events,
          scores,
          "event-1",
          profile,
          controller.signal,
        );

      const rejection = expect(
        resultPromise,
      ).rejects.toMatchObject({
        name: "AbortError",
      });

      await vi.advanceTimersByTimeAsync(0);
      controller.abort();

      await rejection;

      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining("/api/v1/story-jobs/job-cancelled"),
        expect.objectContaining({
          method: "DELETE",
          cache: "no-store",
          keepalive: true,
        }),
      );
    },
  );
});


describe("Story variation cancellation", () => {
  it("clears the legacy job reference and requests cancellation when polling is aborted", async () => {
    window.localStorage.clear();
    window.localStorage.setItem("pawspective-story-job-id", "legacy-job");
    const controller = new AbortController();
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          job_id: "a".repeat(32),
          status: "queued",
          status_url: `/api/v1/story-jobs/${"a".repeat(32)}`,
          variation_id: "variation-safe",
          animation_seed: 7,
          music_track_id: "curious-steps",
        }),
      )
      .mockResolvedValueOnce(jsonResponse({}));

    const pending = renderCapturedStoryReel(
      clip,
      events,
      scores,
      "event-1",
      profile,
      controller.signal,
      undefined,
      "gemini",
      { variationId: "variation-safe", animationSeed: 7 },
    );

    const rejection = expect(pending).rejects.toMatchObject({ name: "AbortError" });

    await vi.advanceTimersByTimeAsync(0);
    expect(window.localStorage.getItem("pawspective-story-job-id")).toBeNull();
    controller.abort();
    await rejection;

    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining("/api/v1/story-jobs/"),
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
