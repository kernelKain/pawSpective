"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { CuriosityMap } from "./components/CuriosityMap";
import { LiveDogLens } from "./components/LiveDogLens";
import { VisibilityInsight } from "./components/VisibilityInsight";
import {
  analyzeCapturedClip,
  scoreCapturedClip,
} from "./lib/sceneAnalysisApi";
import type {
  CapturedClip,
  SceneEvent,
  VisibilityScore,
} from "./types/sceneAnalysis";

type Profile = {
  ownerName: string;
  dogName: string;
  breed: string;
  age: "Puppy" | "Adult" | "Senior";
  size: "Small" | "Medium" | "Large";
  personalities: string[];
  favorite: string;
  photo: string;
};

type Stage = "profile" | "lens" | "processing" | "results";

const personalityOptions = [
  "Curious",
  "Chill",
  "Foodie",
  "Athlete",
  "Detective",
  "Chaos",
];

const favoriteOptions = [
  "Ball",
  "Food",
  "People",
  "Dogs",
  "Cats",
  "Squirrels",
  "Sniffing",
];

const stages: Array<{ id: Stage; label: string }> = [
  { id: "profile", label: "Profile" },
  { id: "lens", label: "Dog Lens" },
  { id: "processing", label: "Analysis" },
  { id: "results", label: "Results" },
];

const defaultProfile: Profile = {
  ownerName: "",
  dogName: "",
  breed: "",
  age: "Adult",
  size: "Medium",
  personalities: [],
  favorite: "Ball",
  photo: "",
};

function formatTimestamp(timestampMs: number) {
  return `${(timestampMs / 1000).toFixed(1)}s`;
}

