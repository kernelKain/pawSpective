# Release checklist

## Automated verification

Run from the repository root:

```powershell
Set-Location frontend
npm ci
npm run lint
npm run test
npm run build
Set-Location ..
python scripts/check_markdown_links.py
python -m pytest backend/tests
```

Confirm the backend container builds and `/api/v1/health/ready` returns `200`
with the intended production environment.

## Browser and device checks

- Desktop Chrome, Android Chrome, and iPhone Safari.
- Camera permission allowed and denied.
- Unsupported camera/browser recovery through upload.
- Portrait and landscape clips with aligned overlays.
- Profile completion without a dog photo.
- Five-second minimum, fifteen-second maximum, and unsupported file handling.
- Loading, cancellation, empty result, retry, and download states.
- Keyboard focus, visible focus styles, dialog escape, and narrow-screen layout.

## Failure checks

- Malformed or unavailable Gemini output uses a labeled safe fallback.
- No useful objects produces an actionable recovery message.
- ElevenLabs timeout uses the labeled fictional template voice fallback.
- Rendering failure leaves the user with a safe retry path.
- Very dark footage warns without corrupting the result.
- Cached example boxes never enter scoring for an unrelated clip.
- Server paths, stack traces, and secrets never appear in browser errors.

## Demo acceptance

- The controlled clip contains red and blue toys, a green background, and movement.
- Analysis, narration, and the completed reel remain available without venue internet.
- Cache provenance rejects any non-matching video.
- The complete three-minute demonstration succeeds twice consecutively without
  developer intervention.
