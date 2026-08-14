import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { describeCameraError, useCamera } from "./useCamera";

const originalMediaDevices = Object.getOwnPropertyDescriptor(
  navigator,
  "mediaDevices",
);

afterEach(() => {
  if (originalMediaDevices) {
    Object.defineProperty(
      navigator,
      "mediaDevices",
      originalMediaDevices,
    );
  } else {
    Reflect.deleteProperty(navigator, "mediaDevices");
  }
});

describe("describeCameraError", () => {
  it.each([
    ["NotAllowedError", "denied"],
    ["SecurityError", "denied"],
    ["NotFoundError", "unavailable"],
    ["OverconstrainedError", "unavailable"],
    ["NotReadableError", "error"],
    ["AbortError", "error"],
  ] as const)("maps %s to %s", (name, expectedStatus) => {
    const result = describeCameraError(
      new DOMException("Camera test error", name),
    );

    expect(result.status).toBe(expectedStatus);
    expect(result.message).not.toHaveLength(0);
  });

  it("maps non-DOM errors to a retryable error", () => {
    expect(describeCameraError(new Error("Unexpected"))).toEqual({
      status: "error",
      message: "The camera could not be started. Please try again.",
    });
  });
});

describe("useCamera", () => {
  it("stops every active media track when the hook unmounts", async () => {
    const stopTrack = vi.fn();
    const stream = {
      getTracks: () => [{ stop: stopTrack }],
    } as unknown as MediaStream;
    const getUserMedia = vi.fn().mockResolvedValue(stream);

    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });

    const video = document.createElement("video");
    Object.defineProperty(video, "readyState", {
      configurable: true,
      value: HTMLMediaElement.HAVE_METADATA,
    });
    Object.defineProperty(video, "play", {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    });
    Object.defineProperty(video, "srcObject", {
      configurable: true,
      writable: true,
      value: null,
    });

    const { result, unmount } = renderHook(() => useCamera());
    (result.current.videoRef as { current: HTMLVideoElement | null }).current =
      video;

    await act(async () => {
      await result.current.startCamera("environment");
    });

    expect(result.current.status).toBe("ready");
    expect(getUserMedia).toHaveBeenCalledOnce();
    expect(stopTrack).not.toHaveBeenCalled();

    unmount();

    expect(stopTrack).toHaveBeenCalledOnce();
    expect(video.srcObject).toBeNull();
  });
});
