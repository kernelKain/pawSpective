"use client";

import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";

import type { CapturedClip } from "../types/sceneAnalysis";

const MINIMUM_DURATION_MS = 5_000;
const MAXIMUM_DURATION_MS = 10_000;
const MAXIMUM_FILE_BYTES = 30 * 1024 * 1024;

type CapturePanelProps = {
  cameraReady: boolean;
  getStream: () => MediaStream | null;
  onClipChange: (clip: CapturedClip | null) => void;
};

function preferredMimeType(): string | undefined {
  const candidates = [
    "video/webm;codecs=vp9",
    "video/webm;codecs=vp8",
    "video/mp4;codecs=avc1",
    "video/webm",
    "video/mp4",
  ];

  return candidates.find((candidate) =>
    MediaRecorder.isTypeSupported(candidate),
  );
}

function extensionForMimeType(mimeType: string): string {
  return mimeType.includes("mp4") ? "mp4" : "webm";
}

function readVideoDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const video = document.createElement("video");
    const url = URL.createObjectURL(file);

    video.preload = "metadata";

    video.onloadedmetadata = () => {
      const durationMs = Math.round(video.duration * 1000);
      URL.revokeObjectURL(url);

      if (!Number.isFinite(durationMs)) {
        reject(new Error("The video duration could not be read."));
        return;
      }

      resolve(durationMs);
    };

    video.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("The selected video could not be read."));
    };

    video.src = url;
  });
}

export function CapturePanel({
  cameraReady,
  getStream,
  onClipChange,
}: CapturePanelProps) {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const intervalRef = useRef<number | null>(null);
  const stopTimerRef = useRef<number | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  const [recording, setRecording] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [clip, setClip] = useState<CapturedClip | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  function clearTimers() {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (stopTimerRef.current !== null) {
      window.clearTimeout(stopTimerRef.current);
      stopTimerRef.current = null;
    }
  }

  function publishClip(nextClip: CapturedClip) {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
    }

    const nextUrl = URL.createObjectURL(nextClip.file);
    previewUrlRef.current = nextUrl;

    setPreviewUrl(nextUrl);
    setClip(nextClip);
    onClipChange(nextClip);
  }

  function resetClip() {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }

    setPreviewUrl("");
    setClip(null);
    setErrorMessage("");
    onClipChange(null);
  }

  function stopRecording() {
    const recorder = recorderRef.current;

    if (recorder?.state === "recording") {
      recorder.stop();
    }
  }

  function startRecording() {
    setErrorMessage("");

    if (!window.MediaRecorder) {
      setErrorMessage(
        "This browser does not support video recording.",
      );
      return;
    }

    const stream = getStream();

    if (!stream) {
      setErrorMessage("Enable the camera before recording.");
      return;
    }

    resetClip();

    const mimeType = preferredMimeType();
    const recorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream);

    recorderRef.current = recorder;
    chunksRef.current = [];
    startedAtRef.current = performance.now();

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data);
      }
    };

    recorder.onerror = () => {
      clearTimers();
      setRecording(false);
      setErrorMessage("Recording failed. Please try again.");
    };

    recorder.onstop = () => {
      clearTimers();
      setRecording(false);

      const durationMs = Math.min(
        Math.round(performance.now() - startedAtRef.current),
        MAXIMUM_DURATION_MS,
      );

      const outputType =
        recorder.mimeType || mimeType || "video/webm";

      const blob = new Blob(chunksRef.current, {
        type: outputType,
      });

      if (blob.size === 0) {
        setErrorMessage("The recording did not contain video.");
        return;
      }

      const extension = extensionForMimeType(outputType);

      const file = new File(
        [blob],
        `pawspective-${Date.now()}.${extension}`,
        { type: outputType },
      );

      publishClip({
        file,
        durationMs,
        source: "recording",
      });
    };

    recorder.start(500);
    setRecording(true);
    setElapsedMs(0);

    intervalRef.current = window.setInterval(() => {
      setElapsedMs(
        Math.min(
          performance.now() - startedAtRef.current,
          MAXIMUM_DURATION_MS,
        ),
      );
    }, 100);

    stopTimerRef.current = window.setTimeout(
      stopRecording,
      MAXIMUM_DURATION_MS,
    );
  }

  async function handleUpload(
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) return;

    resetClip();

    if (
      ![
        "video/mp4",
        "video/webm",
        "video/quicktime",
        "video/x-matroska",
      ].includes(file.type)
    ) {
      setErrorMessage(
        "Choose an MP4, WebM, MOV, or MKV video.",
      );
      return;
    }

    if (file.size > MAXIMUM_FILE_BYTES) {
      setErrorMessage("The maximum file size is 30 MB.");
      return;
    }

    try {
      const durationMs = await readVideoDuration(file);

      if (durationMs < MINIMUM_DURATION_MS) {
        setErrorMessage("Choose a clip of at least five seconds.");
        return;
      }

      if (durationMs > 15_000) {
        setErrorMessage("The maximum duration is 15 seconds.");
        return;
      }

      publishClip({
        file,
        durationMs,
        source: "upload",
      });
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "The video could not be loaded.",
      );
    }
  }

  useEffect(() => {
    return () => {
      clearTimers();

      if (recorderRef.current?.state === "recording") {
        recorderRef.current.stop();
      }

      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
    };
  }, []);

  const clipIsUsable =
    clip !== null &&
    clip.durationMs >= MINIMUM_DURATION_MS &&
    clip.durationMs <= 15_000;

  return (
    <section className="capture-panel">
      <div className="capture-heading">
        <div>
          <strong>Capture a moment</strong>
          <p>Record 5–10 seconds or upload a short clip.</p>
        </div>

        {recording && (
          <span className="recording-indicator">
            ● {(elapsedMs / 1000).toFixed(1)}s
          </span>
        )}
      </div>

      <div className="capture-actions">
        {!recording ? (
          <button
            className="primary-button"
            type="button"
            disabled={!cameraReady}
            onClick={startRecording}
          >
            Record up to 10 seconds
          </button>
        ) : (
          <button
            className="secondary-button"
            type="button"
            disabled={elapsedMs < MINIMUM_DURATION_MS}
            onClick={stopRecording}
          >
            Stop recording
          </button>
        )}

        <label className="secondary-button upload-button">
          Upload clip
          <input
            type="file"
            accept="video/mp4,video/webm,video/quicktime,video/x-matroska"
            onChange={(event) => void handleUpload(event)}
          />
        </label>
      </div>

      {previewUrl && (
        <div className="clip-preview">
          <video
            src={previewUrl}
            controls
            muted
            playsInline
          />

          <div>
            <span>
              {(clip!.durationMs / 1000).toFixed(1)} seconds
            </span>

            <button
              type="button"
              className="text-button"
              onClick={resetClip}
            >
              Remove
            </button>
          </div>
        </div>
      )}

      {clipIsUsable && (
        <p className="capture-ready">
          ✓ Clip ready for scene analysis
        </p>
      )}

      {errorMessage && (
        <p className="capture-error">{errorMessage}</p>
      )}
    </section>
  );
}