# Phase 5 deployment guide

## Backend secrets

Configure these only in the backend hosting environment:

```dotenv
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.6-flash
ELEVENLABS_API_KEY=...
ELEVENLABS_DOG_VOICE_ID=...
ELEVENLABS_MODEL_ID=eleven_flash_v2_5
PAWSPECTIVE_DEMO_MODE=false
PAWSPECTIVE_ALLOW_DEMO_FALLBACK=true
PAWSPECTIVE_CORS_ORIGINS=https://your-frontend-domain
```

The Gemini and ElevenLabs secrets must never use a `NEXT_PUBLIC_` prefix.

## Frontend environment

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain
```

## Runtime requirements

- FFmpeg and FFprobe must be available on `PATH`.
- The service must permit temporary-file creation in
  `PAWSPECTIVE_MEDIA_DIRECTORY`.
- Request and load-balancer timeouts must exceed the 45-second target.
- Response limits must permit the generated MP4.
- CORS must expose `X-PawSpective-Story-Source`.
- HTTPS is required for deployed camera access.

## Post-deployment verification

1. Call `/api/v1/health` and confirm `demo_mode` is false.
2. Run the complete profile, capture, analysis, correction, scoring and Story
   Reel journey with a real clip.
3. Download the reel and inspect it with:

```powershell
ffprobe `
  -v error `
  -show_entries format=duration `
  -show_entries stream=index,codec_name,codec_type,width,height,pix_fmt,display_aspect_ratio `
  -of json `
  path\to\downloaded-reel.mp4
```

4. Confirm temporary source, narration and output files are removed after the
   request finishes.
5. Complete `docs/phase-5-acceptance-checklist.md` on the deployed application.
