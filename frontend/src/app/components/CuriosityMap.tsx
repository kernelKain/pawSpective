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

function useObjectUrl(file: File) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    const nextUrl = URL.createObjectURL(file);

    // The URL is an external browser resource that only exists after commit.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setObjectUrl(nextUrl);

    return () => {
      URL.revokeObjectURL(nextUrl);
    };
  }, [file]);

  return objectUrl;
}

function formatPlaybackTime(timeMs: number) {
  return `${(timeMs / 1000).toFixed(1)}s`;
}

export function CuriosityMap({
  clip,
  events,
  scores,
  selectedEventId,
  onSelect,
}: CuriosityMapProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const videoUrl = useObjectUrl(clip.file);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [durationMs, setDurationMs] = useState(clip.durationMs);
  const [isPlaying, setIsPlaying] = useState(false);

  const scoresById = useMemo(
    () => new Map(scores.map((score) => [score.event_id, score])),
    [scores],
  );

  function seekToEvent(event: SceneEvent) {
    onSelect(event.event_id);

    if (videoRef.current) {
      videoRef.current.currentTime = event.timestamp_ms / 1000;
      setCurrentTimeMs(event.timestamp_ms);
    }
  }

  function seekToTime(timeMs: number) {
    const boundedTimeMs = Math.min(
      Math.max(timeMs, 0),
      durationMs,
    );

    if (videoRef.current) {
      videoRef.current.currentTime = boundedTimeMs / 1000;
    }

    setCurrentTimeMs(boundedTimeMs);
  }

  function togglePlayback() {
    const video = videoRef.current;

    if (!video) {
      return;
    }

    if (video.paused) {
      void video.play().catch(() => {
        setIsPlaying(false);
      });
    } else {
      video.pause();
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
            muted
            playsInline
            onLoadedMetadata={() => {
              if (
                videoRef.current &&
                Number.isFinite(videoRef.current.duration)
              ) {
                setDurationMs(
                  Math.round(videoRef.current.duration * 1000),
                );
              }

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
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onEnded={() => setIsPlaying(false)}
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

      <div className="curiosity-playback-controls">
        <button
          type="button"
          onClick={togglePlayback}
          disabled={!videoUrl}
          aria-label={isPlaying ? "Pause video" : "Play video"}
        >
          {isPlaying ? "Pause" : "Play"}
        </button>

        <input
          type="range"
          min={0}
          max={Math.max(durationMs, 1)}
          step={100}
          value={Math.min(currentTimeMs, Math.max(durationMs, 1))}
          onChange={(event) =>
            seekToTime(Number(event.target.value))
          }
          aria-label="Video position"
          disabled={!videoUrl}
        />

        <span>
          {formatPlaybackTime(currentTimeMs)} /{" "}
          {formatPlaybackTime(durationMs)}
        </span>
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
