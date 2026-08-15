import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { analyzeCapturedClip } from "./sceneAnalysisApi";
import type { CapturedClip } from "../types/sceneAnalysis";


const clip: CapturedClip = {
  file: new File(["video"], "clip.mp4", { type: "video/mp4" }),
  durationMs: 8_000,
  source: "upload",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("analyzeCapturedClip", () => {
  it("posts the clip and returns the validated backend shape", async () => {
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
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(analyzeCapturedClip(clip)).resolves.toEqual(payload);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/analyze-video");
    expect(options.method).toBe("POST");
    expect(options.body).toBeInstanceOf(FormData);
  });

  it("surfaces the backend's safe error detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "The video is not readable." }),
          {
            status: 422,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    await expect(analyzeCapturedClip(clip)).rejects.toThrow(
      "The video is not readable.",
    );
  });

  it("uses a safe default when an error body is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("gateway failure", { status: 502 }),
      ),
    );

    await expect(analyzeCapturedClip(clip)).rejects.toThrow(
      "Scene analysis failed.",
    );
  });
});
