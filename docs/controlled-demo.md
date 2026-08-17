# Controlled demo

The controlled demo keeps a verified rehearsal available when venue internet
or external AI services are unreliable. Cached detections are accepted only
when the uploaded video bytes match the cache manifest SHA-256 fingerprint.

## Record the source

Record `demo-source/controlled-demo-original.mp4` as a stable 5–15 second,
under-30 MB clip containing:

- one clearly visible red toy;
- one clearly visible blue toy;
- grass or another green background;
- one moving subject, optionally with a cat;
- bright, even light and minimal camera shake.

The source clip is ignored by Git. Keep a separate backup.

## Build the cache

Configure real Gemini and ElevenLabs credentials, then run from the repository
root:

```powershell
$env:PAWSPECTIVE_DEMO_MODE = "false"
$env:PAWSPECTIVE_ALLOW_DEMO_FALLBACK = "false"
.\.venv\Scripts\python.exe scripts\build_demo_cache.py --force
```

The builder normalizes the clip, requires real Gemini analysis, validates the
controlled scene, calculates visibility, generates narration, renders the
portrait reel, and writes the exact request and manifest to `demo_cache/`.

Deploy every generated file in `demo_cache/`, then set:

```dotenv
PAWSPECTIVE_CONTROLLED_DEMO_ENABLED=true
```

The backend readiness endpoint returns `503` when this setting is enabled and
the cache is missing or incomplete.

## Rehearse

1. Complete the profile or choose **Use controlled demo**.
2. Show the Dog Lens and camera/upload recovery.
3. Analyze and review detected objects.
4. Calculate visibility and compare the red and blue objects.
5. Open Toy Color Lab.
6. Generate the Story Reel and confirm cached playback works offline.
7. Repeat the complete demonstration twice without developer intervention.
