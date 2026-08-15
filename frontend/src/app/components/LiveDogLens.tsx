"use client";

import { useEffect, useRef, useState } from "react";

import { useCamera } from "../hooks/useCamera";
import {
  createCanineVisionRenderer,
  type CanineVisionRenderer,
} from "../lib/canineVisionRenderer";
import type { CapturedClip } from "../types/sceneAnalysis";
import { CapturePanel } from "./CapturePanel";

type LiveDogLensProps = {
  visionMix: number;
  onVisionMixChange: (value: number) => void;
  onClipChange: (clip: CapturedClip | null) => void;
  onRecordingChange?: (recording: boolean) => void;
};

export function LiveDogLens({
  visionMix,
  onVisionMixChange,
  onClipChange,
  onRecordingChange = () => undefined,
}: LiveDogLensProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rendererRef = useRef<CanineVisionRenderer | null>(null);

  const [detailReduction, setDetailReduction] = useState(12);
  const [recording, setRecording] = useState(false);
  const [rendererError, setRendererError] = useState<string | null>(
    null,
  );

  const {
    videoRef,
    status,
    errorMessage,
    facingMode,
    startCamera,
    switchCamera,
    stopCamera,
    getStream,
  } = useCamera();

  useEffect(() => {
    if (
      status !== "ready" ||
      !canvasRef.current ||
      !videoRef.current
    ) {
      return;
    }

    let renderer: CanineVisionRenderer | null = null;
    let active = true;

    try {
      renderer = createCanineVisionRenderer(
        canvasRef.current,
        videoRef.current,
      );

      renderer.start();

      rendererRef.current = renderer;
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "The Dog Vision renderer could not be started.";

      queueMicrotask(() => {
        if (active) {
          setRendererError(message);
        }
      });
    }

    return () => {
      active = false;
      renderer?.destroy();

      if (rendererRef.current === renderer) {
        rendererRef.current = null;
      }
    };
  }, [status, videoRef]);

  useEffect(() => {
    if (status === "ready") {
      rendererRef.current?.setMix(visionMix / 100);
    }
  }, [status, visionMix]);

  useEffect(() => {
    if (status === "ready") {
      rendererRef.current?.setDetailReduction(
        detailReduction / 100,
      );
    }
  }, [status, detailReduction]);

  useEffect(() => {
    if (status === "ready") {
      rendererRef.current?.setMirror(facingMode === "user");
    }
  }, [status, facingMode]);

  const cameraMessage =
    status === "requesting"
      ? "Waiting for camera permission…"
      : status === "idle"
        ? "Enable your camera to open the live Dog Lens."
        : errorMessage;

  const startButtonLabel =
    status === "idle" ? "Enable camera" : "Try camera again";

  function handleStartCamera() {
    setRendererError(null);
    void startCamera("environment");
  }

  function handleSwitchCamera() {
    setRendererError(null);
    void switchCamera();
  }

  function handleStopCamera() {
    setRendererError(null);
    stopCamera();
  }

  function handleRecordingChange(nextRecording: boolean) {
    setRecording(nextRecording);
    onRecordingChange(nextRecording);
  }

  return (
    <div className="camera-card">
      <div className="camera-labels">
        <span>Live camera</span>
        <span className="camera-status-pill">
          Canine vision approximation
        </span>
      </div>

      <div className="live-camera-frame">
        <video
          ref={videoRef}
          className="camera-video-source"
          autoPlay
          muted
          playsInline
          aria-hidden="true"
        />

        <canvas
          ref={canvasRef}
          className="live-camera-canvas"
          role="img"
          aria-label="Live camera with the Dog Vision approximation"
        />

        {status !== "ready" && (
          <div className="camera-permission-state">
            <div className="camera-state-icon" aria-hidden="true">
              ◉
            </div>

            <h3>Open the Dog Lens</h3>

            <p
              className={
                status === "denied" ||
                status === "unavailable" ||
                status === "error"
                  ? "camera-error"
                  : undefined
              }
            >
              {cameraMessage}
            </p>

            <button
              className="primary-button"
              type="button"
              disabled={status === "requesting"}
              onClick={handleStartCamera}
            >
              {status === "requesting"
                ? "Starting camera…"
                : startButtonLabel}
            </button>
          </div>
        )}

        {status === "ready" && (
          <>
            <div className="camera-actions">
              <button
                className="camera-control-button"
                type="button"
                disabled={recording}
                onClick={handleSwitchCamera}
              >
                Switch camera
              </button>

              <button
                className="camera-control-button"
                type="button"
                disabled={recording}
                onClick={handleStopCamera}
              >
                Stop
              </button>
            </div>

            <div className="alignment-guide" aria-hidden="true">
              <span>+</span>
              <small>Approximate head-facing direction</small>
            </div>
          </>
        )}

        {rendererError && (
          <div className="camera-permission-state camera-renderer-error">
            <h3>Dog Lens unavailable</h3>
            <p className="camera-error">{rendererError}</p>

            <button
              className="secondary-button"
              type="button"
              onClick={handleStopCamera}
            >
              Close camera
            </button>
          </div>
        )}
      </div>

      <div className="comparison-control">
        <span>Human view</span>

        <input
          aria-label="Human and dog vision comparison"
          type="range"
          min="0"
          max="100"
          value={visionMix}
          onChange={(event) =>
            onVisionMixChange(Number(event.target.value))
          }
        />

        <span>Dog Vision</span>
      </div>

      <div className="detail-control">
        <div>
          <strong>Detail reduction</strong>
          <span>{detailReduction}%</span>
        </div>

        <input
          aria-label="Dog vision detail reduction"
          type="range"
          min="0"
          max="35"
          value={detailReduction}
          onChange={(event) =>
            setDetailReduction(Number(event.target.value))
          }
        />

        <p>
          Adds a subtle softening effect. Keep it low because visual
          acuity differs between individual dogs.
        </p>
      </div>

      <p className="science-note">
        This display approximates reduced red/green separation. It is
        educational, not a diagnostic or exact reconstruction of what
        every dog sees.
      </p>

      <CapturePanel
        cameraReady={status === "ready"}
        getStream={getStream}
        onClipChange={onClipChange}
        onRecordingChange={handleRecordingChange}
      />
    </div>
  );
}
