import {
  cleanup,
  render,
  screen,
  within,
} from "@testing-library/react";
import {
  afterEach,
  describe,
  expect,
  it,
} from "vitest";

import type {
  SceneEvent,
  VisibilityScore,
} from "../types/sceneAnalysis";
import { VisibilityInsight } from "./VisibilityInsight";

const event: SceneEvent = {
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
};

const score: VisibilityScore = {
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
    "The transformed object/background contrast is high.",
  ],
};

afterEach(() => {
  cleanup();
});

describe("VisibilityInsight", () => {
  it("shows human and dog-visible contrast meters", () => {
    render(
      <VisibilityInsight
        event={event}
        score={score}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "blue ball",
      }),
    ).toBeDefined();

    const humanMeter = screen.getByRole("meter", {
      name: "Human-visible contrast",
    });

    const dogMeter = screen.getByRole("meter", {
      name: "Approximate dog-visible contrast",
    });

    expect(humanMeter.getAttribute("aria-valuenow")).toBe("70");
    expect(dogMeter.getAttribute("aria-valuenow")).toBe("84");

    expect(
      within(
        humanMeter.parentElement as HTMLElement,
      ).getByText("70/100"),
    ).toBeDefined();

    expect(
      within(
        dogMeter.parentElement as HTMLElement,
      ).getByText("84/100"),
    ).toBeDefined();
  });

  it("shows the scientific-accuracy disclaimer", () => {
    render(
      <VisibilityInsight
        event={event}
        score={score}
      />,
    );

    expect(
      screen.getByText(
        /relative PawSpective product score/i,
      ),
    ).toBeDefined();

    expect(
      screen.getByText(
        /not a probability or scientifically exact measure/i,
      ),
    ).toBeDefined();

    expect(
      screen.getByText("AI-inferred motion"),
    ).toBeDefined();
    expect(
      screen.getByText(
        /Motion is an AI-inferred scene label/i,
      ),
    ).toBeDefined();
  });

  it("shows an empty state before scoring", () => {
    render(
      <VisibilityInsight
        event={event}
        score={undefined}
      />,
    );

    expect(
      screen.getByText(
        /calculate visibility to see a deterministic comparison/i,
      ),
    ).toBeDefined();
  });
});
