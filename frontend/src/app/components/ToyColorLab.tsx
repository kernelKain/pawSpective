"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

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
  disabledReason?: string;
  onSimulate: () => void;
};

export function ToyColorLab({
  clip,
  event,
  result,
  isLoading,
  error,
  disabled,
  disabledReason,
  onSimulate,
}: ToyColorLabProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const videoUrl = useMemo(() => URL.createObjectURL(clip.file), [clip.file]);
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
    () => result?.options.find((option) => option.color_id === selectedColorId) ?? null,
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
            Compare six screen colors for <strong>{event.object_label}</strong>
            against the nearby color measured in this frame.
          </p>
          <button
            className="primary-button"
            type="button"
            disabled={disabled || isLoading}
            onClick={onSimulate}
            aria-describedby={disabled && disabledReason ? "color-disabled-reason" : undefined}
          >
            {isLoading ? "Comparing six colors…" : "Compare six colors"}
          </button>
          {disabled && disabledReason && (
            <p className="action-hint" id="color-disabled-reason">
              {disabledReason}
            </p>
          )}
        </div>
      )}

      {result && videoUrl && (
        <>
          <div className="color-original-summary">
            <div>
              <span className="result-swatch" style={{ backgroundColor: result.original_human_color }} />
              <small>Original sampled color</small>
              <strong>{result.original_human_contrast_score}/100</strong>
            </div>
            <div>
              <span className="result-swatch" style={{ backgroundColor: result.original_dog_color }} />
              <small>Original canine approximation</small>
              <strong>{result.original_dog_contrast_score}/100</strong>
            </div>
          </div>

          <div className="color-preview-stage" style={{ aspectRatio }}>
            <video
              key={videoUrl}
              ref={videoRef}
              src={videoUrl}
              muted
              playsInline
              preload="metadata"
              aria-label={`Color preview for ${event.object_label}`}
              onLoadedMetadata={(metadataEvent) => {
                const video = metadataEvent.currentTarget;
                if (video.videoWidth > 0 && video.videoHeight > 0) {
                  setAspectRatio(`${video.videoWidth} / ${video.videoHeight}`);
                }
                video.currentTime = Math.min(
                  event.timestamp_ms / 1000,
                  Math.max(0, video.duration - 0.05),
                );
                video.pause();
              }}
            />
            {selectedOption && (
              <div className="color-preview-overlay" style={overlayStyle} aria-hidden="true" />
            )}
            <span className="color-preview-label">Illustrative selected area</span>
          </div>

          <div className="color-options" aria-label="Six color recommendations">
            {result.options.map((option) => {
              const selected = option.color_id === selectedColorId;
              const recommended = option.color_id === result.recommended_color_id;
              return (
                <button
                  type="button"
                  className={`color-option${selected ? " selected" : ""}`}
                  key={option.color_id}
                  aria-pressed={selected}
                  onClick={() =>
                    setSelection({ eventId: result.event_id, colorId: option.color_id })
                  }
                >
                  <span className="color-option-swatch" style={{ backgroundColor: option.human_color }} />
                  <span>
                    <strong>{option.label}</strong>
                    <small>
                      Human {option.human_contrast_score} · Dog {option.dog_contrast_score}
                    </small>
                  </span>
                  <span className="color-option-rank">#{option.rank}</span>
                  {recommended && <span className="recommended-color">Best ranked match</span>}
                </button>
              );
            })}
          </div>

          {selectedOption && (
            <div className="selected-color-result">
              <div className="color-score-pair">
                <div>
                  <span className="result-swatch" style={{ backgroundColor: selectedOption.human_color }} />
                  <small>Selected screen color</small>
                  <strong>{selectedOption.human_contrast_score}/100</strong>
                </div>
                <div>
                  <span className="result-swatch" style={{ backgroundColor: selectedOption.dog_approx_color }} />
                  <small>Canine-color approximation</small>
                  <strong>{selectedOption.dog_contrast_score}/100</strong>
                </div>
              </div>
              <p>{selectedOption.explanation}</p>
              <p className="color-gain">
                Contrast {selectedOption.dog_contrast_gain >= 0 ? "gain" : "loss"}: {Math.abs(selectedOption.dog_contrast_gain)} points versus the sampled original
              </p>
            </div>
          )}

          <button className="secondary-button" type="button" disabled={isLoading} onClick={onSimulate}>
            Recalculate from clip
          </button>
        </>
      )}

      {error && <div className="analysis-error" role="alert">{error}</div>}
      <p className="context-note">
        {result?.disclaimer ??
          "This preview colors the selected rectangular area. It is a screen-color approximation—not exact canine vision, object segmentation, or a physical-product guarantee."}
      </p>
    </div>
  );
}
