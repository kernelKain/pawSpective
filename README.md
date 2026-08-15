# PawSpective

See the world closer to how your dog sees it. PawSpective combines a
canine-vision approximation, AI-supported scene analysis, user-reviewed
objects, curiosity mapping, and playful story previews.

## Phase 4 capabilities

- Live camera with a Human/Dog Vision comparison control.
- Five-to-fifteen-second browser recording or MP4, WebM, MOV, and MKV upload.
- Backend MIME, file-size, and FFprobe duration validation.
- FFmpeg normalization to a compact 720p, 15 FPS MP4.
- Gemini 3.6 Flash scene analysis with strict Pydantic validation.
- Clearly labeled cached demo fallback when Gemini is unavailable.
- User selection, renaming, and removal of detected scene objects.
- Frame-level foreground/background sampling from corrected bounding boxes.
- Human and canine-approximation Lab contrast scoring.
- Curiosity scoring with deterministic weights for AI-inferred motion,
  measured contrast, apparent size, and a capped profile bonus.
- A real-video Curiosity Map with timestamp seeking and aligned bounding boxes.
- Visibility Insight with color samples, score breakdowns, and accuracy labels.
- In-flight request cancellation and stale-score protection after navigation or
  object corrections.

Generated and downloadable story reels remain a Phase 5 feature.

## Prerequisites

- Node.js 22
- Python 3.13
- FFmpeg and FFprobe available on `PATH`
- A Gemini API key for live analysis

Confirm the media tools are available:

```powershell
ffmpeg -version
ffprobe -version
```

On Windows, FFmpeg can be installed with:

```powershell
winget install --id Gyan.FFmpeg -e
```

Open a new terminal after installation so the updated `PATH` is loaded.

## Backend setup

From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

For real Gemini analysis, edit `.env`:

```dotenv
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-3.6-flash
PAWSPECTIVE_DEMO_MODE=false
PAWSPECTIVE_ALLOW_DEMO_FALLBACK=true
```

Keep `PAWSPECTIVE_DEMO_MODE=true` to use only the validated cached response.
When fallback is enabled, external Gemini failures return that cached response
with `source: "demo"` instead of presenting it as a real model result.

Start the backend:

```powershell
python -m uvicorn backend.app.main:app --reload --port 8000
```

Temporary uploads and normalized videos are removed after each request.

## Frontend setup

In another PowerShell terminal:

```powershell
Set-Location frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. For a deployed backend, change
`NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local` and add the deployed
frontend origin to `PAWSPECTIVE_CORS_ORIGINS` in the backend environment.

## Verification

Run the full project checks before committing:

```powershell
Set-Location frontend
npm run lint
npm run test
npm run build
Set-Location ..
python -m pytest
```

The backend suite generates a real colored MP4, normalizes it with FFmpeg,
opens and seeks it with OpenCV, and calculates actual Phase 4 visibility
scores. Real-media tests are skipped locally only when FFmpeg is unavailable;
CI explicitly verifies that FFmpeg and FFprobe exist before running tests.

## Manual Phase 4 acceptance

Complete [the Phase 4 acceptance checklist](docs/phase-4-acceptance-checklist.md)
on the actual demo deployment and hardware before calling the phase
release-ready. At minimum:

1. Run a real Gemini result through correction and visibility scoring.
2. Record or upload portrait and landscape clips on desktop Chrome, Android
   Chrome, and iPhone Safari.
3. Confirm every Curiosity Map box remains aligned at desktop and mobile
   widths.
4. Confirm cached demo detections cannot enter visibility scoring.
5. Confirm correcting an event requires recalculation and no late request can
   restore an old score.
6. Record scene-analysis and visibility-scoring latency on the demo hardware.

Never commit `.env`, `.env.local`, API keys, or generated media.
