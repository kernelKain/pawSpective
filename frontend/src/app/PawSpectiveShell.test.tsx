import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  analyzeCapturedClip,
  renderCapturedStoryReel,
  scoreCapturedClip,
  simulateCapturedObjectColors,
} from "./lib/sceneAnalysisApi";
import { PawSpectiveShell } from "./PawSpectiveShell";
import type {
  CapturedClip,
  ColorSimulationResponse,
  SceneEvent,
  VisibilityAnalysisResponse,
  VisibilityScore,
  StoryReelResult,
} from "./types/sceneAnalysis";

vi.mock("./lib/sceneAnalysisApi");
vi.mock("./components/LiveDogLens", () => ({
  LiveDogLens: ({
    onClipChange,
  }: {
    onClipChange: (clip: CapturedClip) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onClipChange({
          file: new File(["video"], "clip.mp4", {
            type: "video/mp4",
          }),
          durationMs: 8_000,
          source: "upload",
        })
      }
    >
      Provide test clip
    </button>
  ),
}));
vi.mock("./components/CuriosityMap", () => ({
  CuriosityMap: ({
    events,
    scores,
    onSelect,
  }: {
    events: SceneEvent[];
    scores: VisibilityScore[];
    onSelect: (eventId: string) => void;
  }) => (
    <div aria-label="Curiosity Map test view">
      <span>
        Curiosity scores: {scores
          .map((score) => `${score.event_id}:${score.salience_score}`)
          .join(",") || "none"}
      </span>
      {events.map((event) => (
        <button
          type="button"
          key={event.event_id}
          onClick={() => onSelect(event.event_id)}
        >
          Select {event.object_label}
        </button>
      ))}
    </div>
  ),
}));
vi.mock("./components/StoryReel", () => ({
  StoryReel: ({
    result,
    isRendering,
    error,
    disabled,
    onRender,
  }: {
    result: StoryReelResult | null;
    isRendering: boolean;
    error: string | null;
    disabled: boolean;
    onRender: () => void;
  }) => (
    <div aria-label="Story Reel test view">
      <button
        type="button"
        disabled={disabled || isRendering}
        onClick={onRender}
      >
        {isRendering ? "Creating Story Reel…" : "Create Story Reel"}
      </button>
      {result && <span>Story source: {result.source}</span>}
      {error && <div role="alert">{error}</div>}
    </div>
  ),
}));
vi.mock("./components/ToyColorLab", () => ({
  ToyColorLab: ({
    result,
    isLoading,
    error,
    disabled,
    onSimulate,
  }: {
    result: ColorSimulationResponse | null;
    isLoading: boolean;
    error: string | null;
    disabled: boolean;
    onSimulate: () => void;
  }) => (
    <div aria-label="Toy Color Lab test view">
      <button
        type="button"
        disabled={disabled || isLoading}
        onClick={onSimulate}
      >
        {isLoading ? "Comparing colors…" : "Try another color"}
      </button>
      {result && <span>Recommended color: {result.recommended_color_id}</span>}
      {error && <div role="alert">{error}</div>}
    </div>
  ),
}));

const mockedAnalyze = vi.mocked(analyzeCapturedClip);
const mockedScore = vi.mocked(scoreCapturedClip);
const mockedRenderStory = vi.mocked(renderCapturedStoryReel);
const mockedSimulateColors = vi.mocked(simulateCapturedObjectColors);

function sceneEvent(
  eventId: string,
  objectLabel: string,
  timestampMs: number,
): SceneEvent {
  return {
    event_id: eventId,
    timestamp_ms: timestampMs,
    object_label: objectLabel,
    category: "toy",
    bounding_box: {
      x_min: 0.1,
      y_min: 0.2,
      x_max: 0.4,
      y_max: 0.6,
    },
    confidence: 0.9,
    visible_evidence: `${objectLabel} is visible.`,
    motion_level: "low",
  };
}

const initialEvents = [sceneEvent("initial", "placeholder", 1_000)];
const analyzedEvents = [
  sceneEvent("ball", "blue ball", 2_000),
  sceneEvent("tree", "tree", 4_000),
];

