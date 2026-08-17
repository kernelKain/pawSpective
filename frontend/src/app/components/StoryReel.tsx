"use client";

import { useEffect, useMemo } from "react";

import type { StoryReelResult } from "../types/sceneAnalysis";

type StoryReelProps = {
  dogName: string;
  result: StoryReelResult | null;
  isRendering: boolean;
  progress: number;
  error: string | null;
  disabled: boolean;
  disabledReason?: string;
  onRender: () => void;
};

function progressMessage(progress: number) {
  if (progress < 20) return "Checking the clip and scene…";
  if (progress < 45) return "Writing a grounded dog-POV story…";
  if (progress < 65) return "Creating the fictional narration…";
  if (progress < 90) return "Drawing frames and mixing quiet music…";
  return "Finishing your reel…";
}

const musicLabels = {
  "sunny-paws": "Sunny Paws",
  "curious-steps": "Curious Steps",
  "cozy-walk": "Cozy Walk",
};

export function StoryReel({
  dogName,
  result,
  isRendering,
  progress,
  error,
  disabled,
  disabledReason,
  onRender,
}: StoryReelProps) {
  const videoUrl = useMemo(
    () => (result ? URL.createObjectURL(result.video) : ""),
    [result],
  );

  useEffect(() => {
    if (!videoUrl) return;
    return () => URL.revokeObjectURL(videoUrl);
  }, [videoUrl]);

  return (
    <div className="story-reel">
      <div className="story-disclosure" role="note">
        <strong>Fictional dog narration</strong>
        <span>
          Playful entertainment based on AI-detected, user-reviewed objects—not
          actual dog thoughts or exact canine vision.
        </span>
      </div>

      {!result && (
        <div className="story-reel-empty">
          <p>
            Transform the original action into a warm, text-free animated sketch
            with first-person narration and quiet instrumental music.
          </p>
          <button
            className="primary-button"
            type="button"
            disabled={disabled || isRendering}
            onClick={onRender}
            aria-describedby={disabled && disabledReason ? "story-disabled-reason" : undefined}
          >
            {isRendering ? "Creating animated reel…" : "Create animated reel"}
          </button>
          {disabled && disabledReason && (
            <p className="action-hint" id="story-disabled-reason">
              {disabledReason}
            </p>
          )}
        </div>
      )}

      {isRendering && (
        <div className="story-progress" aria-live="polite">
          <div
            className="story-progress-track"
            role="progressbar"
            aria-label="Story Reel progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress}
          >
            <span style={{ width: `${Math.max(4, progress)}%` }} />
          </div>
          <p>{progressMessage(progress)}</p>
          <small>Keep this page open; leaving cancels the render and removes its files.</small>
        </div>
      )}

      {result && videoUrl && (
        <>
          <video
            className="story-reel-video"
            src={videoUrl}
            controls
            playsInline
            preload="metadata"
            aria-label={`${dogName || "Your dog"}'s animated Story Reel`}
          />
          <div className="story-reel-actions">
            <p>
              {result.source === "gemini"
                ? "Live grounded story"
                : result.source === "demo_cache"
                  ? "Verified original demo reel"
                  : "Grounded local story"}
              {` · Variation ${result.variationId.slice(0, 8)}`}
              {` · ${musicLabels[result.musicTrackId]}`}
              {result.voiceSource === "controlled_demo_cache"
                ? " · Saved demo narration"
                : " · ElevenLabs narration"}
            </p>
            <a
              className="primary-button download-button"
              href={videoUrl}
              download={`${dogName || "dog"}-pawspective-reel.mp4`}
            >
              Download reel
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
          <strong>We couldn&apos;t finish this reel.</strong> {error} You can retry,
          or use the controlled demo if your connection is unreliable.
        </div>
      )}

      <p className="context-note">
        The sketch preserves recorded scene evidence and uses a canine-color
        approximation. It does not reconstruct exactly what a dog sees.
      </p>
    </div>
  );
}
