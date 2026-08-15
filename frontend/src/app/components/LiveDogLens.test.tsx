import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { useState, type RefObject } from "react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  useCamera,
  type CameraStatus,
  type FacingMode,
} from "../hooks/useCamera";
import {
  createCanineVisionRenderer,
  type CanineVisionRenderer,
} from "../lib/canineVisionRenderer";
import { LiveDogLens } from "./LiveDogLens";

vi.mock("../hooks/useCamera");
vi.mock("../lib/canineVisionRenderer");

const mockedUseCamera = vi.mocked(useCamera);
const mockedCreateRenderer = vi.mocked(createCanineVisionRenderer);

let cameraStatus: CameraStatus;
let facingMode: FacingMode;
let renderers: CanineVisionRenderer[];

const videoRef = {
  current: null,
} as RefObject<HTMLVideoElement | null>;
const startCamera = vi.fn(async () => undefined);
const switchCamera = vi.fn(async () => undefined);
const stopCamera = vi.fn();
const getStream = vi.fn((): MediaStream | null => null);
const onClipChange = vi.fn();

function createRendererMock(): CanineVisionRenderer {
  return {
    start: vi.fn(),
    stop: vi.fn(),
    destroy: vi.fn(),
    setMix: vi.fn(),
    setDetailReduction: vi.fn(),
    setMirror: vi.fn(),
  };
}

function LensHarness() {
  const [visionMix, setVisionMix] = useState(72);

  return (
    <LiveDogLens
      visionMix={visionMix}
      onVisionMixChange={setVisionMix}
      onClipChange={onClipChange}
    />
  );
}

beforeEach(() => {
  cameraStatus = "idle";
  facingMode = "environment";
  renderers = [];
  videoRef.current = null;

  mockedUseCamera.mockImplementation(() => ({
    videoRef,
    status: cameraStatus,
    errorMessage: null,
    facingMode,
    startCamera,
    switchCamera,
    stopCamera,
    getStream,
  }));

  mockedCreateRenderer.mockImplementation(() => {
    const renderer = createRendererMock();
    renderers.push(renderer);
    return renderer;
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("LiveDogLens", () => {
  it("reapplies current controls to a renderer after camera restart", () => {
    const { rerender } = render(<LensHarness />);

    cameraStatus = "ready";
    rerender(<LensHarness />);

    expect(renderers).toHaveLength(1);

    fireEvent.change(
      screen.getByRole("slider", {
        name: "Human and dog vision comparison",
      }),
      { target: { value: "20" } },
    );
    fireEvent.change(
      screen.getByRole("slider", {
        name: "Dog vision detail reduction",
      }),
      { target: { value: "25" } },
    );

    cameraStatus = "idle";
    rerender(<LensHarness />);
    cameraStatus = "ready";
    rerender(<LensHarness />);

    expect(renderers).toHaveLength(2);
    expect(renderers[1].setMix).toHaveBeenLastCalledWith(0.2);
    expect(
      renderers[1].setDetailReduction,
    ).toHaveBeenLastCalledWith(0.25);
    expect(renderers[1].setMirror).toHaveBeenLastCalledWith(false);
  });

  it("mirrors the renderer when the active camera faces the user", () => {
    const { rerender } = render(<LensHarness />);

    cameraStatus = "ready";
    facingMode = "user";
    rerender(<LensHarness />);

    expect(renderers[0].setMirror).toHaveBeenLastCalledWith(true);
  });

  it("uses existing button styles and renders the supported guide", () => {
    const { rerender } = render(<LensHarness />);

    expect(
      screen.getByRole("button", { name: "Enable camera" }).className,
    ).toContain("primary-button");

    cameraStatus = "ready";
    rerender(<LensHarness />);

    expect(
      screen.getByText("Approximate head-facing direction"),
    ).toBeDefined();
    expect(
      document.querySelector(".alignment-guide")?.textContent,
    ).toContain("+");
  });

  it("uses the existing secondary style for renderer recovery", async () => {
    mockedCreateRenderer.mockImplementationOnce(() => {
      throw new Error("WebGL unavailable");
    });

    cameraStatus = "ready";
    render(<LensHarness />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(
      screen.getByRole("button", { name: "Close camera" }).className,
    ).toContain("secondary-button");
  });
});
