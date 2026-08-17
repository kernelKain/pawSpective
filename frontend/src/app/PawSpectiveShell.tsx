"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { CuriosityMap } from "./components/CuriosityMap";
import { LiveDogLens } from "./components/LiveDogLens";
import { PawSpectiveLogo } from "./components/PawSpectiveLogo";
import { StoryReel } from "./components/StoryReel";
import { ToyColorLab } from "./components/ToyColorLab";
import { VisibilityInsight } from "./components/VisibilityInsight";
import {
  analyzeCapturedClip,
  loadControlledDemo,
  renderCapturedStoryReel,
  scoreCapturedClip,
  simulateCapturedObjectColors,
} from "./lib/sceneAnalysisApi";
import type {
  AnalysisSource,
  AnimationProvider,
  CapturedClip,
  ColorSimulationResponse,
  SceneEvent,
  StoryReelResult,
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

type Stage =
  | "profile"
  | "lens"
  | "processing"
  | "results";

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

const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
const MAX_PHOTO_EDGE = 6_000;
const MAX_PHOTO_PIXELS = 24_000_000;
const PHOTO_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
]);

function hasExpectedPhotoSignature(type: string, bytes: Uint8Array) {
  if (type === "image/jpeg") {
    return bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
  }
  if (type === "image/png") {
    return [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]
      .every((value, index) => bytes[index] === value);
  }
  if (type === "image/webp") {
    return String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" &&
      String.fromCharCode(...bytes.slice(8, 12)) === "WEBP";
  }
  const gifHeader = String.fromCharCode(...bytes.slice(0, 6));
  return gifHeader === "GIF87a" || gifHeader === "GIF89a";
}

async function validatePhoto(file: File) {
  const header = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  if (!hasExpectedPhotoSignature(file.type, header)) {
    throw new Error("That file does not match its image format.");
  }

  let width = 0;
  let height = 0;
  if (typeof createImageBitmap === "function") {
    const bitmap = await createImageBitmap(file);
    try {
      width = bitmap.width;
      height = bitmap.height;
    } finally {
      bitmap.close();
    }
  } else {
    const objectUrl = URL.createObjectURL(file);
    try {
      const image = new Image();
      image.src = objectUrl;
      if (typeof image.decode === "function") {
        await image.decode();
      } else {
        await new Promise<void>((resolve, reject) => {
          image.onload = () => resolve();
          image.onerror = () => reject(new Error("That photo could not be decoded."));
        });
      }
      width = image.naturalWidth;
      height = image.naturalHeight;
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
  }

  if (
    width <= 0 ||
    height <= 0 ||
    width > MAX_PHOTO_EDGE ||
    height > MAX_PHOTO_EDGE ||
    width * height > MAX_PHOTO_PIXELS
  ) {
    throw new Error("Choose a photo up to 6000 px per side and 24 megapixels.");
  }
}

function readPhoto(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () =>
      typeof reader.result === "string"
        ? resolve(reader.result)
        : reject(new Error("That photo could not be read."));
    reader.onerror = () => reject(new Error("That photo could not be read."));
    reader.readAsDataURL(file);
  });
}

function formatTimestamp(timestampMs: number) {
  return `${(timestampMs / 1000).toFixed(1)}s`;
}

