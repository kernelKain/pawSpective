import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import type { CapturedClip } from "../types/sceneAnalysis";
import {
  analyzeCapturedClip,
  scoreCapturedClip,
} from "./sceneAnalysisApi";

const clip: CapturedClip = {
  file: new File(
    ["synthetic-video"],
    "clip.mp4",
    { type: "video/mp4" },
  ),
  durationMs: 8_000,
  source: "upload",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("analyzeCapturedClip", () => {
  it("posts the clip and returns the backend response", async () => {
    const payload = {
      source: "gemini" as const,
      analysis: {
        analysis_version: "1.0" as const,
        duration_ms: 8_000,
        events: [],
        warnings: [],
      },
    };

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify(payload),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      analyzeCapturedClip(clip),
    ).resolves.toEqual(payload);

    expect(fetchMock).toHaveBeenCalledTimes(1);

    const [url, request] = fetchMock.mock.calls[0];

    expect(url).toBe(
      "http://localhost:8000/api/v1/analyze-video",
    );
    expect(request.method).toBe("POST");
    expect(request.body).toBeInstanceOf(FormData);

    const formData = request.body as FormData;

    const uploadedFile = formData.get("file");

    expect(uploadedFile).toBeInstanceOf(File);
    expect((uploadedFile as File).name).toBe(
      clip.file.name,
    );
    expect((uploadedFile as File).type).toBe(
      clip.file.type,
    );
    expect((uploadedFile as File).size).toBe(
      clip.file.size,
    );
  });

  it("surfaces a safe backend error message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "The video is not readable.",
          }),
          {
            status: 422,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );

    await expect(
      analyzeCapturedClip(clip),
    ).rejects.toThrow("The video is not readable.");
  });

  it("uses the fallback message for non-JSON errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          "Gateway failure",
          { status: 502 },
        ),
      ),
    );

    await expect(
      analyzeCapturedClip(clip),
    ).rejects.toThrow("Scene analysis failed.");
  });
});

describe("scoreCapturedClip", () => {
  it("submits corrected events for deterministic scoring", async () => {
    const responsePayload = {
      scoring_version: "1.0" as const,
      method: "bbox-region-lab-v1" as const,
      scores: [],
      warnings: [],
    };

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify(responsePayload),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    vi.stubGlobal("fetch", fetchMock);
    const abortController = new AbortController();

    await expect(
      scoreCapturedClip(
        clip,
        [
          {
            event_id: "ball-1",
            timestamp_ms: 1_000,
            object_label: "blue ball",
            category: "toy",
            bounding_box: {
              x_min: 0.2,
              y_min: 0.2,
              x_max: 0.5,
              y_max: 0.5,
            },
            confidence: 0.9,
            visible_evidence: "A blue ball is visible.",
            motion_level: "medium",
          },
        ],
        "Ball",
        abortController.signal,
      ),
    ).resolves.toEqual(responsePayload);

    expect(fetchMock).toHaveBeenCalledTimes(1);

    const [url, request] = fetchMock.mock.calls[0];

    expect(url).toBe(
      "http://localhost:8000/api/v1/score-visibility",
    );
    expect(request.method).toBe("POST");
    expect(request.body).toBeInstanceOf(FormData);
    expect(request.signal).toBe(abortController.signal);

    const formData = request.body as FormData;
    const payload = JSON.parse(
      formData.get("payload") as string,
    );

    const uploadedFile = formData.get("file");

    expect(uploadedFile).toBeInstanceOf(File);
    expect((uploadedFile as File).name).toBe(
      clip.file.name,
    );
    expect((uploadedFile as File).type).toBe(
      clip.file.type,
    );
    expect((uploadedFile as File).size).toBe(
      clip.file.size,
    );
    expect(payload.analysis_source).toBe("gemini");
    expect(payload.favorite_interest).toBe("Ball");
    expect(payload.events).toHaveLength(1);
    expect(payload.events[0].event_id).toBe("ball-1");
    expect(payload.events[0].object_label).toBe("blue ball");
  });

  it("surfaces a backend visibility-scoring error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "The object region is too small to score.",
          }),
          {
            status: 422,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );

    await expect(
      scoreCapturedClip(
        clip,
        [
          {
            event_id: "ball-1",
            timestamp_ms: 1_000,
            object_label: "blue ball",
            category: "toy",
            bounding_box: {
              x_min: 0.2,
              y_min: 0.2,
              x_max: 0.5,
              y_max: 0.5,
            },
            confidence: 0.9,
            visible_evidence: "A blue ball is visible.",
            motion_level: "medium",
          },
        ],
        "Ball",
      ),
    ).rejects.toThrow(
      "The object region is too small to score.",
    );
  });

  it("uses the fallback visibility error for non-JSON responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          "Gateway failure",
          { status: 502 },
        ),
      ),
    );

    await expect(
      scoreCapturedClip(
        clip,
        [
          {
            event_id: "ball-1",
            timestamp_ms: 1_000,
            object_label: "blue ball",
            category: "toy",
            bounding_box: {
              x_min: 0.2,
              y_min: 0.2,
              x_max: 0.5,
              y_max: 0.5,
            },
            confidence: 0.9,
            visible_evidence: "A blue ball is visible.",
            motion_level: "medium",
          },
        ],
        "Ball",
      ),
    ).rejects.toThrow("Visibility scoring failed.");
  });
});