export function PawSpectiveShell({
  initialEvents,
}: {
  initialEvents: SceneEvent[];
}) {
  const [stage, setStage] = useState<Stage>("profile");
  const [profile, setProfile] = useState(defaultProfile);
  const [visionMix, setVisionMix] = useState(72);
  const [events, setEvents] = useState(initialEvents);
  const [selectedEventId, setSelectedEventId] = useState(
    initialEvents[0]?.event_id ?? "",
  );
  const [accuracyOpen, setAccuracyOpen] = useState(false);
  const [capturedClip, setCapturedClip] =
    useState<CapturedClip | null>(null);
  const [analysisError, setAnalysisError] =
    useState<string | null>(null);
  const [analysisSource, setAnalysisSource] =
    useState<"gemini" | "demo" | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [visibilityScores, setVisibilityScores] = useState<
    VisibilityScore[]
  >([]);
  const [visibilityWarnings, setVisibilityWarnings] = useState<
    string[]
  >([]);
  const [visibilityError, setVisibilityError] = useState<
    string | null
  >(null);
  const [isScoring, setIsScoring] = useState(false);
  const visibilityRequestIdRef = useRef(0);
  const visibilityAbortControllerRef =
    useRef<AbortController | null>(null);

  function invalidateVisibilityScores() {
    visibilityRequestIdRef.current += 1;
    visibilityAbortControllerRef.current?.abort();
    visibilityAbortControllerRef.current = null;
    setIsScoring(false);
    setVisibilityScores([]);
    setVisibilityWarnings([]);
    setVisibilityError(null);
  }

  useEffect(() => {
    return () => {
      visibilityRequestIdRef.current += 1;
      visibilityAbortControllerRef.current?.abort();
    };
  }, []);

  function updateProfile<K extends keyof Profile>(
    key: K,
    value: Profile[K],
  ) {
    setProfile((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function togglePersonality(personality: string) {
    setProfile((current) => {
      const selected =
        current.personalities.includes(personality);

      if (selected) {
        return {
          ...current,
          personalities: current.personalities.filter(
            (item) => item !== personality,
          ),
        };
      }

      if (current.personalities.length >= 2) {
        return current;
      }

      return {
        ...current,
        personalities: [
          ...current.personalities,
          personality,
        ],
      };
    });
  }

  function handlePhoto(
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    const reader = new FileReader();

    reader.onload = () => {
      if (typeof reader.result === "string") {
        updateProfile("photo", reader.result);
      }
    };

    reader.readAsDataURL(file);
  }

  function submitProfile(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    setStage("lens");
  }

  function handleClipChange(
    clip: CapturedClip | null,
  ) {
    setCapturedClip(clip);
    invalidateVisibilityScores();
  }

  async function beginSceneAnalysis() {
    if (!capturedClip) {
      return;
    }

    setAnalysisError(null);
    setAnalysisSource(null);
    setStage("processing");

    invalidateVisibilityScores();

    try {
      const response =
        await analyzeCapturedClip(capturedClip);

      setEvents(response.analysis.events);
      setSelectedEventId(
        response.analysis.events[0]?.event_id ?? "",
      );
      setAnalysisSource(response.source);
      setStage("results");
    } catch (error) {
      setAnalysisError(
        error instanceof Error
          ? error.message
          : "Scene analysis failed.",
      );
      setStage("lens");
    }
  }

  async function calculateVisibility() {
    if (!capturedClip || events.length === 0) {
      return;
    }

    if (analysisSource !== "gemini") {
      setVisibilityError(
        "Cached demo detections cannot be measured against this video. Run real Gemini analysis first.",
      );
      return;
    }

    visibilityAbortControllerRef.current?.abort();

    const requestId = visibilityRequestIdRef.current + 1;
    const abortController = new AbortController();

    visibilityRequestIdRef.current = requestId;
    visibilityAbortControllerRef.current = abortController;

    setIsScoring(true);
    setVisibilityScores([]);
    setVisibilityError(null);
    setVisibilityWarnings([]);

    try {
      const response = await scoreCapturedClip(
        capturedClip,
        events.map((event) => ({
          ...event,
          object_label: event.object_label.trim(),
        })),
        profile.favorite,
        abortController.signal,
      );

      if (
        requestId !== visibilityRequestIdRef.current ||
        abortController.signal.aborted
      ) {
        return;
      }

      setVisibilityScores(response.scores);
      setVisibilityWarnings(response.warnings);
    } catch (error) {
      if (
        requestId !== visibilityRequestIdRef.current ||
        abortController.signal.aborted ||
        (error instanceof DOMException &&
          error.name === "AbortError")
      ) {
        return;
      }

      setVisibilityError(
        error instanceof Error
          ? error.message
          : "Visibility scoring failed.",
      );
    } finally {
      if (requestId === visibilityRequestIdRef.current) {
        visibilityAbortControllerRef.current = null;
        setIsScoring(false);
      }
    }
  }

  function renameEvent(
    eventId: string,
    objectLabel: string,
  ) {
    invalidateVisibilityScores();

    if (
      objectLabel.length > 80 ||
      objectLabel.trim().length === 0
    ) {
      return;
    }

    setEvents((current) =>
      current.map((event) =>
        event.event_id === eventId
          ? {
              ...event,
              object_label: objectLabel,
            }
          : event,
      ),
    );
  }

  function removeEvent(eventId: string) {
    invalidateVisibilityScores();

    setEvents((current) => {
      const remaining = current.filter(
        (event) => event.event_id !== eventId,
      );

      if (selectedEventId === eventId) {
        setSelectedEventId(
          remaining[0]?.event_id ?? "",
        );
      }

      return remaining;
    });
  }

  const stageIndex = stages.findIndex(
    (item) => item.id === stage,
  );

  const selectedEvent = events.find(
    (event) => event.event_id === selectedEventId,
  );

  const selectedVisibilityScore =
    visibilityScores.find(
      (score) => score.event_id === selectedEventId,
    );

  return (
    <main className="app-shell">
      <header className="topbar">
        <button
          className="brand"
          type="button"
          disabled={isRecording}
          onClick={() => {
            invalidateVisibilityScores();
            setStage("profile");
          }}
          aria-label="Return to profile"
        >
          <span className="brand-mark">P</span>

          <span>
            <strong>PawSpective</strong>
            <small>
              Closer to their point of view
            </small>
          </span>
        </button>

        <div className="topbar-actions">
          <span className="phase-badge">
            Phase 4 · Visibility &amp; Curiosity
          </span>

          <button
            className="text-button"
            type="button"
            onClick={() => setAccuracyOpen(true)}
          >
            How accurate is this?
          </button>
        </div>
      </header>

      <nav
        className="progress"
        aria-label="Experience progress"
      >
        {stages.map((item, index) => {
          const completed = index < stageIndex;
          const active = item.id === stage;

          return (
            <div
              className={[
                "progress-step",
                active ? "active" : "",
                completed ? "completed" : "",
              ].join(" ")}
              key={item.id}
            >
              <span>
                {completed ? "✓" : index + 1}
              </span>
              <small>{item.label}</small>
            </div>
          );
        })}
      </nav>

      {stage === "profile" && (
        <section className="screen profile-screen">
          <div className="intro-copy">
            <p className="eyebrow">
              Tell us about your co-pilot
            </p>

            <h1>
              Meet the world from a slightly more{" "}
              <em>dog-shaped</em> perspective.
            </h1>

            <p className="lead">
              We use size to guide camera height.
              Personality and favorites personalize Story
              Mode—they never alter the scientific vision
              filter.
            </p>

            <button
              className="accuracy-card"
              type="button"
              onClick={() => setAccuracyOpen(true)}
            >
              <span>◉</span>

              <span>
                <strong>
                  Science and imagination stay separate
                </strong>
                <small>
                  Open the Accuracy Drawer
                </small>
              </span>
            </button>
          </div>

          <form
            className="profile-card"
            onSubmit={submitProfile}
          >
            <div className="avatar-row">
              <label className="avatar-upload">
                {profile.photo ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={profile.photo}
                    alt="Dog profile preview"
                  />
                ) : (
                  <span>🐕</span>
                )}

                <input
                  type="file"
                  accept="image/*"
                  onChange={handlePhoto}
                />
              </label>

              <div>
                <strong>Dog photo</strong>
                <small>
                  Optional · used as the profile avatar
                </small>
              </div>
            </div>

            <div className="field-grid">
              <label>
                Your first name

                <input
                  required
                  value={profile.ownerName}
                  onChange={(event) =>
                    updateProfile(
                      "ownerName",
                      event.target.value,
                    )
                  }
                  placeholder="Kshitij"
                />
              </label>

              <label>
                Dog&apos;s name

                <input
                  required
                  value={profile.dogName}
                  onChange={(event) =>
                    updateProfile(
                      "dogName",
                      event.target.value,
                    )
                  }
                  placeholder="Bruno"
                />
              </label>
            </div>

            <label>
              Breed or mix

              <input
                value={profile.breed}
                onChange={(event) =>
                  updateProfile(
                    "breed",
                    event.target.value,
                  )
                }
                placeholder="Optional"
              />
            </label>

            <div className="field-grid">
              <label>
                Age

                <select
                  value={profile.age}
                  onChange={(event) =>
                    updateProfile(
                      "age",
                      event.target
                        .value as Profile["age"],
                    )
                  }
                >
                  <option>Puppy</option>
                  <option>Adult</option>
                  <option>Senior</option>
                </select>
              </label>

              <label>
                Size

                <select
                  value={profile.size}
                  onChange={(event) =>
                    updateProfile(
                      "size",
                      event.target
                        .value as Profile["size"],
                    )
                  }
                >
                  <option>Small</option>
                  <option>Medium</option>
                  <option>Large</option>
                </select>
              </label>
            </div>

            <fieldset>
              <legend>
                Personality{" "}
                <span>Choose up to two</span>
              </legend>

              <div className="choice-row">
                {personalityOptions.map(
                  (personality) => {
                    const selected =
                      profile.personalities.includes(
                        personality,
                      );

                    return (
                      <button
                        className={
                          selected
                            ? "choice selected"
                            : "choice"
                        }
                        type="button"
                        key={personality}
                        aria-pressed={selected}
                        onClick={() =>
                          togglePersonality(
                            personality,
                          )
                        }
                      >
                        {personality}
                      </button>
                    );
                  },
                )}
              </div>
            </fieldset>

            <label>
              Favorite thing

              <select
                value={profile.favorite}
                onChange={(event) =>
                  updateProfile(
                    "favorite",
                    event.target.value,
                  )
                }
              >
                {favoriteOptions.map((favorite) => (
                  <option key={favorite}>
                    {favorite}
                  </option>
                ))}
              </select>
            </label>

            <button
              className="primary-button"
              type="submit"
            >
              Meet my co-pilot <span>→</span>
            </button>
          </form>
        </section>
      )}

      {stage === "lens" && (
        <section className="screen lens-screen">
          <div className="section-heading">
            <div>
              <p className="eyebrow">
                Live Dog Lens
              </p>

              <h1>
                Welcome,{" "}
                {profile.dogName || "co-pilot"}.
              </h1>
            </div>

            <button
              className="secondary-button"
              type="button"
              disabled={isRecording}
              onClick={() => setStage("profile")}
            >
              Edit profile
            </button>
          </div>

          <div className="lens-layout">
            <LiveDogLens
              visionMix={visionMix}
              onVisionMixChange={setVisionMix}
              onClipChange={handleClipChange}
              onRecordingChange={setIsRecording}
            />

            <aside className="lens-sidebar">
              <div className="profile-summary">
                <span className="profile-avatar">
                  {profile.photo ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={profile.photo}
                      alt=""
                    />
                  ) : (
                    "🐕"
                  )}
                </span>

                <div>
                  <p>
                    Meet{" "}
                    {profile.dogName || "your dog"}
                  </p>

                  <small>
                    {profile.age}{" "}
                    {profile.breed ||
                      `${profile.size} dog`}
                  </small>
                </div>
              </div>

              <div className="guide-card">
                <span>01</span>

                <div>
                  <strong>
                    Lower the camera
                  </strong>

                  <p>
                    Position it approximately at your
                    dog&apos;s eye height.
                  </p>
                </div>
              </div>

              <div className="guide-card">
                <span>02</span>

                <div>
                  <strong>
                    Follow head direction
                  </strong>

                  <p>
                    This is an approximate point of
                    view—not gaze tracking.
                  </p>
                </div>
              </div>

              <div className="mock-notice">
                Record or upload a short clip. Gemini
                identifies visibly supported objects.
                After reviewing them, you can calculate
                deterministic visibility and Curiosity
                scores.
              </div>

              {analysisError && (
                <div
                  className="analysis-error"
                  role="alert"
                >
                  {analysisError}
                </div>
              )}

              <button
                className="primary-button"
                type="button"
                disabled={
                  !capturedClip ||
                  isRecording ||
                  capturedClip.durationMs < 5_000 ||
                  capturedClip.durationMs > 15_000
                }
                onClick={() =>
                  void beginSceneAnalysis()
                }
              >
                Analyze captured moment
              </button>
            </aside>
          </div>
        </section>
      )}

      {stage === "processing" && (
        <section className="screen processing-screen">
          <div className="processing-mark">
            🐾
          </div>

          <p className="eyebrow">
            AI scene analysis
          </p>

          <h1>Finding visible scene signals…</h1>

          <p className="lead">
            The video is being validated, normalized,
            and analyzed against the strict Phase 0
            scene contract.
          </p>

          <div className="processing-list">
            <span className="done">
              ✓ Clip uploaded
            </span>
            <span className="loading">
              ● Checking visible objects
            </span>
            <span>
              ○ Validating scene timeline
            </span>
          </div>
        </section>
      )}

      {stage === "results" && (
        <section className="screen results-screen">
          <div className="section-heading">
            <div>
              <p className="eyebrow">
                Scene analysis
              </p>

              <h1>
                {profile.dogName || "Your dog"}
                &apos;s visible scene
              </h1>
            </div>

            <button
              className="secondary-button"
              type="button"
              disabled={isScoring}
              onClick={() => {
                setCapturedClip(null);
                setAnalysisError(null);
                setAnalysisSource(null);
                setEvents([]);
                setSelectedEventId("");
                invalidateVisibilityScores();
                setStage("lens");
              }}
            >
              Try another moment
            </button>
          </div>

          {analysisSource === "demo" && (
            <div className="mock-notice">
              Gemini was unavailable or demo mode is
              enabled. The validated cached response is
              being shown.
            </div>
          )}

          <div className="results-grid">
            <section className="result-card object-review">
              <div className="card-heading">
                <div>
                  <span className="label ai">
                    AI-inferred
                  </span>
                  <h2>
                    Review detected objects
                  </h2>
                </div>

                <span>
                  {events.length} objects
                </span>
              </div>

              <p>
                Rename or remove anything incorrect.
                Your corrections become the source of
                truth.
              </p>

              <div className="event-list">
                {events.map((event) => (
                  <div
                    className="event-row"
                    key={event.event_id}
                  >
                    <input
                      type="radio"
                      name="visibility-object"
                      checked={
                        selectedEventId ===
                        event.event_id
                      }
                      aria-label={`Use ${event.object_label} for visibility analysis`}
                      disabled={isScoring}
                      onChange={() =>
                        setSelectedEventId(
                          event.event_id,
                        )
                      }
                    />

                    <div>
                      <input
                        className="event-name"
                        value={event.object_label}
                        disabled={isScoring}
                        onChange={(changeEvent) =>
                          renameEvent(
                            event.event_id,
                            changeEvent.target.value,
                          )
                        }
                        onBlur={(blurEvent) =>
                          renameEvent(
                            event.event_id,
                            blurEvent.target.value.trim(),
                          )
                        }
                      />

                      <small>
                        {formatTimestamp(
                          event.timestamp_ms,
                        )}{" "}
                        ·{" "}
                        {Math.round(
                          event.confidence * 100,
                        )}
                        % confidence
                      </small>
                    </div>

                    <button
                      type="button"
                      aria-label={`Remove ${event.object_label}`}
                      disabled={isScoring}
                      onClick={() =>
                        removeEvent(event.event_id)
                      }
                    >
                      Remove
                    </button>
                  </div>
                ))}

                {events.length === 0 && (
                  <p className="empty-state">
                    No objects remain. Return to Dog
                    Lens to analyze another clip.
                  </p>
                )}
              </div>

              <button
                className="primary-button"
                type="button"
                disabled={
                  isScoring ||
                  events.length === 0 ||
                  analysisSource !== "gemini"
                }
                onClick={() =>
                  void calculateVisibility()
                }
              >
                {isScoring
                  ? "Calculating visibility…"
                  : "Calculate visibility & curiosity"}
              </button>

              {analysisSource === "demo" && (
                <p className="phase-note">
                  Visibility scoring is disabled because
                  cached bounding boxes do not belong to
                  this uploaded clip.
                </p>
              )}

              {visibilityError && (
                <div
                  className="analysis-error"
                  role="alert"
                >
                  {visibilityError}
                </div>
              )}

              {visibilityWarnings.length > 0 && (
                <div className="score-warnings">
                  {visibilityWarnings.map(
                    (warning) => (
                      <p key={warning}>
                        {warning}
                      </p>
                    ),
                  )}
                </div>
              )}
            </section>

            <section className="result-card curiosity-card">
              <div className="card-heading">
                <div>
                  <span className="label ai">
                    AI boxes + deterministic weighting
                  </span>

                  <h2>Curiosity Map</h2>
                </div>
              </div>

              {capturedClip ? (
                <CuriosityMap
                  clip={capturedClip}
                  events={events}
                  scores={visibilityScores}
                  selectedEventId={
                    selectedEventId
                  }
                  onSelect={
                    setSelectedEventId
                  }
                />
              ) : (
                <p>
                  The original clip is unavailable.
                </p>
              )}
            </section>

            <section className="result-card visibility-card">
              <div className="card-heading">
                <div>
                  <span className="label science">
                    Measured + AI-labeled inputs
                  </span>

                  <h2>Visibility insight</h2>
                </div>

                {selectedVisibilityScore && (
                  <span>
                    {
                      selectedVisibilityScore.salience_score
                    }
                    /100 cue score
                  </span>
                )}
              </div>

              <VisibilityInsight
                event={selectedEvent}
                score={selectedVisibilityScore}
              />
            </section>

            <section className="result-card story-card">
              <div className="card-heading">
                <div>
                  <span className="label fun">
                    Phase 5 preview
                  </span>
                  <h2>Story Reel preview</h2>
                </div>
              </div>

              <blockquote>
                “At 14:03,{" "}
                {profile.dogName ||
                  "our investigator"}{" "}
                entered the garden. The human
                believed the objective was exercise.
                The evidence pointed toward one
                suspicious blue ball.”
              </blockquote>

              <p>
                Nature documentary · fictional dog
                voice · approximately 18 seconds
              </p>

              <button
                className="secondary-button"
                type="button"
                disabled
              >
                Audio arrives in a later phase
              </button>
            </section>
          </div>
        </section>
      )}

      <footer>
        <span>PawSpective</span>

        <p>
          Fun enough to share. Transparent enough to
          trust.
        </p>
      </footer>

      {accuracyOpen && (
        <div className="drawer-layer">
          <button
            className="drawer-backdrop"
            type="button"
            aria-label="Close accuracy information"
            onClick={() =>
              setAccuracyOpen(false)
            }
          />

          <aside
            className="accuracy-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="accuracy-title"
          >
            <button
              className="drawer-close"
              type="button"
              onClick={() =>
                setAccuracyOpen(false)
              }
              aria-label="Close"
            >
              ×
            </button>

            <p className="eyebrow">
              Transparency by design
            </p>

            <h2 id="accuracy-title">
              How PawSpective reaches a result
            </h2>

            <div className="accuracy-section">
              <span className="accuracy-icon science">
                ✓
              </span>

              <div>
                <strong>
                  Research-grounded
                </strong>

                <p>
                  Canine color transformation and
                  foreground/background contrast
                  calculation, apparent-size measurement,
                  and deterministic score weighting.
                </p>
              </div>
            </div>

            <div className="accuracy-section">
              <span className="accuracy-icon ai">
                ~
              </span>

              <div>
                <strong>AI-inferred</strong>

                <p>
                  Object identification, bounding
                  boxes, ordinal motion labels, and
                  possible visible attention cues.
                </p>
              </div>
            </div>

            <div className="accuracy-section">
              <span className="accuracy-icon fun">
                ✦
              </span>

              <div>
                <strong>Just for fun</strong>

                <p>
                  Fictional dog narration, cat
                  commentary and playful story
                  framing.
                </p>
              </div>
            </div>

            <div className="accuracy-warning">
              PawSpective never claims to read a
              dog&apos;s exact gaze, thoughts,
              feelings or sense of smell.
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}
