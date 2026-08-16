"use client";

import { useEffect, useMemo } from "react";

import type {
  StoryReelResult,
} from "../types/sceneAnalysis";

type StoryReelProps = {
  dogName: string;
  result: StoryReelResult | null;
  isRendering: boolean;
  progress: number;
  error: string | null;
  disabled: boolean;
  onRender: () => void;
};

export function StoryReel({
  dogName,
  result,
  isRendering,
  progress,
  error,
  disabled,
  onRender,
}: StoryReelProps) {

  const videoUrl = useMemo(
    () =>
      result
        ? URL.createObjectURL(result.video)
        : "",
    [result],
  );

  useEffect(() => {
    if (!videoUrl) {
      return;
    }

    return () => {
      URL.revokeObjectURL(videoUrl);
    };
  }, [videoUrl]);

  return (
    <div className="story-reel">
      {!result && (
        <div className="story-reel-empty">
          <p>
            Turn the corrected scene into a narrated,
            downloadable vertical video.
          </p>

          <button
            className="primary-button"
            type="button"
            disabled={disabled || isRendering}
            onClick={onRender}
          >
            {isRendering
              ? "Creating Story Reel…"
              : "Create Story Reel"}
          </button>
        </div>
      )}

      {isRendering && (
        <div className="story-progress">
          <div
            className="story-progress-track"
            role="progressbar"
            aria-label="Story Reel progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress}
          >
            <span
              style={{
                width: `${Math.max(4, progress)}%`,
              }}
            />
          </div>

          <p>
            {progress < 30
              ? "Preparing the video…"
              : progress < 50
                ? "Writing the grounded story…"
                : progress < 65
                  ? "Creating the fictional voice…"
                  : "Composing the vertical reel…"}
          </p>
        </div>
      )}

      {result && videoUrl && (
        <>
          <video
            className="story-reel-video"
            src={videoUrl}
            controls
            playsInline
          />

          <div className="story-reel-actions">
            <p>
              {result.source === "gemini"
                ? "Gemini-grounded fictional narration"
                : "Safe template narration was used"}
              {" · "}
              ElevenLabs fictional dog voice
            </p>

            <a
              className="primary-button download-button"
              href={videoUrl}
              download={`${dogName || "dog"}-pawspective-reel.mp4`}
            >
              Download Story Reel
            </a>

            <button
              className="secondary-button"
              type="button"
              disabled={isRendering}
              onClick={onRender}
            >
              Render again
            </button>
          </div>
        </>
      )}

      {error && (
        <div className="analysis-error" role="alert">
          {error}
        </div>
      )}

      <p className="phase-note">
        Just for fun · fictional voice · based only on
        corrected visible events · no gaze, thought,
        emotion, or scent detection
      </p>
    </div>
  );
}
