# PawSpective

See the world closer to how your dog sees it. PawSpective combines a
canine-vision approximation, reviewed AI scene analysis, deterministic
visibility scoring, color comparison, curiosity mapping, and downloadable
fictional Story Reels.

## What it does

- Opens a live Human/Dog Vision comparison or accepts a 5–15 second video.
- Detects visible objects with Gemini and lets the user correct the result.
- Measures foreground/background contrast with OpenCV and CIE Lab color.
- Shows possible attention cues in a timestamp-aligned Curiosity Map.
- Compares six screen colors in Toy Color Lab.
- Creates a 15–25 second vertical MP4 with a predefined fictional voice.
- Supports a SHA-256-bound controlled demo for offline rehearsals.

PawSpective labels deterministic calculations as **Research-grounded**,
model interpretation as **AI-inferred**, and fictional output as
**Just for fun**. It does not claim exact canine vision, gaze, thoughts,
emotions, smell, or behavioral diagnosis.

## Architecture

- `frontend/`: Next.js 16 and React 19.
- `backend/`: FastAPI, Pydantic, Gemini, OpenCV, FFmpeg, and ElevenLabs.
- `contracts/`: exported JSON Schemas shared across product boundaries.
- `media/`: local temporary uploads, job state, and generated reels; ignored by Git.

The frontend can run on Vercel. The backend requires FFmpeg, writable
persistent storage, SQLite, and a long-running worker, so deploy it as the
included Docker container on a compatible host.

## Local setup

Prerequisites: Node.js 22, Python 3.13, FFmpeg, and FFprobe.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env

Set-Location frontend
npm ci
Copy-Item .env.example .env.local
Set-Location ..
```

Add Gemini and ElevenLabs credentials to `.env` for live analysis and voice
synthesis. Never commit `.env`, `.env.local`, API keys, or generated media.

Start the backend and frontend in separate terminals:

```powershell
python -m uvicorn backend.app.main:app --reload --port 8000
```

```powershell
Set-Location frontend
npm run dev
```

Open `http://localhost:3000`.

## Configuration

The root `.env.example` documents backend settings. Important deployment
values are:

- `GEMINI_API_KEY`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_DOG_VOICE_ID`
- `PAWSPECTIVE_CORS_ORIGINS`
- `PAWSPECTIVE_CONTROLLED_DEMO_ENABLED`
- `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local` or the Vercel project

Controlled-demo support defaults to off because an empty cache must not make a
fresh backend deployment unhealthy. Enable it only after building and
deploying every verified cache asset.

## Verification

```powershell
Set-Location frontend
npm run lint
npm run test
npm run build
Set-Location ..
python scripts/check_markdown_links.py
python -m pytest backend/tests
```

Real-media tests require FFmpeg and FFprobe. The full test suite validates
upload constraints, malformed AI output, cancellation, visibility scoring,
controlled-demo provenance, narration fallback, rendering, and job lifecycle.

## Documentation

- [Product contract](docs/product-contract.md)
- [Deployment guide](docs/deployment.md)
- [Controlled demo](docs/controlled-demo.md)
- [Release checklist](docs/release-checklist.md)

Released under the [MIT License](LICENSE).
