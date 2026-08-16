"use client";

import { useEffect, useState } from "react";

import type {
  StoryReelResult,
} from "../types/sceneAnalysis";

type StoryReelProps = {
  dogName: string;
  result: StoryReelResult | null;
  isRendering: boolean;
  error: string | null;
  disabled: boolean;
  onRender: () => void;
};

export function StoryReel({
  dogName,
  result,
  isRendering,
  error,
  disabled,
  onRender,
}: StoryReelProps) {
  const [videoUrl, setVideoUrl] = useState("");

  useEffect(() => {
    if (!result) {
      return;
    }

    const nextUrl = URL.createObjectURL(result.video);
    const updateId = window.setTimeout(() => {
      setVideoUrl(nextUrl);
    }, 0);

    return () => {
      window.clearTimeout(updateId);
      URL.revokeObjectURL(nextUrl);
    };
  }, [result]);

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
