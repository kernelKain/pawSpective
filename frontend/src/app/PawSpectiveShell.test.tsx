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

import { analyzeCapturedClip } from "./lib/sceneAnalysisApi";
import { PawSpectiveShell } from "./PawSpectiveShell";
import type {
  CapturedClip,
  SceneEvent,
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

const mockedAnalyze = vi.mocked(analyzeCapturedClip);

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

function reachLens() {
  render(<PawSpectiveShell initialEvents={initialEvents} />);
  fireEvent.change(screen.getByLabelText("Your first name"), {
    target: { value: "Kshitij" },
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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PawSpectiveShell Phase 3 flow", () => {
  it("uses analyzed events, labels fallback, and supports valid corrections", async () => {
    mockedAnalyze.mockResolvedValue({
      source: "demo",
      analysis: {
        analysis_version: "1.0",
        duration_ms: 8_000,
        events: analyzedEvents,
        warnings: ["Cached fallback was used."],
      },
    });
    reachLens();

    fireEvent.click(
      screen.getByRole("button", { name: "Analyze captured moment" }),
    );

    await screen.findByRole("heading", {
      name: "Bruno's visible scene",
    });
    expect(
      screen.getByText(/validated cached response is being shown/),
    ).toBeDefined();

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
  });

  it("returns to the lens with a safe API error", async () => {
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
    expect(
      screen.getByRole("button", { name: "Analyze captured moment" }),
    ).toBeDefined();
  });
});
