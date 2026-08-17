# Deployment

PawSpective uses two deployable services:

- The Next.js frontend can run on Vercel.
- The FastAPI backend must run on a container host with FFmpeg and persistent
  writable storage. It is not suitable for a short-lived Vercel Function
  because Story Reel jobs use local SQLite, media files, and background work.

## Deploy the backend

Build the included `Dockerfile.backend` and mount persistent storage at
`/data`. Run one worker; the local SQLite job store is not designed for
multiple backend replicas.

Set these production variables on the backend host:

```dotenv
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.6-flash
GEMINI_ANALYSIS_FALLBACK_MODEL=gemini-3.1-flash-lite
ELEVENLABS_API_KEY=...
ELEVENLABS_DOG_VOICE_ID=...
ELEVENLABS_MODEL_ID=eleven_flash_v2_5
PAWSPECTIVE_DEMO_MODE=false
PAWSPECTIVE_ALLOW_DEMO_FALLBACK=true
PAWSPECTIVE_CONTROLLED_DEMO_ENABLED=false
PAWSPECTIVE_CORS_ORIGINS=https://your-project.vercel.app
PAWSPECTIVE_MEDIA_DIRECTORY=/data/media
PAWSPECTIVE_JOBS_DIRECTORY=/data/jobs
PAWSPECTIVE_JOB_DATABASE=/data/jobs.sqlite3
PAWSPECTIVE_ANIMATION_ENABLED=true
PAWSPECTIVE_OMNI_VIDEO_MODEL=gemini-omni-flash-preview
PAWSPECTIVE_VEO_VIDEO_MODEL=veo-3.1-fast-generate-preview
PAWSPECTIVE_ANIMATION_TIMEOUT_SECONDS=420
PAWSPECTIVE_ALLOW_LOCAL_ANIMATION_FALLBACK=true
```

Use comma-separated exact origins for production and preview domains. Do not
use `*` with browser credentials. Confirm readiness after deployment:

```powershell
Invoke-RestMethod https://api.example.com/api/v1/health/ready
```

Enable `PAWSPECTIVE_CONTROLLED_DEMO_ENABLED` only after following the
[controlled-demo guide](controlled-demo.md) and deploying the complete cache.
The backend account must have paid preview access to the selected animation
model. Omni edits the uploaded clip directly; Veo uses three extracted scene
reference frames. Keep all Gemini and ElevenLabs credentials backend-only.

## Deploy the frontend to Vercel

1. Import the repository into Vercel.
2. Set **Root Directory** to `frontend`.
3. Keep the detected Next.js build command and output settings.
4. Set `NEXT_PUBLIC_API_BASE_URL` to the public HTTPS backend origin without a
   trailing slash.
5. Deploy, then add the final Vercel origin to `PAWSPECTIVE_CORS_ORIGINS` on
   the backend and restart it.

The Vercel build intentionally fails when `NEXT_PUBLIC_API_BASE_URL` is
missing. Public variables are embedded at build time, so redeploy after
changing the backend URL.

## Production checks

1. Load the Vercel URL over HTTPS and confirm camera permission can be requested.
2. Open the backend readiness endpoint from the deployed frontend origin.
3. Upload a short clip, review detections, and calculate visibility.
4. Generate, preview, and download a Story Reel.
5. Confirm errors contain no API keys, stack traces, or server file paths.
6. Complete the [release checklist](release-checklist.md).
