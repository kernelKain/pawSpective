# Phase 8 demo rehearsal

Phase 8 makes the three-minute demonstration recoverable when camera access,
AI output, text-to-speech, rendering, or venue connectivity fails. The normal
product path remains live; the controlled path is accepted only when the
uploaded bytes match the cache manifest SHA-256 fingerprint.

## 1. Record the source

Record `demo-source/controlled-demo-original.mp4` as a stable 5–15 second,
landscape, under-30 MB clip containing:

- one clearly visible red toy;
- one clearly visible blue toy;
- grass or another green background;
- one moving subject, optionally with a cat;
- bright, even light and minimal camera shake.

The source clip is ignored by Git. Keep a separate backup of it.

## 2. Build the offline cache

Configure real Gemini and ElevenLabs credentials, then run from the repository
root:

```powershell
$env:PAWSPECTIVE_DEMO_MODE = "false"
$env:PAWSPECTIVE_ALLOW_DEMO_FALLBACK = "false"
.\.venv\Scripts\python.exe scripts\build_demo_cache.py --force
```

The builder normalizes the clip, requires real Gemini analysis, checks for red
and blue labels plus a medium/high-motion event, calculates visibility, selects
the strongest dog-contrast event, generates narration, renders the portrait
reel, and writes the exact request and manifest to `demo_cache/`.

Commit or otherwise deploy every generated file in `demo_cache/`. Docker copies
that directory into the backend image. `/api/v1/health/ready` reports 503 when
controlled-demo support is enabled but the cache is incomplete.

## 3. Verify normal and failure paths

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest
Set-Location frontend
npm.cmd run lint
npm.cmd test -- --run
npm.cmd run build
```

Manually exercise camera permission denial, an unsupported browser, portrait
and landscape uploads, no profile photo, malformed Gemini output, no useful
objects, an ElevenLabs timeout, a render failure, very dark footage, and red
and blue toys on grass. Error messages must not expose local paths.

## 4. Rehearse the three-minute flow

1. Complete the profile or choose **Use controlled demo**.
2. Show the Dog Lens and explain camera upload recovery.
3. Analyze and review detected objects.
4. Calculate visibility and compare the red and blue objects.
5. Open Toy Color Lab.
6. Generate Story Reel; a matching controlled request returns the cached reel
   without Gemini, ElevenLabs, or rendering.
7. Repeat the entire demonstration twice consecutively with no developer
   intervention.

The Phase 8 exit gate is met only after both consecutive rehearsals succeed.
