# PawSpective

See the world closer to how your dog sees it. PawSpective combines a
canine-vision approximation, AI-supported scene analysis, user-reviewed
objects, curiosity mapping, and playful story previews.

## Phase 3 capabilities

- Live camera with a Human/Dog Vision comparison control.
- Five-to-ten-second browser recording or MP4, WebM, MOV, and MKV upload.
- Backend MIME, file-size, and FFprobe duration validation.
- FFmpeg normalization to a compact 720p, 15 FPS MP4.
- Gemini 3.6 Flash scene analysis with strict Pydantic validation.
- Clearly labeled cached demo fallback when Gemini is unavailable.
- User selection, renaming, and removal of detected scene objects.

Visibility scoring and generated story reels remain Phase 4 and Phase 5
features.

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

The backend suite includes a real generated-video FFmpeg test. It is skipped
locally only when FFmpeg is not installed; CI explicitly verifies that both
FFmpeg and FFprobe exist before running the tests.

## Manual Phase 3 acceptance

Before a demo or release, verify the following on the intended devices:

1. Record a clip in desktop Chrome and confirm real Gemini events appear.
2. Record or upload on Android Chrome.
3. Record or upload on iPhone Safari.
4. Use an invalid Gemini key and confirm the result is visibly labeled as a
   cached demo fallback.
5. Confirm short, long, corrupt, and unsupported files show safe errors.
6. Confirm analysis usually completes within the Phase 3 target of 20 seconds.

Never commit `.env`, `.env.local`, API keys, or generated media.
