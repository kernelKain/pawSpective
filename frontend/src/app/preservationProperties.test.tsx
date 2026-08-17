import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StoryReelSource } from "./types/sceneAnalysis";
import { StoryReel } from "./components/StoryReel";


const createObjectURL = vi.fn(() => "blob:preserved-story-reel");
const revokeObjectURL = vi.fn();

beforeEach(() => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL,
    revokeObjectURL,
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("Property 2: non-bug Story Reel presentation is preserved", () => {
  // **Validates: Requirements 3.6, 3.10**
  it.each([
    ["gemini", "Live grounded story"],
    ["template", "Grounded local story"],
  ] as const)(
    "keeps %s provenance distinct from scientific and entertainment disclosures",
    (source: StoryReelSource, expectedSource: string) => {
      const result = {
        video: new Blob(["rendered-mp4"], { type: "video/mp4" }),
        source,
        artifactSource: "live_render" as const,
        voiceSource: "elevenlabs" as const,
        variationId: "preservation-variation",
        animationSeed: 7,
        musicTrackId: "curious-steps" as const,
        visualSource: "gemini_omni" as const,
        visualModel: "gemini-omni-flash-preview",
      };

      const rendered = render(
        <StoryReel
          dogName="Bruno"
          result={result}
          isRendering={false}
          progress={100}
          error={null}
          disabled={false}
          animationProvider="gemini_omni"
          onAnimationProviderChange={vi.fn()}
          onRender={vi.fn()}
        />,
      );

      expect(screen.getByText(new RegExp(expectedSource))).toBeDefined();
      expect(screen.getByRole("note").textContent).toContain(
        "Playful entertainment based on AI-detected, user-reviewed objects",
      );
      expect(screen.getByRole("note").textContent).toContain(
        "not actual dog thoughts or exact canine vision",
      );
      expect(screen.getByText(/does not reconstruct exact canine sight/i)).toBeDefined();
      expect(screen.getByText("Download reel")).toBeDefined();
      expect(createObjectURL).toHaveBeenCalledWith(result.video);

      rendered.unmount();
      expect(revokeObjectURL).toHaveBeenCalledWith(
        "blob:preserved-story-reel",
      );
    },
  );
});