const visibilityScore: VisibilityScore = {
  event_id: "ball",
  identification_confidence: 0.9,
  human_contrast_score: 70,
  dog_contrast_score: 84,
  contrast_change: 14,
  motion_score: 33,
  apparent_size_score: 69,
  profile_relevance_score: 100,
  salience_score: 75,
  salience_level: "high",
  human_object_color: "#2055D0",
  human_background_color: "#438A35",
  dog_object_color: "#3F6BC8",
  dog_background_color: "#8A813B",
  explanation:
    "The object remains distinct after the canine-vision approximation.",
  why: [
    "The transformed object/background contrast is high.",
  ],
};

const colorSimulation: ColorSimulationResponse = {
  simulation_version: "1.0",
  method: "fixed-swatch-background-lab-v1",
  event_id: "ball",
  original_human_color: "#2055D0",
  original_dog_color: "#3F6BC8",
  human_background_color: "#438A35",
  dog_background_color: "#8A813B",
  original_human_contrast_score: 70,
  original_dog_contrast_score: 84,
  recommended_color_id: "yellow",
  options: [],
  disclaimer:
    "Screen-color simulation using a fixed palette and the measured nearby background. It is not exact canine vision, object segmentation, or a physical-product guarantee.",
};

function visibilityResponse(
  warnings: string[] = [],
): VisibilityAnalysisResponse {
  return {
    scoring_version: "1.0",
    method: "bbox-region-lab-v1",
    scores: [visibilityScore],
    warnings,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });

  return { promise, resolve, reject };
}

