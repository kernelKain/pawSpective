import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import type { CapturedClip } from "../types/sceneAnalysis";
import { CapturePanel } from "./CapturePanel";


let recorderInstances: FakeMediaRecorder[];
let failConstruction: boolean;
let failStart: boolean;

class FakeMediaRecorder {
  static isTypeSupported(mimeType: string) {
    return mimeType === "video/webm;codecs=vp9";
  }

  state: RecordingState = "inactive";
  mimeType: string;
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onstop: ((event: Event) => void) | null = null;

  constructor(_stream: MediaStream, options?: MediaRecorderOptions) {
    if (failConstruction) {
      throw new DOMException("unsupported", "NotSupportedError");
    }

    this.mimeType = options?.mimeType ?? "video/webm";
    recorderInstances.push(this);
  }

  start() {
    if (failStart) {
      throw new DOMException("failed", "InvalidStateError");
    }

    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.(
      new BlobEvent("dataavailable", {
        data: new Blob(["recorded-video"], {
          type: this.mimeType,
        }),
      }),
    );
    this.onstop?.(new Event("stop"));
  }
}

const stream = {} as MediaStream;
const getStream = vi.fn(() => stream);
const onClipChange = vi.fn<(clip: CapturedClip | null) => void>();
const onRecordingChange = vi.fn<(recording: boolean) => void>();

beforeEach(() => {
  recorderInstances = [];
  failConstruction = false;
  failStart = false;
  vi.useFakeTimers();
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:preview"),
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function renderPanel() {
  return render(
    <CapturePanel
      cameraReady
      getStream={getStream}
      onClipChange={onClipChange}
      onRecordingChange={onRecordingChange}
    />,
  );
}

describe("CapturePanel", () => {
  it("records a usable clip with a backend-safe base MIME type", () => {
    renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: "Record up to 10 seconds" }),
    );

    expect(onRecordingChange).toHaveBeenLastCalledWith(true);
    expect(
      (screen.getByLabelText("Upload clip") as HTMLInputElement).disabled,
    ).toBe(true);

    act(() => {
      vi.advanceTimersByTime(5_100);
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Stop recording" }),
    );

    const lastCall = onClipChange.mock.calls.at(-1);
    const clip = lastCall?.[0];

    expect(clip?.source).toBe("recording");
    expect(clip?.file.type).toBe("video/webm");
    expect(clip?.durationMs).toBeGreaterThanOrEqual(5_000);
    expect(onRecordingChange).toHaveBeenLastCalledWith(false);
    expect(screen.getByText("✓ Clip ready for scene analysis")).toBeDefined();
  });

  it("shows a controlled error when MediaRecorder construction fails", () => {
    failConstruction = true;
    renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: "Record up to 10 seconds" }),
    );

    expect(
      screen.getByText(
        "Video recording could not be started in this browser.",
      ),
    ).toBeDefined();
    expect(onRecordingChange).not.toHaveBeenCalledWith(true);
  });

  it("shows a controlled error when MediaRecorder start fails", () => {
    failStart = true;
    renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: "Record up to 10 seconds" }),
    );

    expect(
      screen.getByText(
        "Video recording could not be started in this browser.",
      ),
    ).toBeDefined();
    expect(onRecordingChange).not.toHaveBeenCalledWith(true);
  });

  it("detaches recorder callbacks before unmount cleanup", () => {
    const { unmount } = renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: "Record up to 10 seconds" }),
    );

    expect(onClipChange).toHaveBeenCalledTimes(1);
    unmount();

    expect(recorderInstances[0].state).toBe("inactive");
    expect(onClipChange).toHaveBeenCalledTimes(1);
  });

  it("stops a failed recorder without publishing a partial clip", () => {
    renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: "Record up to 10 seconds" }),
    );
    act(() => {
      recorderInstances[0].onerror?.(new Event("error"));
    });

    expect(recorderInstances[0].state).toBe("inactive");
    expect(onRecordingChange).toHaveBeenLastCalledWith(false);
    expect(onClipChange).toHaveBeenCalledTimes(1);
    expect(
      screen.getByText("Recording failed. Please try again."),
    ).toBeDefined();
  });

  it("rejects unsupported and oversized uploads before reading metadata", () => {
    renderPanel();
    const upload = screen.getByLabelText("Upload clip");

    fireEvent.change(upload, {
      target: {
        files: [new File(["text"], "clip.txt", { type: "text/plain" })],
      },
    });

    expect(
      screen.getByText("Choose an MP4, WebM, MOV, or MKV video."),
    ).toBeDefined();

    const oversized = new File(["video"], "clip.mp4", {
      type: "video/mp4",
    });
    Object.defineProperty(oversized, "size", {
      value: 30 * 1024 * 1024 + 1,
    });

    fireEvent.change(upload, { target: { files: [oversized] } });

    expect(
      screen.getByText("The maximum file size is 30 MB."),
    ).toBeDefined();
  });
});
