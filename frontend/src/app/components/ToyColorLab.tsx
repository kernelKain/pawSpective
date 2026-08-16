"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";

import type {
  CapturedClip,
  ColorSimulationResponse,
  SceneEvent,
  ToyColorId,
} from "../types/sceneAnalysis";

type ToyColorLabProps = {
  clip: CapturedClip;
  event: SceneEvent;
  result: ColorSimulationResponse | null;
  isLoading: boolean;
  error: string | null;
  disabled: boolean;
  onSimulate: () => void;
};

export function ToyColorLab({
  clip,
  event,
  result,
  isLoading,
  error,
  disabled,
  onSimulate,
}: ToyColorLabProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [videoUrl] = useState(() => URL.createObjectURL(clip.file));
  const [aspectRatio, setAspectRatio] = useState("16 / 9");
  const [selection, setSelection] = useState<{
    eventId: string;
    colorId: ToyColorId;
  } | null>(null);

  useEffect(() => {
    return () => URL.revokeObjectURL(videoUrl);
  }, [videoUrl]);

  const selectedColorId =
    result &&
    selection?.eventId === result.event_id &&
    result.options.some((option) => option.color_id === selection.colorId)
      ? selection.colorId
      : (result?.recommended_color_id ?? null);

  const selectedOption = useMemo(
    () =>
      result?.options.find(
        (option) => option.color_id === selectedColorId,
      ) ?? null,
    [result, selectedColorId],
  );

  const box = event.bounding_box;
  const overlayStyle: CSSProperties = {
    left: `${box.x_min * 100}%`,
    top: `${box.y_min * 100}%`,
    width: `${(box.x_max - box.x_min) * 100}%`,
    height: `${(box.y_max - box.y_min) * 100}%`,
    backgroundColor: selectedOption?.human_color ?? "transparent",
  };

  return (
    <div className="toy-color-lab">
      {!result && (
        <div className="color-lab-intro">
          <p>
            Compare a fixed screen-color palette against the measured
            background around <strong>{event.object_label}</strong>.
          </p>
          <button
            className="primary-button"
            type="button"
            disabled={disabled || isLoading}
            onClick={onSimulate}
          >
            {isLoading ? "Comparing colors…" : "Try another color"}
          </button>
        </div>
      )}

      {result && videoUrl && (
        <>
          <div className="color-preview-stage" style={{ aspectRatio }}>
            <video
              ref={videoRef}
              src={videoUrl}
              muted
              playsInline
              preload="metadata"
              onLoadedMetadata={(metadataEvent) => {
                const video = metadataEvent.currentTarget;

                if (video.videoWidth > 0 && video.videoHeight > 0) {
                  setAspectRatio(`${video.videoWidth} / ${video.videoHeight}`);
                }

                video.currentTime = event.timestamp_ms / 1000;
                video.pause();
              }}
            />

            {selectedOption && (
              <div
                className="color-preview-overlay"
                style={overlayStyle}
                aria-hidden="true"
              />
            )}
            <span className="color-preview-label">
              Illustrative bounding-box tint
            </span>
          </div>

          <div className="color-options" aria-label="Simulated toy colors">
            {result.options.map((option) => {
              const selected = option.color_id === selectedColorId;
              const recommended =
                option.color_id === result.recommended_color_id;

              return (
                <button
                  type="button"
                  className={`color-option${selected ? " selected" : ""}`}
                  key={option.color_id}
                  aria-pressed={selected}
                  onClick={() =>
                    setSelection({
                      eventId: result.event_id,
                      colorId: option.color_id,
                    })
                  }
                >
                  <span
                    className="color-option-swatch"
                    style={{ backgroundColor: option.human_color }}
                  />
                  <span>
                    <strong>{option.label}</strong>
                    <small>
                      Dog-visible contrast: {option.dog_contrast_score}/100
                    </small>
                  </span>
                  <span className="color-option-rank">#{option.rank}</span>
                  {recommended && (
                    <span className="recommended-color">
                      Strongest simulated option
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {selectedOption && (
            <div className="selected-color-result">
              <div className="color-score-pair">
                <div>
                  <span
                    className="result-swatch"
                    style={{ backgroundColor: selectedOption.human_color }}
                  />
                  <small>Human palette color</small>
                  <strong>{selectedOption.human_contrast_score}/100</strong>
                </div>
                <div>
                  <span
                    className="result-swatch"
                    style={{ backgroundColor: selectedOption.dog_approx_color }}
                  />
                  <small>Canine-vision approximation</small>
                  <strong>{selectedOption.dog_contrast_score}/100</strong>
                </div>
              </div>
              <p>{selectedOption.explanation}</p>
              <p className="color-gain">
                Compared with sampled original:{" "}
                {selectedOption.dog_contrast_gain >= 0 ? "+" : ""}
                {selectedOption.dog_contrast_gain} points
              </p>
            </div>
          )}

          <button
            className="secondary-button"
            type="button"
            disabled={isLoading}
            onClick={onSimulate}
          >
            Recalculate from video
          </button>
        </>
      )}

      {error && (
        <div className="analysis-error" role="alert">
          {error}
        </div>
      )}
      <p className="phase-note">
        {result?.disclaimer ??
          "The preview tints the AI bounding box. It does not segment or physically recolor the object."}
      </p>
    </div>
  );
}