function reachLens() {
  render(<PawSpectiveShell initialEvents={initialEvents} />);
  fireEvent.change(screen.getByLabelText("Your first name"), {
    target: { value: "Alex" },
  });
  fireEvent.change(screen.getByLabelText("Dog's name"), {
    target: { value: "Bruno" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: /Meet my co-pilot/ }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Provide test clip" }),
  );
}

async function reachResults(source: "gemini" | "demo" = "gemini") {
  mockedAnalyze.mockResolvedValue({
    source,
    analysis: {
      analysis_version: "1.0",
      duration_ms: 8_000,
      events: analyzedEvents,
      warnings: source === "demo" ? ["Cached fallback was used."] : [],
    },
  });
  reachLens();

  fireEvent.click(
    screen.getByRole("button", { name: "Analyze captured moment" }),
  );

  await screen.findByRole("heading", {
    name: "Bruno's visible scene",
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("PawSpectiveShell release flow", () => {
  it("labels demo fallback, supports corrections, and blocks scoring", async () => {
    await reachResults("demo");

    expect(
      screen.getByText(/validated cached response is being shown/),
    ).toBeDefined();

    const scoringButton = screen.getByRole("button", {
      name: "Calculate visibility & curiosity",
    });
    expect((scoringButton as HTMLButtonElement).disabled).toBe(true);

    const ballInput = screen.getByDisplayValue("blue ball");
    fireEvent.change(ballInput, { target: { value: "" } });
    expect((ballInput as HTMLInputElement).value).toBe("blue ball");

    fireEvent.change(ballInput, {
      target: { value: "  green ball  " },
    });
    fireEvent.blur(ballInput);
    expect((ballInput as HTMLInputElement).value).toBe("green ball");

    fireEvent.click(
      screen.getByRole("button", { name: "Remove tree" }),
    );
    expect(screen.getByText("1 objects")).toBeDefined();
    expect(mockedScore).not.toHaveBeenCalled();
  });

  it("renders a grounded Story Reel from corrected scored events", async () => {
    mockedScore.mockResolvedValue(visibilityResponse());
    mockedRenderStory.mockResolvedValue({
      video: new Blob(["story-mp4"], { type: "video/mp4" }),
      source: "gemini",
      artifactSource: "live_render",
      voiceSource: "elevenlabs",
      variationId: "original",
      animationSeed: 0,
      musicTrackId: "sunny-paws",
    });
    await reachResults();

    fireEvent.change(screen.getByDisplayValue("blue ball"), {
      target: { value: "green ball" },
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: "Calculate visibility & curiosity",
      }),
    );
    await screen.findByText("75/100 cue score");

    fireEvent.click(
      screen.getByRole("button", { name: "Create Story Reel" }),
    );

    await screen.findByText("Story source: gemini");

    expect(mockedRenderStory).toHaveBeenCalledTimes(1);
    expect(mockedRenderStory.mock.calls[0][1][0].object_label).toBe(
      "green ball",
    );
    expect(mockedRenderStory.mock.calls[0][2][0]).toEqual(
      visibilityScore,
    );
    expect(mockedRenderStory.mock.calls[0][3]).toBe("ball");
    expect(mockedRenderStory.mock.calls[0][4]).toMatchObject({
      owner_name: "Alex",
      dog_name: "Bruno",
      favorite_interest: "Ball",
    });
    expect(mockedRenderStory.mock.calls[0][5]).toBeInstanceOf(
      AbortSignal,
    );
    expect(mockedRenderStory.mock.calls[0][8]).toMatchObject({
      variationId: expect.any(String),
      animationSeed: expect.any(Number),
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Create Story Reel" }),
    );
    await waitFor(() => expect(mockedRenderStory).toHaveBeenCalledTimes(2));
    expect(mockedRenderStory.mock.calls[1][8]!.variationId).not.toBe(
      mockedRenderStory.mock.calls[0][8]!.variationId,
    );
    expect(mockedRenderStory.mock.calls[1][8]!.animationSeed % 3).not.toBe(
      mockedRenderStory.mock.calls[0][8]!.animationSeed % 3,
    );

    fireEvent.change(screen.getByDisplayValue("green ball"), {
      target: { value: "yellow ball" },
    });
    expect(screen.queryByText("Story source: gemini")).toBeNull();
  });

  it("shows a retryable Story Reel error", async () => {
    mockedScore.mockResolvedValue(visibilityResponse());
    mockedRenderStory.mockRejectedValue(
      new Error("The fictional dog voice is unavailable."),
    );
    await reachResults();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Calculate visibility & curiosity",
      }),
    );
    await screen.findByText("75/100 cue score");
    fireEvent.click(
      screen.getByRole("button", { name: "Create Story Reel" }),
    );

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain(
        "fictional dog voice",
      );
    });
    expect(
      screen.getByRole("button", { name: "Create Story Reel" }),
    ).toBeDefined();
  });

  it("returns to the lens with a safe analysis API error", async () => {
    mockedAnalyze.mockRejectedValue(new Error("Scene analysis timed out."));
    reachLens();

    fireEvent.click(
      screen.getByRole("button", { name: "Analyze captured moment" }),
    );

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain(
        "Scene analysis timed out.",
      );
    });
  });

  it("submits corrections and displays scores in both result views", async () => {
    mockedScore.mockResolvedValue(
      visibilityResponse(["One frame used a reduced sample."]),
    );
    await reachResults();

    const ballInput = screen.getByDisplayValue("blue ball");
    fireEvent.change(ballInput, {
      target: { value: "green ball" },
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Calculate visibility & curiosity",
      }),
    );

    await screen.findByText("75/100 cue score");

    const submittedEvents = mockedScore.mock.calls[0][1];
    expect(submittedEvents[0].object_label).toBe("green ball");
    expect(mockedScore.mock.calls[0][2]).toBe("Ball");
    expect(mockedScore.mock.calls[0][3]).toBeInstanceOf(AbortSignal);
    expect(
      screen.getByText("Curiosity scores: ball:75"),
    ).toBeDefined();
    expect(
      screen.getByRole("heading", { name: "green ball" }),
    ).toBeDefined();
    expect(
      screen.getByText("One frame used a reduced sample."),
    ).toBeDefined();
  });

  it("shows visibility scoring failures as an alert", async () => {
    mockedScore.mockRejectedValue(
      new Error("No corrected event could be scored from this video."),
    );
    await reachResults();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Calculate visibility & curiosity",
      }),
    );

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain(
        "No corrected event could be scored",
      );
    });
  });

  it("invalidates completed scores after renaming or removing an event", async () => {
    mockedScore.mockResolvedValue(visibilityResponse());
    await reachResults();

    const calculateButton = screen.getByRole("button", {
      name: "Calculate visibility & curiosity",
    });
    fireEvent.click(calculateButton);
    await screen.findByText("75/100 cue score");

    fireEvent.change(screen.getByDisplayValue("blue ball"), {
      target: { value: "green ball" },
    });

    expect(
      screen.getByText("Curiosity scores: none"),
    ).toBeDefined();
    expect(
      screen.getByText(
        /calculate visibility to see a deterministic comparison/i,
      ),
    ).toBeDefined();

    fireEvent.click(calculateButton);
    await screen.findByText("75/100 cue score");
    fireEvent.click(
      screen.getByRole("button", { name: "Remove tree" }),
    );

    expect(
      screen.getByText("Curiosity scores: none"),
    ).toBeDefined();
    expect(
      screen.queryByText("75/100 cue score"),
    ).toBeNull();
  });

  it("locks corrections, aborts navigation, and ignores a late response", async () => {
    const pendingScore = deferred<VisibilityAnalysisResponse>();
    mockedScore.mockReturnValue(pendingScore.promise);
    await reachResults();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Calculate visibility & curiosity",
      }),
    );

    const ballInput = screen.getByDisplayValue("blue ball");
    const removeButton = screen.getByRole("button", {
      name: "Remove tree",
    });
    const tryAnotherButton = screen.getByRole("button", {
      name: "Try another moment",
    });

    expect((ballInput as HTMLInputElement).disabled).toBe(true);
    expect((removeButton as HTMLButtonElement).disabled).toBe(true);
    expect((tryAnotherButton as HTMLButtonElement).disabled).toBe(true);
    expect(mockedScore.mock.calls[0][1][0].object_label).toBe(
      "blue ball",
    );

    const requestSignal = mockedScore.mock.calls[0][3];
    fireEvent.click(
      screen.getByRole("button", { name: "Return to profile" }),
    );

    expect(requestSignal?.aborted).toBe(true);

    pendingScore.resolve(visibilityResponse());

    await waitFor(() => {
      expect(
        screen.getByRole("heading", {
          name: /dog-shaped perspective/i,
        }),
      ).toBeDefined();
    });
    expect(
      screen.queryByText("75/100 cue score"),
    ).toBeNull();
  });

  it("requires a score and clears a Toy Color Lab result when selection changes", async () => {
    mockedScore.mockResolvedValue(visibilityResponse());
    mockedSimulateColors.mockResolvedValue(colorSimulation);
    await reachResults();

    const colorButton = screen.getByRole("button", {
      name: "Try another color",
    });
    expect((colorButton as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Calculate visibility & curiosity",
      }),
    );
    await screen.findByText("75/100 cue score");
    fireEvent.click(colorButton);
    await screen.findByText("Recommended color: yellow");

    expect(mockedSimulateColors).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ event_id: "ball" }),
      expect.any(AbortSignal),
      "gemini",
    );

    fireEvent.click(screen.getByRole("button", { name: "Select tree" }));
    expect(screen.queryByText("Recommended color: yellow")).toBeNull();
  });

  it("does not add simulated colors to Story Reel grounding", async () => {
    mockedScore.mockResolvedValue(visibilityResponse());
    mockedSimulateColors.mockResolvedValue(colorSimulation);
    mockedRenderStory.mockResolvedValue({
      video: new Blob(["story"], { type: "video/mp4" }),
      source: "gemini",
      artifactSource: "live_render",
      voiceSource: "elevenlabs",
      variationId: "original",
      animationSeed: 0,
      musicTrackId: "sunny-paws",
    });
    await reachResults();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Calculate visibility & curiosity",
      }),
    );
    await screen.findByText("75/100 cue score");
    fireEvent.click(screen.getByRole("button", { name: "Try another color" }));
    await screen.findByText("Recommended color: yellow");
    fireEvent.click(screen.getByRole("button", { name: "Create Story Reel" }));
    await screen.findByText("Story source: gemini");

    expect(mockedRenderStory.mock.calls[0][1]).toEqual(analyzedEvents);
    expect(mockedRenderStory.mock.calls[0][2]).toEqual([visibilityScore]);
  });

  it("aborts and ignores an in-flight color simulation after selection changes", async () => {
    const pendingSimulation = deferred<ColorSimulationResponse>();
    mockedScore.mockResolvedValue(visibilityResponse());
    mockedSimulateColors.mockReturnValue(pendingSimulation.promise);
    await reachResults();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Calculate visibility & curiosity",
      }),
    );
    await screen.findByText("75/100 cue score");
    fireEvent.click(screen.getByRole("button", { name: "Try another color" }));

    await waitFor(() => expect(mockedSimulateColors).toHaveBeenCalledOnce());
    const requestSignal = mockedSimulateColors.mock.calls[0][2];
    fireEvent.click(screen.getByRole("button", { name: "Select tree" }));

    expect(requestSignal?.aborted).toBe(true);
    pendingSimulation.resolve(colorSimulation);

    await waitFor(() => {
      expect(screen.queryByText("Recommended color: yellow")).toBeNull();
    });
  });

  it("offers retry and rehearsal recovery when no objects are detected", async () => {
    mockedAnalyze.mockResolvedValue({
      source: "gemini",
      analysis: {
        analysis_version: "1.0",
        duration_ms: 8_000,
        events: [],
        warnings: ["No useful visible objects were detected."],
      },
    });
    reachLens();

    fireEvent.click(
      screen.getByRole("button", { name: "Analyze captured moment" }),
    );

    expect(
      await screen.findByRole("heading", {
        name: "No useful visible objects detected",
      }),
    ).toBeDefined();
    expect(screen.getByRole("button", { name: "Try another clip" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Use controlled demo" })).toBeDefined();
  });

  it("isolates the app while the accuracy drawer is open", async () => {
    render(<PawSpectiveShell initialEvents={initialEvents} />);
    const opener = screen.getAllByRole("button", { name: "How accurate is this?" })[0];
    opener.focus();
    fireEvent.click(opener);

    const main = document.querySelector("main");
    expect(main?.hasAttribute("inert")).toBe(true);
    expect(main?.getAttribute("aria-hidden")).toBe("true");
    expect(await screen.findByRole("button", { name: "Close" })).toBe(
      document.activeElement,
    );

    fireEvent.keyDown(document, { key: "Escape" });
    expect(main?.hasAttribute("inert")).toBe(false);
    expect(main?.hasAttribute("aria-hidden")).toBe(false);
    expect(opener).toBe(document.activeElement);
  });

  it("discloses profile processing without overstating photo privacy", () => {
    render(<PawSpectiveShell initialEvents={initialEvents} />);

    expect(screen.getByText(/Your photo stays in this browser/i)).toBeDefined();
    expect(screen.getByText(/dog details may be shared with Gemini/i)).toBeDefined();
    expect(screen.getByText(/narration sent to ElevenLabs/i)).toBeDefined();
    expect(screen.getByText(/first name is sent to neither provider/i)).toBeDefined();
  });

  it("rejects spoofed and excessive-dimension photos before preview", async () => {
    const decode = vi.fn().mockResolvedValue({
      width: 50_000,
      height: 50_000,
      close: vi.fn(),
    });
    vi.stubGlobal("createImageBitmap", decode);
    const { container } = render(<PawSpectiveShell initialEvents={initialEvents} />);
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    fireEvent.change(input!, {
      target: {
        files: [new File(["not-a-png"], "spoofed.png", { type: "image/png" })],
      },
    });
    expect((await screen.findByRole("alert")).textContent).toMatch(/does not match/i);
    expect(decode).not.toHaveBeenCalled();
    expect(screen.queryByAltText("Dog profile preview")).toBeNull();

    const pngHeader = new Uint8Array([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0,
    ]);
    fireEvent.change(input!, {
      target: {
        files: [new File([pngHeader], "huge.png", { type: "image/png" })],
      },
    });
    expect((await screen.findByRole("alert")).textContent).toMatch(/24 megapixels/i);
    expect(screen.queryByAltText("Dog profile preview")).toBeNull();
  });
});
