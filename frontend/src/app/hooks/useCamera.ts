"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

export type CameraStatus =
  | "idle"
  | "requesting"
  | "ready"
  | "denied"
  | "unavailable"
  | "error";

export type FacingMode = "environment" | "user";

type CameraError = {
  status: Exclude<CameraStatus, "idle" | "requesting" | "ready">;
  message: string;
};

type UseCameraResult = {
  videoRef: RefObject<HTMLVideoElement | null>;
  status: CameraStatus;
  errorMessage: string | null;
  facingMode: FacingMode;
  startCamera: (requestedFacingMode?: FacingMode) => Promise<void>;
  switchCamera: () => Promise<void>;
  stopCamera: () => void;
  getStream: () => MediaStream | null;
};

export function describeCameraError(error: unknown): CameraError {
  if (!(error instanceof DOMException)) {
    return {
      status: "error",
      message: "The camera could not be started. Please try again.",
    };
  }

  switch (error.name) {
    case "NotAllowedError":
    case "SecurityError":
      return {
        status: "denied",
        message:
          "Camera access was blocked. Allow camera access in your browser’s site settings, then try again.",
      };

    case "NotFoundError":
      return {
        status: "unavailable",
        message: "No camera was found on this device.",
      };

    case "OverconstrainedError":
      return {
        status: "unavailable",
        message:
          "The requested camera configuration is not available on this device.",
      };

    case "NotReadableError":
      return {
        status: "error",
        message:
          "The camera may already be in use by another application or browser tab.",
      };

    case "AbortError":
      return {
        status: "error",
        message: "Camera startup was interrupted. Please try again.",
      };

    default:
      return {
        status: "error",
        message: "The camera could not be started. Please try again.",
      };
  }
}

export function useCamera(): UseCameraResult {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const getStream = useCallback(
    () => streamRef.current,
    [],
  );

  const [status, setStatus] = useState<CameraStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [facingMode, setFacingMode] =
    useState<FacingMode>("environment");

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, []);

  const stopCamera = useCallback(() => {
    releaseStream();
    setStatus("idle");
    setErrorMessage(null);
  }, [releaseStream]);

  const startCamera = useCallback(
    async (requestedFacingMode: FacingMode = facingMode) => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setStatus("unavailable");
        setErrorMessage(
          "Camera access is unavailable. Open PawSpective through HTTPS or localhost in a supported browser.",
        );
        return;
      }

      releaseStream();
      setStatus("requesting");
      setErrorMessage(null);

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: {
              ideal: requestedFacingMode,
            },
            width: {
              ideal: 1280,
            },
            height: {
              ideal: 720,
            },
            frameRate: {
              ideal: 30,
              max: 60,
            },
          },
        });

        const video = videoRef.current;

        if (!video) {
          stream.getTracks().forEach((track) => track.stop());
          throw new Error("The camera preview is not available.");
        }

        streamRef.current = stream;
        video.srcObject = stream;

        if (video.readyState < HTMLMediaElement.HAVE_METADATA) {
          await new Promise<void>((resolve) => {
            video.addEventListener("loadedmetadata", () => resolve(), {
              once: true,
            });
          });
        }

        await video.play();

        setFacingMode(requestedFacingMode);
        setStatus("ready");
      } catch (error) {
        releaseStream();

        const cameraError = describeCameraError(error);
        setStatus(cameraError.status);
        setErrorMessage(cameraError.message);
      }
    },
    [facingMode, releaseStream],
  );

  const switchCamera = useCallback(async () => {
    const nextFacingMode: FacingMode =
      facingMode === "environment" ? "user" : "environment";

    // Mobile browsers behave more reliably when the old track is stopped
    // before requesting a camera with a different facing mode.
    releaseStream();
    await startCamera(nextFacingMode);
  }, [facingMode, releaseStream, startCamera]);

  useEffect(() => {
    return () => {
      releaseStream();
    };
  }, [releaseStream]);

  return {
    videoRef,
    status,
    errorMessage,
    facingMode,
    startCamera,
    switchCamera,
    stopCamera,
    getStream,
  };
}