export function PawSpectiveShell({
  initialEvents,
}: {
  initialEvents: SceneEvent[];
}) {
  const [stage, setStage] =
    useState<Stage>("profile");
  const [profile, setProfile] =
    useState(defaultProfile);
  const [visionMix, setVisionMix] = useState(72);
  const [events, setEvents] =
    useState(initialEvents);
  const [selectedEventId, setSelectedEventId] =
    useState(
      initialEvents[0]?.event_id ?? "",
    );
  const [accuracyOpen, setAccuracyOpen] =
    useState(false);
  const [photoError, setPhotoError] =
    useState<string | null>(null);
  const [capturedClip, setCapturedClip] =
    useState<CapturedClip | null>(null);
  const [analysisError, setAnalysisError] =
    useState<string | null>(null);
  const [analysisSource, setAnalysisSource] =
    useState<AnalysisSource | null>(null);
  const [analysisWarnings, setAnalysisWarnings] = useState<string[]>([]);
  const [isLoadingDemo, setIsLoadingDemo] = useState(false);
  const [isRecording, setIsRecording] =
    useState(false);

  const [
    visibilityScores,
    setVisibilityScores,
  ] = useState<VisibilityScore[]>([]);
  const [
    visibilityWarnings,
    setVisibilityWarnings,
  ] = useState<string[]>([]);
  const [
    visibilityError,
    setVisibilityError,
  ] = useState<string | null>(null);
  const [isScoring, setIsScoring] =
    useState(false);

  const visibilityRequestIdRef =
    useRef(0);
  const visibilityAbortControllerRef =
    useRef<AbortController | null>(null);

  const [storyResult, setStoryResult] =
    useState<StoryReelResult | null>(null);
  const [storyError, setStoryError] =
    useState<string | null>(null);
  const [
    isRenderingStory,
    setIsRenderingStory,
  ] = useState(false);
  const [storyProgress, setStoryProgress] =
    useState(0);
  const [animationProvider, setAnimationProvider] =
    useState<AnimationProvider>("gemini_omni");

  const storyRequestIdRef = useRef(0);
  const storyAbortControllerRef =
    useRef<AbortController | null>(null);
  const usedVariationIdsRef = useRef(new Set<string>());
  const lastAnimationSeedRef = useRef<number | null>(null);
  const photoRequestIdRef = useRef(0);
  const accuracyCloseRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const [colorSimulation, setColorSimulation] =
    useState<ColorSimulationResponse | null>(null);
  const [colorSimulationError, setColorSimulationError] =
    useState<string | null>(null);
  const [isSimulatingColor, setIsSimulatingColor] =
    useState(false);

  const colorRequestIdRef = useRef(0);
  const colorAbortControllerRef =
    useRef<AbortController | null>(null);

  function invalidateColorSimulation() {
    colorRequestIdRef.current += 1;
    colorAbortControllerRef.current?.abort();
    colorAbortControllerRef.current = null;

    setIsSimulatingColor(false);
    setColorSimulation(null);
    setColorSimulationError(null);
  }

  function invalidateStoryReel() {
    storyRequestIdRef.current += 1;
    storyAbortControllerRef.current?.abort();
    storyAbortControllerRef.current = null;

    setIsRenderingStory(false);
    setStoryProgress(0);
    setStoryResult(null);
    setStoryError(null);
  }

  function invalidateVisibilityScores() {
    invalidateColorSimulation();
    invalidateStoryReel();

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

      storyRequestIdRef.current += 1;
      storyAbortControllerRef.current?.abort();

      colorRequestIdRef.current += 1;
      colorAbortControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!accuracyOpen) return;

    previousFocusRef.current = document.activeElement as HTMLElement | null;
    const focusDrawer = () => accuracyCloseRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setAccuracyOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const drawer = accuracyCloseRef.current?.closest("aside");
      const focusable = drawer?.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    queueMicrotask(focusDrawer);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [accuracyOpen]);

  function updateProfile<
    K extends keyof Profile,
  >(
    key: K,
    value: Profile[K],
  ) {
    setProfile((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function togglePersonality(
    personality: string,
  ) {
    setProfile((current) => {
      const selected =
        current.personalities.includes(
          personality,
        );

      if (selected) {
        return {
          ...current,
          personalities:
            current.personalities.filter(
              (item) =>
                item !== personality,
            ),
        };
      }

      if (
        current.personalities.length >= 2
      ) {
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

  async function handlePhoto(
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    const requestId = photoRequestIdRef.current + 1;
    photoRequestIdRef.current = requestId;
    setPhotoError(null);

    if (!file) return;
    if (!PHOTO_TYPES.has(file.type)) {
      setPhotoError("Choose a JPG, PNG, WebP, or GIF image.");
      input.value = "";
      return;
    }
    if (file.size > MAX_PHOTO_BYTES) {
      setPhotoError("Choose a dog photo smaller than 5 MB.");
      input.value = "";
      return;
    }

    try {
      await validatePhoto(file);
      const photo = await readPhoto(file);
      if (photoRequestIdRef.current === requestId) {
        updateProfile("photo", photo);
      }
    } catch (error) {
      if (photoRequestIdRef.current === requestId) {
        setPhotoError(
          error instanceof Error
            ? error.message
            : "That photo could not be read. Try another image.",
        );
        input.value = "";
      }
    }
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
    setAnalysisError(null);
    setAnalysisWarnings([]);
    setAnalysisSource(null);
    setEvents([]);
    setSelectedEventId("");
    usedVariationIdsRef.current.clear();
    lastAnimationSeedRef.current = null;
    invalidateVisibilityScores();
  }

  function selectEvent(
    eventId: string,
  ) {
    invalidateColorSimulation();
    invalidateStoryReel();
    setSelectedEventId(eventId);
  }

  async function analyzeClip(clip: CapturedClip) {
    setCapturedClip(clip);
    setAnalysisError(null);
    setAnalysisWarnings([]);
    setAnalysisSource(null);
    setStage("processing");

    invalidateVisibilityScores();

    try {
      const response =
        await analyzeCapturedClip(
          clip,
        );

      setEvents(response.analysis.events);
      setSelectedEventId(
        response.analysis.events[0]
          ?.event_id ?? "",
      );
      setAnalysisSource(response.source);
      setAnalysisWarnings(response.analysis.warnings);
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

  async function beginSceneAnalysis() {
    if (capturedClip) {
      await analyzeClip(capturedClip);
    }
  }

  async function beginControlledDemo() {
    setIsLoadingDemo(true);
    setAnalysisError(null);

    try {
      const demo = await loadControlledDemo();

      setProfile({
        ownerName: demo.profile.owner_name,
        dogName: demo.profile.dog_name,
        breed: demo.profile.breed,
        age: demo.profile.age,
        size: demo.profile.size,
        personalities: demo.profile.personality_tags,
        favorite: demo.profile.favorite_interest,
        photo: "",
      });

      await analyzeClip(demo.clip);
    } catch (error) {
      setAnalysisError(
        error instanceof Error
          ? error.message
          : "The rehearsal demo could not be loaded.",
      );
      setStage("lens");
    } finally {
      setIsLoadingDemo(false);
    }
  }

  async function calculateVisibility() {
    if (
      !capturedClip ||
      events.length === 0
    ) {
      return;
    }

    if (
      analysisSource !== "gemini" &&
      analysisSource !== "controlled_demo"
    ) {
      setVisibilityError(
        "Cached demo detections cannot be measured against this video. Run real Gemini analysis first.",
      );
      return;
    }

    invalidateColorSimulation();
    invalidateStoryReel();
    visibilityAbortControllerRef.current?.abort();

    const requestId =
      visibilityRequestIdRef.current + 1;
    const abortController =
      new AbortController();

    visibilityRequestIdRef.current =
      requestId;
    visibilityAbortControllerRef.current =
      abortController;

    setIsScoring(true);
    setVisibilityScores([]);
    setVisibilityError(null);
    setVisibilityWarnings([]);

    try {
      const response =
        await scoreCapturedClip(
          capturedClip,
          events.map((event) => ({
            ...event,
            object_label:
              event.object_label.trim(),
          })),
          profile.favorite,
          abortController.signal,
          analysisSource,
        );

      if (
        requestId !==
          visibilityRequestIdRef.current ||
        abortController.signal.aborted
      ) {
        return;
      }

      setVisibilityScores(
        response.scores,
      );
      setVisibilityWarnings(
        response.warnings,
      );

      if (analysisSource === "controlled_demo") {
        const featured = response.scores.reduce(
          (best, score) =>
            !best || score.dog_contrast_score > best.dog_contrast_score
              ? score
              : best,
          response.scores[0],
        );

        if (featured) {
          setSelectedEventId(featured.event_id);
        }
      }
    } catch (error) {
      if (
        requestId !==
          visibilityRequestIdRef.current ||
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
      if (
        requestId ===
        visibilityRequestIdRef.current
      ) {
        visibilityAbortControllerRef.current =
          null;
        setIsScoring(false);
      }
    }
  }

  async function createStoryReel() {
    if (
      !capturedClip ||
      (analysisSource !== "gemini" &&
        analysisSource !== "controlled_demo") ||
      visibilityScores.length === 0 ||
      !selectedEventId
    ) {
      return;
    }

    const selectedHasScore =
      visibilityScores.some(
        (score) =>
          score.event_id ===
          selectedEventId,
      );

    if (!selectedHasScore) {
      setStoryError(
        "Select an object that has a completed visibility score.",
      );
      return;
    }

    storyAbortControllerRef.current?.abort();

    const requestId =
      storyRequestIdRef.current + 1;
    const abortController =
      new AbortController();

    storyRequestIdRef.current =
      requestId;
    storyAbortControllerRef.current =
      abortController;

    setIsRenderingStory(true);
    setStoryProgress(0);
    setStoryResult(null);
    setStoryError(null);

    try {
      const result =
        await renderCapturedStoryReel(
          capturedClip,
          events,
          visibilityScores,
          selectedEventId,
          {
            owner_name:
              profile.ownerName,
            dog_name:
              profile.dogName ||
              "Co-pilot",
            breed: profile.breed,
            age: profile.age,
            size: profile.size,
            personality_tags:
              profile.personalities,
            favorite_interest:
              profile.favorite,
          },
          abortController.signal,
          setStoryProgress,
          analysisSource,
          (() => {
            const cachedOriginal =
              analysisSource === "controlled_demo" &&
              usedVariationIdsRef.current.size === 0;
            let variationId = cachedOriginal
              ? "original"
              : globalThis.crypto?.randomUUID?.().replaceAll("-", "") ??
                `variation-${Date.now()}-${usedVariationIdsRef.current.size}`;
            while (usedVariationIdsRef.current.has(variationId)) {
              variationId = `${variationId}-${usedVariationIdsRef.current.size + 1}`;
            }
            usedVariationIdsRef.current.add(variationId);
            let animationSeed = cachedOriginal
              ? 0
              : globalThis.crypto?.getRandomValues
                ? globalThis.crypto.getRandomValues(new Uint32Array(1))[0] & 0x7fffffff
                : (Date.now() + usedVariationIdsRef.current.size) & 0x7fffffff;
            if (
              lastAnimationSeedRef.current !== null &&
              animationSeed % 3 === lastAnimationSeedRef.current % 3
            ) {
              animationSeed = (animationSeed + 1) & 0x7fffffff;
            }
            lastAnimationSeedRef.current = animationSeed;
            return { variationId, animationSeed };
          })(),
          animationProvider,
        );

      if (
        requestId !==
          storyRequestIdRef.current ||
        abortController.signal.aborted
      ) {
        return;
      }

      setStoryResult(result);
    } catch (error) {
      if (
        requestId !==
          storyRequestIdRef.current ||
        abortController.signal.aborted ||
        (error instanceof DOMException &&
          error.name === "AbortError")
      ) {
        return;
      }

      setStoryError(
        error instanceof Error
          ? error.message
          : "Story Reel generation failed.",
      );
    } finally {
      if (
        requestId ===
        storyRequestIdRef.current
      ) {
        storyAbortControllerRef.current =
          null;
        setIsRenderingStory(false);
      }
    }
  }

  async function calculateColorSimulation() {
    if (
      !capturedClip ||
      !selectedEvent ||
      (analysisSource !== "gemini" &&
        analysisSource !== "controlled_demo")
    ) {
      return;
    }

    const selectedHasScore = visibilityScores.some(
      (score) => score.event_id === selectedEvent.event_id,
    );

    if (!selectedHasScore) {
      setColorSimulationError(
        "Calculate visibility for this object before comparing colors.",
      );
      return;
    }

    colorAbortControllerRef.current?.abort();

    const requestId = colorRequestIdRef.current + 1;
    const abortController = new AbortController();

    colorRequestIdRef.current = requestId;
    colorAbortControllerRef.current = abortController;
    setIsSimulatingColor(true);
    setColorSimulation(null);
    setColorSimulationError(null);

    try {
      const response = await simulateCapturedObjectColors(
        capturedClip,
        selectedEvent,
        abortController.signal,
        analysisSource,
      );

      if (
        requestId !== colorRequestIdRef.current ||
        abortController.signal.aborted
      ) {
        return;
      }

      setColorSimulation(response);
    } catch (error) {
      if (
        requestId !== colorRequestIdRef.current ||
        abortController.signal.aborted ||
        (error instanceof DOMException && error.name === "AbortError")
      ) {
        return;
      }

      setColorSimulationError(
        error instanceof Error
          ? error.message
          : "Toy Color Lab simulation failed.",
      );
    } finally {
      if (requestId === colorRequestIdRef.current) {
        colorAbortControllerRef.current = null;
        setIsSimulatingColor(false);
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

  function removeEvent(
    eventId: string,
  ) {
    invalidateVisibilityScores();

    setEvents((current) => {
      const remaining = current.filter(
        (event) =>
          event.event_id !== eventId,
      );

      if (
        selectedEventId === eventId
      ) {
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
    (event) =>
      event.event_id ===
      selectedEventId,
  );

  const selectedVisibilityScore =
    visibilityScores.find(
      (score) =>
        score.event_id ===
        selectedEventId,
    );

  const isResultsBusy =
    isScoring || isRenderingStory || isSimulatingColor;

  return (
    <>
      <main
        className="app-shell"
        aria-hidden={accuracyOpen ? "true" : undefined}
        inert={accuracyOpen}
      >
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
          <PawSpectiveLogo compact />

          <span>
            <strong>
              PawSpective
            </strong>

            <small>
              Closer to their point of
              view
            </small>
          </span>
        </button>

        <div className="topbar-actions">
          <span className="status-badge">
            Reliable by design
          </span>

          <button
            className="text-button"
            type="button"
            onClick={() =>
              setAccuracyOpen(true)
            }
          >
            How accurate is this?
          </button>
        </div>
      </header>

      <nav
        className="progress"
        aria-label="Experience progress"
      >
        {stages.map(
          (item, index) => {
            const completed =
              index < stageIndex;
            const active =
              item.id === stage;

            return (
              <div
                className={[
                  "progress-step",
                  active
                    ? "active"
                    : "",
                  completed
                    ? "completed"
                    : "",
                ].join(" ")}
                key={item.id}
              >
                <span>
                  {completed
                    ? "✓"
                    : index + 1}
                </span>

                <small>
                  {item.label}
                </small>
              </div>
            );
          },
        )}
      </nav>

      {stage === "profile" && (
        <section className="screen profile-screen">
          <div className="intro-copy">
            <p className="eyebrow">
              Tell us about your
              co-pilot
            </p>

            <h1>
              Meet the world from a
              slightly more{" "}
              <em>dog-shaped</em>{" "}
              perspective.
            </h1>

            <p className="lead">
              We use size to guide camera
              height. Personality and
              favorites personalize Story
              Mode—they never alter the
              scientific vision filter.
            </p>

            <button
              className="accuracy-card"
              type="button"
              onClick={() =>
                setAccuracyOpen(true)
              }
            >
              <span>◉</span>

              <span>
                <strong>
                  Science and imagination
                  stay separate
                </strong>

                <small>
                  See what is measured and what is fictional
                </small>
              </span>
            </button>

            <div className="how-it-works" aria-label="How it works">
              <strong>How it works</strong>
              <ol>
                <li><span>1</span>Create a dog profile.</li>
                <li><span>2</span>Record or upload a 5–15 second moment.</li>
                <li><span>3</span>Review objects, compare visibility, and make a sketch reel.</li>
              </ol>
            </div>
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
                  aria-label="Dog photo"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  onChange={(event) => void handlePhoto(event)}
                />
              </label>

              <div>
                <strong>
                  Dog photo
                </strong>

                <small>
                  Optional · stays in this browser and is never sent for story generation
                </small>
              </div>
            </div>

            {photoError && (
              <p className="field-error" role="alert">
                {photoError}
              </p>
            )}

            <p className="context-note" role="note">
              Your photo stays in this browser. Profile text is sent to the
              PawSpective backend; dog details may be shared with Gemini for
              live story framing and included in narration sent to ElevenLabs
              for voice synthesis. Your first name is sent to neither provider.
            </p>

            <div className="field-grid">
              <label>
                Your first name

                <input
                  required
                  value={
                    profile.ownerName
                  }
                  onChange={(event) =>
                    updateProfile(
                      "ownerName",
                      event.target.value.slice(0, 60),
                    )
                  }
                  maxLength={60}
                  autoComplete="given-name"
                  placeholder="Alex"
                />
              </label>

              <label>
                Dog&apos;s name

                <input
                  required
                  value={
                    profile.dogName
                  }
                  onChange={(event) =>
                    updateProfile(
                      "dogName",
                      event.target.value.slice(0, 40),
                    )
                  }
                  maxLength={40}
                  autoComplete="off"
                  placeholder="Bruno"
                />
              </label>
            </div>

            <label>
              Breed or mix

              <input
                maxLength={80}
                value={profile.breed}
                onChange={(event) =>
                  updateProfile(
                    "breed",
                    event.target.value.slice(0, 80),
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
                  <option>
                    Puppy
                  </option>
                  <option>
                    Adult
                  </option>
                  <option>
                    Senior
                  </option>
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
                  <option>
                    Small
                  </option>
                  <option>
                    Medium
                  </option>
                  <option>
                    Large
                  </option>
                </select>
              </label>
            </div>

            <fieldset>
              <legend>
                Personality{" "}

                <span>
                  Choose up to two
                </span>
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
                        aria-pressed={
                          selected
                        }
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
                value={
                  profile.favorite
                }
                onChange={(event) =>
                  updateProfile(
                    "favorite",
                    event.target.value,
                  )
                }
              >
                {favoriteOptions.map(
                  (favorite) => (
                    <option
                      key={favorite}
                    >
                      {favorite}
                    </option>
                  ),
                )}
              </select>
            </label>

            <button
              className="primary-button"
              type="submit"
            >
              Meet my co-pilot{" "}
              <span>→</span>
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
                {profile.dogName ||
                  "co-pilot"}
                .
              </h1>
            </div>

            <button
              className="secondary-button"
              type="button"
              disabled={
                isRecording ||
                isResultsBusy
              }
              onClick={() =>
                setStage("profile")
              }
            >
              Edit profile
            </button>
          </div>

          <div className="lens-layout">
            <LiveDogLens
              visionMix={visionMix}
              onVisionMixChange={
                setVisionMix
              }
              onClipChange={
                handleClipChange
              }
              onRecordingChange={
                setIsRecording
              }
            />

            <aside className="lens-sidebar">
              <div className="profile-summary">
                <span className="profile-avatar">
                  {profile.photo ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={
                        profile.photo
                      }
                      alt=""
                    />
                  ) : (
                    "🐕"
                  )}
                </span>

                <div>
                  <p>
                    Meet{" "}
                    {profile.dogName ||
                      "your dog"}
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
                    Position it
                    approximately at your
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
                    This is an approximate
                    point of view—not gaze
                    tracking.
                  </p>
                </div>
              </div>

              <div className="mock-notice">
                Record or upload a short
                clip. Gemini identifies
                visibly supported objects.
                After reviewing them, you
                can calculate deterministic
                visibility and Curiosity
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
                  isResultsBusy ||
                  capturedClip.durationMs <
                    5_000 ||
                  capturedClip.durationMs >
                    15_000
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

          <h1>
            Finding visible scene
            signals…
          </h1>

          <p className="lead">
            We&apos;re checking the clip and finding clearly visible objects.
            Your original media stays temporary and is cleaned up after processing.
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
                {profile.dogName ||
                  "Your dog"}
                &apos;s visible scene
              </h1>
            </div>

            <button
              className="secondary-button"
              type="button"
              disabled={isResultsBusy}
              onClick={() => {
                setCapturedClip(null);
                setAnalysisError(null);
                setAnalysisSource(null);
                setAnalysisWarnings([]);
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
              Live scene analysis could not complete. Validated cached
              detections are shown below; check the detailed warning before
              continuing.
            </div>
          )}

          {analysisSource === "controlled_demo" && (
            <div className="controlled-demo-notice">
              Rehearsal mode is using the exact verified demo clip and its saved
              analysis. You can rename labels; the measured scene stays locked.
            </div>
          )}

          {analysisWarnings.length > 0 && (
            <div className="score-warnings" role="status">
              {analysisWarnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </div>
          )}

          {events.length === 0 && (
            <section className="empty-analysis-card">
              <h2>No useful visible objects detected</h2>
              <p>
                Try a brighter, steadier 5–15 second clip, or use the
                controlled rehearsal so the demonstration can continue.
              </p>
              <div>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setStage("lens")}
                >
                  Try another clip
                </button>
                <button
                  className="primary-button"
                  type="button"
                  disabled={isLoadingDemo}
                  onClick={() => void beginControlledDemo()}
                >
                  Use controlled demo
                </button>
              </div>
            </section>
          )}

          {events.length > 0 && <div className="results-grid">
            <section className="result-card object-review">
              <div className="card-heading">
                <div>
                  <span className="label ai">
                    AI-inferred
                  </span>

                  <h2>
                    Review detected
                    objects
                  </h2>
                </div>

                <span>
                  {events.length} objects
                </span>
              </div>

              <p>
                Rename or remove anything
                incorrect. Your corrections
                become the source of truth.
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
                      disabled={
                        isResultsBusy
                      }
                      onChange={() =>
                        selectEvent(
                          event.event_id,
                        )
                      }
                    />

                    <div>
                      <input
                        className="event-name"
                        value={
                          event.object_label
                        }
                        disabled={
                          isResultsBusy
                        }
                        onChange={(
                          changeEvent,
                        ) =>
                          renameEvent(
                            event.event_id,
                            changeEvent
                              .target.value,
                          )
                        }
                        onBlur={(
                          blurEvent,
                        ) =>
                          renameEvent(
                            event.event_id,
                            blurEvent
                              .target.value
                              .trim(),
                          )
                        }
                      />

                      <small>
                        {formatTimestamp(
                          event.timestamp_ms,
                        )}{" "}
                        ·{" "}
                        {Math.round(
                          event.confidence *
                            100,
                        )}
                        % confidence
                      </small>
                    </div>

                    <button
                      type="button"
                      aria-label={`Remove ${event.object_label}`}
                      disabled={
                        isResultsBusy
                      }
                      onClick={() =>
                        removeEvent(
                          event.event_id,
                        )
                      }
                    >
                      Remove
                    </button>
                  </div>
                ))}

                {events.length === 0 && (
                  <p className="empty-state">
                    No objects remain.
                    Return to Dog Lens to
                    analyze another clip.
                  </p>
                )}
              </div>

              <button
                className="primary-button"
                type="button"
                disabled={
                  isResultsBusy ||
                  events.length === 0 ||
                  (analysisSource !== "gemini" &&
                    analysisSource !== "controlled_demo")
                }
                onClick={() =>
                  void calculateVisibility()
                }
              >
                {isScoring
                  ? "Calculating visibility…"
                  : "Calculate visibility & curiosity"}
              </button>

              {analysisSource ===
                "demo" && (
                <p className="context-note">
                  Cached example markers do not match this uploaded clip.
                  Run live analysis or use the verified rehearsal clip.
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

              {visibilityWarnings.length >
                0 && (
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
                    AI boxes +
                    deterministic weighting
                  </span>

                  <h2>
                    Curiosity Map
                  </h2>
                </div>
              </div>

              {capturedClip ? (
                <CuriosityMap
                  clip={capturedClip}
                  events={events}
                  scores={
                    visibilityScores
                  }
                  selectedEventId={
                    selectedEventId
                  }
                  onSelect={
                    selectEvent
                  }
                />
              ) : (
                <p>
                  The original clip is
                  unavailable.
                </p>
              )}
            </section>

            <section className="result-card visibility-card">
              <div className="card-heading">
                <div>
                  <span className="label science">
                    Measured +
                    AI-labeled inputs
                  </span>

                  <h2>
                    Visibility insight
                  </h2>
                </div>

                {selectedVisibilityScore && (
                  <span>
                    {
                      selectedVisibilityScore
                        .salience_score
                    }
                    /100 cue score
                  </span>
                )}
              </div>

              <VisibilityInsight
                event={selectedEvent}
                score={
                  selectedVisibilityScore
                }
              />
            </section>

            <section className="result-card color-lab-card">
              <div className="card-heading">
                <div>
                  <span className="label science">
                    Deterministic simulation
                  </span>
                  <h2>Toy Color Lab</h2>
                </div>

                {colorSimulation && <span>Fixed six-color palette</span>}
              </div>

              <div className="demo-backup-card">
                <strong>Rehearsal recovery</strong>
                <p>
                  Load the verified clip, analysis, profile, audio, and reel
                  when venue connectivity is unreliable.
                </p>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={isLoadingDemo || isRecording || isResultsBusy}
                  onClick={() => void beginControlledDemo()}
                >
                  {isLoadingDemo
                    ? "Loading rehearsal…"
                    : "Use controlled demo"}
                </button>
              </div>

              {capturedClip && selectedEvent ? (
                <ToyColorLab
                  clip={capturedClip}
                  event={selectedEvent}
                  result={colorSimulation}
                  isLoading={isSimulatingColor}
                  error={colorSimulationError}
                  disabled={
                    (analysisSource !== "gemini" &&
                      analysisSource !== "controlled_demo") ||
                    !selectedVisibilityScore ||
                    isScoring ||
                    isRenderingStory
                  }
                  disabledReason={
                    !selectedVisibilityScore
                      ? "Calculate visibility for the selected object first."
                      : isScoring || isRenderingStory
                        ? "Wait for the current task to finish."
                        : undefined
                  }
                  onSimulate={() => void calculateColorSimulation()}
                />
              ) : (
                <p>Select a scored object to compare simulated colors.</p>
              )}
            </section>

            <section className="result-card story-card">
              <div className="card-heading">
                <div>
                  <span className="label fun">
                    Just for fun
                  </span>

                  <h2>
                    Story Reel
                  </h2>
                </div>
              </div>

              <StoryReel
                dogName={
                  profile.dogName
                }
                result={storyResult}
                isRendering={
                  isRenderingStory
                }
                progress={storyProgress}
                error={storyError}
                disabled={
                  (analysisSource !== "gemini" &&
                    analysisSource !== "controlled_demo") ||
                  visibilityScores.length === 0 ||
                  isScoring ||
                  isSimulatingColor
                }
                disabledReason={
                  visibilityScores.length === 0
                    ? "Review the objects and calculate visibility first."
                    : isScoring || isSimulatingColor
                      ? "Wait for the current calculation to finish."
                      : undefined
                }
                animationProvider={animationProvider}
                onAnimationProviderChange={(provider) => {
                  invalidateStoryReel();
                  setAnimationProvider(provider);
                }}
                onRender={() =>
                  void createStoryReel()
                }
              />
            </section>
          </div>}
        </section>
      )}

      <footer>
        <span>PawSpective</span>

        <p>
          Fun enough to share.
          Transparent enough to trust.
        </p>
      </footer>
      </main>

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
              ref={accuracyCloseRef}
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
              How PawSpective reaches a
              result
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
                  Canine color transformation, foreground/background
                  sampling, relative contrast calculations, deterministic
                  weighting, and fixed-palette Toy Color Lab comparisons.
                </p>
              </div>
            </div>

            <div className="accuracy-section">
              <span className="accuracy-icon ai">
                ~
              </span>

              <div>
                <strong>
                  AI-inferred
                </strong>

                <p>
                  Object identification, bounding boxes, ordinal motion
                  labels, and possible visible attention cues. The Toy Color
                  Lab uses the selected AI bounding box.
                </p>
              </div>
            </div>

            <div className="accuracy-section">
              <span className="accuracy-icon fun">
                ✦
              </span>

              <div>
                <strong>
                  Just for fun
                </strong>

                <p>
                  Fictional first-person dog narration and playful story framing.
                  It is entertainment—not actual dog thoughts.
                </p>
              </div>
            </div>

            <div className="accuracy-warning">
              PawSpective never claims to
              read a dog&apos;s exact gaze,
              thoughts, feelings or sense
              of smell.
            </div>

            <div className="accuracy-warning">
              Toy Color Lab previews tint an entire bounding box for
              illustration. They are not object segmentation and do not
              predict the appearance of a physical product under every
              lighting condition.
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
