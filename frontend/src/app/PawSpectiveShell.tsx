"use client";

import {
  ChangeEvent,
  FormEvent,
  useMemo,
  useRef,
  useState,
} from "react";

export type SceneEvent = {
  event_id: string;
  timestamp_ms: number;
  object_label: string;
  category:
    | "person"
    | "animal"
    | "toy"
    | "food"
    | "vehicle"
    | "environment"
    | "other";
  bounding_box: {
    x_min: number;
    y_min: number;
    x_max: number;
    y_max: number;
  };
  confidence: number;
  visible_evidence: string;
  motion_level: "none" | "low" | "medium" | "high";
};

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

function visibilityScore(event?: SceneEvent) {
  if (!event) return 0;
  if (event.object_label.toLowerCase().includes("blue")) return 89;
  if (event.category === "toy") return 76;
  if (event.motion_level === "high") return 72;
  return 61;
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
  const analysisTimer = useRef<number | null>(null);

  const selectedEvent = useMemo(
    () => events.find((event) => event.event_id === selectedEventId),
    [events, selectedEventId],
  );

  const score = visibilityScore(selectedEvent);

  function updateProfile<K extends keyof Profile>(
    key: K,
    value: Profile[K],
  ) {
    setProfile((current) => ({ ...current, [key]: value }));
  }

  function togglePersonality(personality: string) {
    setProfile((current) => {
      const selected = current.personalities.includes(personality);

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
        personalities: [...current.personalities, personality],
      };
    });
  }

  function handlePhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) return;

    const reader = new FileReader();

    reader.onload = () => {
      if (typeof reader.result === "string") {
        updateProfile("photo", reader.result);
      }
    };

    reader.readAsDataURL(file);
  }

  function submitProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStage("lens");
  }

  function beginMockAnalysis() {
    setStage("processing");

    if (analysisTimer.current) {
      window.clearTimeout(analysisTimer.current);
    }

    analysisTimer.current = window.setTimeout(() => {
      setStage("results");
    }, 1800);
  }

  function renameEvent(eventId: string, objectLabel: string) {
    setEvents((current) =>
      current.map((event) =>
        event.event_id === eventId
          ? { ...event, object_label: objectLabel }
          : event,
      ),
    );
  }

  function removeEvent(eventId: string) {
    setEvents((current) => {
      const remaining = current.filter(
        (event) => event.event_id !== eventId,
      );

      if (selectedEventId === eventId) {
        setSelectedEventId(remaining[0]?.event_id ?? "");
      }

      return remaining;
    });
  }

  const stageIndex = stages.findIndex((item) => item.id === stage);

  return (
    <main className="app-shell">
      <header className="topbar">
        <button
          className="brand"
          type="button"
          onClick={() => setStage("profile")}
          aria-label="Return to profile"
        >
          <span className="brand-mark">P</span>
          <span>
            <strong>PawSpective</strong>
            <small>Closer to their point of view</small>
          </span>
        </button>

        <div className="topbar-actions">
          <span className="phase-badge">Phase 1 · Mock experience</span>

          <button
            className="text-button"
            type="button"
            onClick={() => setAccuracyOpen(true)}
          >
            How accurate is this?
          </button>
        </div>
      </header>

      <nav className="progress" aria-label="Experience progress">
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
              <span>{completed ? "✓" : index + 1}</span>
              <small>{item.label}</small>
            </div>
          );
        })}
      </nav>

      {stage === "profile" && (
        <section className="screen profile-screen">
          <div className="intro-copy">
            <p className="eyebrow">Tell us about your co-pilot</p>

            <h1>
              Meet the world from a slightly more{" "}
              <em>dog-shaped</em> perspective.
            </h1>

            <p className="lead">
              We use size to guide camera height. Personality and
              favorites personalize Story Mode—they never alter the
              scientific vision filter.
            </p>

            <button
              className="accuracy-card"
              type="button"
              onClick={() => setAccuracyOpen(true)}
            >
              <span>◉</span>

              <span>
                <strong>Science and imagination stay separate</strong>
                <small>Open the Accuracy Drawer</small>
              </span>
            </button>
          </div>

          <form className="profile-card" onSubmit={submitProfile}>
            <div className="avatar-row">
              <label className="avatar-upload">
                {profile.photo ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={profile.photo} alt="Dog profile preview" />
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
                <small>Optional · used as the profile avatar</small>
              </div>
            </div>

            <div className="field-grid">
              <label>
                Your first name
                <input
                  required
                  value={profile.ownerName}
                  onChange={(event) =>
                    updateProfile("ownerName", event.target.value)
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
                    updateProfile("dogName", event.target.value)
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
                  updateProfile("breed", event.target.value)
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
                      event.target.value as Profile["age"],
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
                      event.target.value as Profile["size"],
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
                Personality <span>Choose up to two</span>
              </legend>

              <div className="choice-row">
                {personalityOptions.map((personality) => {
                  const selected =
                    profile.personalities.includes(personality);

                  return (
                    <button
                      className={selected ? "choice selected" : "choice"}
                      type="button"
                      key={personality}
                      aria-pressed={selected}
                      onClick={() => togglePersonality(personality)}
                    >
                      {personality}
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <label>
              Favorite thing
              <select
                value={profile.favorite}
                onChange={(event) =>
                  updateProfile("favorite", event.target.value)
                }
              >
                {favoriteOptions.map((favorite) => (
                  <option key={favorite}>{favorite}</option>
                ))}
              </select>
            </label>

            <button className="primary-button" type="submit">
              Meet my co-pilot <span>→</span>
            </button>
          </form>
        </section>
      )}

      {stage === "lens" && (
        <section className="screen lens-screen">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Live Dog Lens</p>
              <h1>
                Welcome, {profile.dogName || "co-pilot"}.
              </h1>
            </div>

            <button
              className="secondary-button"
              type="button"
              onClick={() => setStage("profile")}
            >
              Edit profile
            </button>
          </div>

          <div className="lens-layout">
            <div className="camera-card">
              <div className="camera-labels">
                <span>Mock camera</span>
                <span>Research-grounded approximation</span>
              </div>

              <div className="mock-camera">
                <div className="human-scene">
                  <div className="sun" />
                  <div className="tree tree-one" />
                  <div className="tree tree-two" />
                  <div className="ball red-ball" />
                  <div className="ball blue-ball" />
                  <div className="dog-subject">🐕</div>
                </div>

                <div
                  className="dog-vision-layer"
                  style={{ opacity: visionMix / 100 }}
                />

                <div className="alignment-guide">
                  <span>+</span>
                  <small>Approximate head-facing direction</small>
                </div>
              </div>

              <div className="comparison-control">
                <strong>Human view</strong>

                <input
                  aria-label="Human and dog vision comparison"
                  type="range"
                  min="0"
                  max="100"
                  value={visionMix}
                  onChange={(event) =>
                    setVisionMix(Number(event.target.value))
                  }
                />

                <strong>Dog Vision</strong>
              </div>
            </div>

            <aside className="lens-sidebar">
              <div className="profile-summary">
                <span className="profile-avatar">
                  {profile.photo ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={profile.photo} alt="" />
                  ) : (
                    "🐕"
                  )}
                </span>

                <div>
                  <p>Meet {profile.dogName || "your dog"}</p>
                  <small>
                    {profile.age}{" "}
                    {profile.breed || `${profile.size} dog`}
                  </small>
                </div>
              </div>

              <div className="guide-card">
                <span>01</span>

                <div>
                  <strong>Lower the camera</strong>
                  <p>
                    Position it approximately at your dog&apos;s eye
                    height.
                  </p>
                </div>
              </div>

              <div className="guide-card">
                <span>02</span>

                <div>
                  <strong>Follow head direction</strong>
                  <p>
                    This is an approximate point of view—not gaze
                    tracking.
                  </p>
                </div>
              </div>

              <div className="mock-notice">
                Camera access arrives in Phase 2. This scene proves the
                Phase 1 interaction flow.
              </div>

              <button
                className="primary-button"
                type="button"
                onClick={beginMockAnalysis}
              >
                Record mock moment <span>●</span>
              </button>
            </aside>
          </div>
        </section>
      )}

      {stage === "processing" && (
        <section className="screen processing-screen">
          <div className="processing-mark">🐾</div>

          <p className="eyebrow">Mock analysis</p>
          <h1>Finding visible scene signals…</h1>

          <p className="lead">
            We are loading the validated Phase 0 example response. No
            external AI request is being made.
          </p>

          <div className="processing-list">
            <span className="done">✓ Scene prepared</span>
            <span className="loading">● Checking visible objects</span>
            <span>○ Preparing curiosity map</span>
          </div>
        </section>
      )}

      {stage === "results" && (
        <section className="screen results-screen">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Your mock result</p>
              <h1>{profile.dogName || "Your dog"}&apos;s garden briefing</h1>
            </div>

            <button
              className="secondary-button"
              type="button"
              onClick={() => setStage("lens")}
            >
              Try another moment
            </button>
          </div>

          <div className="results-grid">
            <section className="result-card object-review">
              <div className="card-heading">
                <div>
                  <span className="label ai">AI-inferred</span>
                  <h2>Review detected objects</h2>
                </div>

                <span>{events.length} objects</span>
              </div>

              <p>
                Rename or remove anything incorrect. Your corrections
                become the source of truth.
              </p>

              <div className="event-list">
                {events.map((event) => (
                  <div className="event-row" key={event.event_id}>
                    <input
                      type="radio"
                      name="visibility-object"
                      checked={selectedEventId === event.event_id}
                      aria-label={`Use ${event.object_label} for visibility analysis`}
                      onChange={() =>
                        setSelectedEventId(event.event_id)
                      }
                    />

                    <div>
                      <input
                        className="event-name"
                        value={event.object_label}
                        onChange={(changeEvent) =>
                          renameEvent(
                            event.event_id,
                            changeEvent.target.value,
                          )
                        }
                      />

                      <small>
                        {formatTimestamp(event.timestamp_ms)} ·{" "}
                        {Math.round(event.confidence * 100)}% confidence
                      </small>
                    </div>

                    <button
                      type="button"
                      aria-label={`Remove ${event.object_label}`}
                      onClick={() => removeEvent(event.event_id)}
                    >
                      Remove
                    </button>
                  </div>
                ))}

                {events.length === 0 && (
                  <p className="empty-state">
                    No objects remain. Return to Dog Lens to restart the
                    mock analysis.
                  </p>
                )}
              </div>
            </section>

            <section className="result-card curiosity-card">
              <div className="card-heading">
                <div>
                  <span className="label ai">AI-inferred</span>
                  <h2>Curiosity Map</h2>
                </div>
              </div>

              <div className="curiosity-map">
                <div className="map-ground" />

                {events.map((event, index) => {
                  const box = event.bounding_box;

                  return (
                    <button
                      type="button"
                      className={[
                        "map-marker",
                        selectedEventId === event.event_id
                          ? "selected"
                          : "",
                      ].join(" ")}
                      key={event.event_id}
                      onClick={() =>
                        setSelectedEventId(event.event_id)
                      }
                      style={{
                        left: `${box.x_min * 100}%`,
                        top: `${box.y_min * 100}%`,
                        width: `${(box.x_max - box.x_min) * 100}%`,
                        height: `${(box.y_max - box.y_min) * 100}%`,
                      }}
                    >
                      <span>{index + 1}</span>
                      <small>{event.object_label}</small>
                    </button>
                  );
                })}
              </div>

              <p className="map-explanation">
                Possible attention cues only. This is not gaze tracking.
              </p>
            </section>

            <section className="result-card visibility-card">
              <div className="card-heading">
                <div>
                  <span className="label science">
                    Research-grounded
                  </span>
                  <h2>Visibility insight</h2>
                </div>

                <strong className="score">{score}/100</strong>
              </div>

              {selectedEvent ? (
                <>
                  <h3>{selectedEvent.object_label}</h3>

                  <div className="score-track">
                    <span style={{ width: `${score}%` }} />
                  </div>

                  <p>
                    This object remains relatively distinct after the
                    canine-vision transformation. The score is a
                    product-relative contrast measure—not a probability.
                  </p>

                  <small>
                    Selected from the corrected scene timeline.
                  </small>
                </>
              ) : (
                <p>Select an object to calculate a mock result.</p>
              )}
            </section>

            <section className="result-card story-card">
              <div className="card-heading">
                <div>
                  <span className="label fun">Just for fun</span>
                  <h2>Story Reel preview</h2>
                </div>
              </div>

              <blockquote>
                “At 14:03, {profile.dogName || "our investigator"} entered
                the garden. The human believed the objective was
                exercise. The evidence pointed toward one suspicious blue
                ball.”
              </blockquote>

              <p>
                Nature documentary · fictional dog voice · approximately
                18 seconds
              </p>

              <button className="secondary-button" type="button" disabled>
                Audio arrives in a later phase
              </button>
            </section>
          </div>
        </section>
      )}

      <footer>
        <span>PawSpective</span>

        <p>
          Fun enough to share. Transparent enough to trust.
        </p>
      </footer>

      {accuracyOpen && (
        <div className="drawer-layer">
          <button
            className="drawer-backdrop"
            type="button"
            aria-label="Close accuracy information"
            onClick={() => setAccuracyOpen(false)}
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
              onClick={() => setAccuracyOpen(false)}
              aria-label="Close"
            >
              ×
            </button>

            <p className="eyebrow">Transparency by design</p>
            <h2 id="accuracy-title">How PawSpective reaches a result</h2>

            <div className="accuracy-section">
              <span className="accuracy-icon science">✓</span>

              <div>
                <strong>Research-grounded</strong>
                <p>
                  Canine color transformation and foreground/background
                  contrast calculation.
                </p>
              </div>
            </div>

            <div className="accuracy-section">
              <span className="accuracy-icon ai">~</span>

              <div>
                <strong>AI-inferred</strong>
                <p>
                  Object identification, bounding boxes and possible
                  visible attention cues.
                </p>
              </div>
            </div>

            <div className="accuracy-section">
              <span className="accuracy-icon fun">✦</span>

              <div>
                <strong>Just for fun</strong>
                <p>
                  Fictional dog narration, cat commentary and playful
                  story framing.
                </p>
              </div>
            </div>

            <div className="accuracy-warning">
              PawSpective never claims to read a dog&apos;s exact gaze,
              thoughts, feelings or sense of smell.
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}