import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";

import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import type {
  CapturedClip,
  SceneEvent,
  VisibilityScore,
} from "../types/sceneAnalysis";
import { CuriosityMap } from "./CuriosityMap";

const clip: CapturedClip = {
  file: new File(
    ["synthetic-video"],
    "clip.mp4",
    { type: "video/mp4" },
  ),
  durationMs: 8_000,
  source: "upload",
};

const events: SceneEvent[] = [
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
    confidence: 0.91,
    visible_evidence: "A blue ball is visible.",
    motion_level: "medium",
  },
];

const scores: VisibilityScore[] = [
  {
    event_id: "ball-1",
    identification_confidence: 0.91,

    human_contrast_score: 70,
    dog_contrast_score: 84,
    contrast_change: 14,

    motion_score: 67,
    apparent_size_score: 60,
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
      "The AI-inferred motion label increased the cue score.",
    ],
  },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CuriosityMap", () => {
  it("selects and seeks to a timeline event", () => {
    const createObjectURL = vi.fn(
      () => "blob:pawspective-test",
    );
    const revokeObjectURL = vi.fn();

    vi.stubGlobal("URL", {
      createObjectURL,
      revokeObjectURL,
    });

    const onSelect = vi.fn();

    const { container } = render(
      <CuriosityMap
        clip={clip}
        events={events}
        scores={scores}
        selectedEventId=""
        onSelect={onSelect}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /1\.0s · blue ball/i,
      }),
    );

    expect(onSelect).toHaveBeenCalledWith("ball-1");

    const video = container.querySelector("video");

    expect(video).not.toBeNull();
    expect(video?.currentTime).toBe(1);
  });

  it("shows why the selected cue appeared", () => {
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(
        () => "blob:pawspective-test",
      ),
      revokeObjectURL: vi.fn(),
    });

    render(
      <CuriosityMap
        clip={clip}
        events={events}
        scores={scores}
        selectedEventId="ball-1"
        onSelect={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Why this appeared"),
    ).toBeDefined();

    expect(
      screen.getByText(
        "The AI-inferred motion label increased the cue score.",
      ),
    ).toBeDefined();

    expect(
      screen.getByText(/This is not gaze tracking/i),
    ).toBeDefined();
  });

  it("keeps the overlay on the uncropped video and controls outside it", () => {
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(
        () => "blob:pawspective-test",
      ),
      revokeObjectURL: vi.fn(),
    });

    const { container } = render(
      <CuriosityMap
        clip={clip}
        events={events}
        scores={scores}
        selectedEventId="ball-1"
        onSelect={vi.fn()}
      />,
    );

    const stage = container.querySelector(
      ".curiosity-video-stage",
    );
    const video = stage?.querySelector("video");
    const overlay = stage?.querySelector(
      ".curiosity-overlay",
    );
    const controls = container.querySelector(
      ".curiosity-playback-controls",
    );

    expect(stage).not.toBeNull();
    expect(video).not.toBeNull();
    expect(video?.hasAttribute("controls")).toBe(false);
    expect(overlay).not.toBeNull();
    expect(controls).not.toBeNull();
    expect(stage?.contains(controls)).toBe(false);
    expect(
      screen.getByRole("slider", {
        name: "Video position",
      }),
    ).toBeDefined();
  });

  it("creates object URLs after commit and revokes every replaced URL", () => {
    const createObjectURL = vi
      .fn()
      .mockReturnValueOnce("blob:first")
      .mockReturnValueOnce("blob:second");
    const revokeObjectURL = vi.fn();

    vi.stubGlobal("URL", {
      createObjectURL,
      revokeObjectURL,
    });

    const secondClip: CapturedClip = {
      ...clip,
      file: new File(
        ["second-video"],
        "second.mp4",
        { type: "video/mp4" },
      ),
    };

    const { rerender, unmount } = render(
      <CuriosityMap
        clip={clip}
        events={events}
        scores={scores}
        selectedEventId="ball-1"
        onSelect={vi.fn()}
      />,
    );

    rerender(
      <CuriosityMap
        clip={secondClip}
        events={events}
        scores={scores}
        selectedEventId="ball-1"
        onSelect={vi.fn()}
      />,
    );

    expect(createObjectURL).toHaveBeenCalledTimes(2);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:first");

    unmount();

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:second");
  });
});
