import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { StoryReel } from "./StoryReel";

const createObjectURL = vi.fn(
  () => "blob:story-reel",
);
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

describe("StoryReel", () => {
  it("starts Story Reel generation", () => {
    const onRender = vi.fn();

    render(
      <StoryReel
        dogName="Bruno"
        result={null}
        isRendering={false}
        progress={0}
        error={null}
        disabled={false}
        onRender={onRender}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Create Story Reel",
      }),
    );

    expect(onRender).toHaveBeenCalledTimes(1);
  });

  it("shows Story Reel rendering progress", () => {
    const onRender = vi.fn();

    render(
      <StoryReel
        dogName="Bruno"
        result={null}
        isRendering={true}
        progress={65}
        error={null}
        disabled={false}
        onRender={onRender}
      />,
    );

    const progressBar = screen.getByRole(
      "progressbar",
      {
        name: "Story Reel progress",
      },
    );

    expect(
      progressBar.getAttribute("aria-valuenow"),
    ).toBe("65");

    expect(
      screen.getByText(
        "Composing the vertical reel…",
      ),
    ).toBeDefined();

    const button = screen.getByRole(
      "button",
      {
        name: "Creating Story Reel…",
      },
    ) as HTMLButtonElement;

    expect(button.disabled).toBe(true);
  });

  it(
    "previews, downloads, retries, and revokes the MP4 URL",
    async () => {
      const onRender = vi.fn();

      const result = {
        video: new Blob(["mp4"], {
          type: "video/mp4",
        }),
        source: "gemini" as const,
      };

      const rendered = render(
        <StoryReel
          dogName="Bruno"
          result={result}
          isRendering={false}
          progress={0}
          error={null}
          disabled={false}
          onRender={onRender}
        />,
      );

      await waitFor(() => {
        expect(
          createObjectURL,
        ).toHaveBeenCalledWith(result.video);

        expect(
          screen.getByText(
            "Download Story Reel",
          ),
        ).toBeDefined();
      });

      const download = screen.getByText(
        "Download Story Reel",
      ) as HTMLAnchorElement;

      expect(download.href).toContain(
        "blob:story-reel",
      );

      expect(download.download).toBe(
        "Bruno-pawspective-reel.mp4",
      );

      fireEvent.click(
        screen.getByRole("button", {
          name: "Render again",
        }),
      );

      expect(onRender).toHaveBeenCalledTimes(1);

      rendered.unmount();

      expect(
        revokeObjectURL,
      ).toHaveBeenCalledWith(
        "blob:story-reel",
      );
    },
  );

  it("shows a retryable safe error", () => {
    const onRender = vi.fn();

    render(
      <StoryReel
        dogName="Bruno"
        result={null}
        isRendering={false}
        progress={0}
        error="The fictional dog voice is unavailable."
        disabled={false}
        onRender={onRender}
      />,
    );

    expect(
      screen.getByRole("alert").textContent,
    ).toContain("fictional dog voice");

    expect(
      screen.getByRole("button", {
        name: "Create Story Reel",
      }),
    ).toBeDefined();
  });
});