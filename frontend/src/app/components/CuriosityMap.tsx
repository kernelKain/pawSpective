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
  SceneEvent,
  VisibilityScore,
} from "../types/sceneAnalysis";

type CuriosityMapProps = {
  clip: CapturedClip;
  events: SceneEvent[];
  scores: VisibilityScore[];
  selectedEventId: string;
  onSelect: (eventId: string) => void;
};

export function CuriosityMap({
  clip,
  events,
  scores,
  selectedEventId,
  onSelect,
}: CuriosityMapProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const videoUrl = useMemo(
    () => URL.createObjectURL(clip.file),
    [clip.file],
  );
  const [currentTimeMs, setCurrentTimeMs] = useState(0);

  const scoresById = useMemo(
    () => new Map(scores.map((score) => [score.event_id, score])),
    [scores],
  );

  useEffect(() => {
    return () => {
      URL.revokeObjectURL(videoUrl);
    };
  }, [videoUrl]);

  function seekToEvent(event: SceneEvent) {
    onSelect(event.event_id);

    if (videoRef.current) {
      videoRef.current.currentTime = event.timestamp_ms / 1000;
      setCurrentTimeMs(event.timestamp_ms);
    }
  }

  useEffect(() => {
    const selectedEvent = events.find(
      (event) => event.event_id === selectedEventId,
    );

    if (
      selectedEvent &&
      videoRef.current &&
      videoRef.current.readyState >= 1
    ) {
      videoRef.current.currentTime =
        selectedEvent.timestamp_ms / 1000;
    }
  }, [events, selectedEventId]);

  const selectedScore = scoresById.get(selectedEventId);

  return (
    <div className="curiosity-experience">
      <div className="curiosity-video-stage">
        {videoUrl && (
          <video
            ref={videoRef}
            src={videoUrl}
            controls
            muted
            playsInline
            onLoadedMetadata={() => {
              const selectedEvent = events.find(
                (event) => event.event_id === selectedEventId,
              );

              if (selectedEvent && videoRef.current) {
                videoRef.current.currentTime =
                  selectedEvent.timestamp_ms / 1000;
                setCurrentTimeMs(selectedEvent.timestamp_ms);
              }
            }}
            onTimeUpdate={(event) =>
              setCurrentTimeMs(
                Math.round(event.currentTarget.currentTime * 1000),
              )
            }
          />
        )}

        <div className="curiosity-overlay" aria-live="polite">
          {events.map((event) => {
            const score = scoresById.get(event.event_id);
            const isNearTimestamp =
              Math.abs(event.timestamp_ms - currentTimeMs) <= 900;

            if (!isNearTimestamp) {
              return null;
            }

            const box = event.bounding_box;
            const opacity =
              0.4 + ((score?.salience_score ?? 25) / 100) * 0.6;

            return (
              <button
                type="button"
                key={event.event_id}
                className={[
                  "curiosity-marker",
                  score ? `cue-${score.salience_level}` : "",
                  selectedEventId === event.event_id
                    ? "selected"
                    : "",
                ].join(" ")}
                aria-label={`Possible attention cue: ${event.object_label}`}
                onClick={() => seekToEvent(event)}
                style={
                  {
                    left: `${box.x_min * 100}%`,
                    top: `${box.y_min * 100}%`,
                    width: `${(box.x_max - box.x_min) * 100}%`,
                    height: `${(box.y_max - box.y_min) * 100}%`,
                    opacity,
                  } as CSSProperties
                }
              >
                <span>{event.object_label}</span>
                {score && <small>{score.salience_score}/100</small>}
              </button>
            );
          })}
        </div>
      </div>

      <div className="curiosity-timeline">
        {events.map((event) => (
          <button
            type="button"
            key={event.event_id}
            className={
              selectedEventId === event.event_id ? "selected" : ""
            }
            onClick={() => seekToEvent(event)}
          >
            {(event.timestamp_ms / 1000).toFixed(1)}s ·{" "}
            {event.object_label}
          </button>
        ))}
      </div>

      {selectedScore && (
        <div className="cue-explanation">
          <strong>Why this appeared</strong>
          <ul>
            {selectedScore.why.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="map-explanation">
        Possible visual cues only. This is not gaze tracking and does not
        identify thoughts, emotions, or intent.
      </p>
    </div>
  );
}