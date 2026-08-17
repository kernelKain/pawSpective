import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StoryReel } from "./StoryReel";

const createObjectURL = vi.fn(() => "blob:story-reel");
const revokeObjectURL = vi.fn();

beforeEach(() => {
  vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("StoryReel", () => {
  it("starts animated Story Reel generation and labels the fiction", () => {
    const onRender = vi.fn();
    render(
      <StoryReel
        dogName="Bruno"
        result={null}
        isRendering={false}
        progress={0}
        error={null}
        disabled={false}
        animationProvider="gemini_omni"
        onAnimationProviderChange={vi.fn()}
        onRender={onRender}
      />,
    );

    expect(screen.getByText("Fictional dog narration")).toBeDefined();
    expect(screen.getByText(/not actual dog thoughts/i)).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Create animated reel" }));
    expect(onRender).toHaveBeenCalledTimes(1);
  });

  it("shows accessible, stage-specific rendering progress", () => {
    render(
      <StoryReel
        dogName="Bruno"
        result={null}
        isRendering
        progress={65}
        error={null}
        disabled={false}
        animationProvider="gemini_omni"
        onAnimationProviderChange={vi.fn()}
        onRender={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("progressbar", { name: "Story Reel progress" }).getAttribute("aria-valuenow"),
    ).toBe("65");
    expect(screen.getByText("Generating the animated dog-POV scene…")).toBeDefined();
    expect(
      (screen.getByRole("button", { name: "Creating animated reel…" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("previews, downloads, rerenders, and revokes the MP4 URL", async () => {
    const onRender = vi.fn();
    const result = {
      video: new Blob(["mp4"], { type: "video/mp4" }),
      source: "gemini" as const,
      artifactSource: "live_render" as const,
      voiceSource: "elevenlabs" as const,
      variationId: "variation-123456",
      animationSeed: 42,
      musicTrackId: "sunny-paws" as const,
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
        onRender={onRender}
      />,
    );

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledWith(result.video));
    const download = screen.getByText("Download reel") as HTMLAnchorElement;
    expect(download.href).toContain("blob:story-reel");
    expect(download.download).toBe("Bruno-pawspective-reel.mp4");
    expect(screen.getByText(/Variation variatio/)).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Render again" }));
    expect(onRender).toHaveBeenCalledTimes(1);
    rendered.unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:story-reel");
  });

  it("clearly labels cached output and shows a safe retry", () => {
    const { rerender } = render(
      <StoryReel
        dogName="Bruno"
        result={{
          video: new Blob(["cached"]),
          source: "demo_cache",
          artifactSource: "controlled_demo_cache",
          voiceSource: "controlled_demo_cache",
          variationId: "original",
          animationSeed: 0,
          musicTrackId: "sunny-paws",
          visualSource: "controlled_demo_cache",
          visualModel: null,
        }}
        isRendering={false}
        progress={100}
        error={null}
        disabled={false}
        animationProvider="gemini_omni"
        onAnimationProviderChange={vi.fn()}
        onRender={vi.fn()}
      />,
    );
    expect(screen.getByText(/verified original demo reel/i)).toBeDefined();

    rerender(
      <StoryReel
        dogName="Bruno"
        result={null}
        isRendering={false}
        progress={0}
        error="The fictional voice is temporarily unavailable."
        disabled={false}
        animationProvider="gemini_omni"
        onAnimationProviderChange={vi.fn()}
        onRender={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert").textContent).not.toMatch(/[A-Z]:\\|api[_-]?key/i);
    expect(screen.getByRole("button", { name: "Create animated reel" })).toBeDefined();
  });
});
