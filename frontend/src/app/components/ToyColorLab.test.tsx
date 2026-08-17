import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CapturedClip, ColorSimulationResponse, SceneEvent } from "../types/sceneAnalysis";
import { ToyColorLab } from "./ToyColorLab";

const clip: CapturedClip = {
  file: new File(["video"], "clip.mp4", { type: "video/mp4" }),
  durationMs: 8_000,
  source: "upload",
};
const event: SceneEvent = {
  event_id: "ball",
  timestamp_ms: 2_000,
  object_label: "blue ball",
  category: "toy",
  bounding_box: { x_min: 0.1, y_min: 0.2, x_max: 0.4, y_max: 0.6 },
  confidence: 0.9,
  visible_evidence: "A blue ball is visible.",
  motion_level: "medium",
};
const result: ColorSimulationResponse = {
  simulation_version: "1.0",
  method: "fixed-swatch-background-lab-v1",
  event_id: "ball",
  original_human_color: "#2F6BFF",
  original_dog_color: "#596CD7",
  human_background_color: "#43AA4B",
  dog_background_color: "#9C914A",
  original_human_contrast_score: 70,
  original_dog_contrast_score: 50,
  recommended_color_id: "yellow",
  options: [
    { color_id: "yellow", label: "Bright yellow", human_color: "#FFD43B", dog_approx_color: "#F0D13C", human_contrast_score: 80, dog_contrast_score: 90, dog_contrast_gain: 40, contrast_change: 10, rank: 1, explanation: "Bright yellow has strong simulated separation." },
    { color_id: "blue", label: "Bright blue", human_color: "#2F6BFF", dog_approx_color: "#596CD7", human_contrast_score: 70, dog_contrast_score: 50, dog_contrast_gain: 0, contrast_change: -20, rank: 2, explanation: "Bright blue has moderate simulated separation." },
  ],
  disclaimer: "Screen-color simulation using a fixed palette and the measured nearby background. It is not exact canine vision, object segmentation, or a physical-product guarantee.",
};

const createObjectURL = vi.fn((file: File) => `blob:${file.name}`);
const revokeObjectURL = vi.fn();

beforeEach(() => {
  vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("ToyColorLab", () => {
  it("explains why color comparison is unavailable", () => {
    const onSimulate = vi.fn();
    render(
      <ToyColorLab
        clip={clip}
        event={event}
        result={null}
        isLoading={false}
        error={null}
        disabled
        disabledReason="Calculate visibility first."
        onSimulate={onSimulate}
      />,
    );
    const button = screen.getByRole("button", { name: "Compare six colors" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Calculate visibility first.")).toBeDefined();
    fireEvent.click(button);
    expect(onSimulate).not.toHaveBeenCalled();
  });

  it("shows original and candidate scores without mutating the event", () => {
    const originalEvent = structuredClone(event);
    render(
      <ToyColorLab clip={clip} event={event} result={result} isLoading={false} error={null} disabled={false} onSimulate={vi.fn()} />,
    );
    expect(screen.getByText("Original sampled color")).toBeDefined();
    expect(screen.getByText("Original canine approximation")).toBeDefined();
    const yellow = screen.getByRole("button", { name: /Bright yellow/ });
    const blue = screen.getByRole("button", { name: /Bright blue/ });
    expect(yellow.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(blue);
    expect(blue.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Selected screen color")).toBeDefined();
    expect(screen.getByText("Original sampled color")).toBeDefined();
    expect(screen.queryByText("Original human color")).toBeNull();
    expect(screen.getByText(/Contrast gain: 0 points/)).toBeDefined();
    expect(event).toEqual(originalEvent);
  });

  it("replaces and revokes the preview URL when the clip changes", () => {
    const { rerender, unmount } = render(
      <ToyColorLab clip={clip} event={event} result={result} isLoading={false} error={null} disabled={false} onSimulate={vi.fn()} />,
    );
    const secondClip = {
      ...clip,
      file: new File(["portrait"], "portrait.mp4", { type: "video/mp4" }),
    };
    rerender(
      <ToyColorLab clip={secondClip} event={event} result={result} isLoading={false} error={null} disabled={false} onSimulate={vi.fn()} />,
    );
    expect(createObjectURL).toHaveBeenCalledTimes(2);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:clip.mp4");
    unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:portrait.mp4");
  });
});
