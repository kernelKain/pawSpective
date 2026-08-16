# Phase 5 acceptance checklist

Record the deployment URL, device/browser versions, input orientation, timing
and result for every run. Automated tests do not replace these physical-device
checks.

## Real-service journey

- [ ] `PAWSPECTIVE_DEMO_MODE=false` is set on the backend.
- [ ] A real 5-to-15-second clip produces Gemini scene events.
- [ ] Incorrect events can be renamed or removed before scoring.
- [ ] Visibility scoring finishes for at least one corrected event.
- [ ] The selected featured event has a visibility score.
- [ ] Story generation mentions only corrected visible object labels.
- [ ] The narration is identified as a fictional dog voice.
- [ ] The rendered reel plays with audible narration and readable subtitles.
- [ ] The reel downloads and plays outside the browser.

## Output inspection

- [ ] Width is 720 and height is 1280.
- [ ] Video codec is H.264, audio codec is AAC and pixel format is yuv420p.
- [ ] Display aspect ratio is 9:16.
- [ ] Duration is between 15 and 25 seconds.
- [ ] Human View, canine-vision transition, Curiosity Map and result card appear.
- [ ] The PawSpective watermark and accuracy disclaimer are visible.

## Failure and retry behavior

- [ ] Missing Gemini key produces a safe fallback or retryable error.
- [ ] Missing ElevenLabs key and invalid voice ID produce safe retryable errors.
- [ ] Gemini and ElevenLabs timeouts do not leave the UI stuck.
- [ ] Unsupported, corrupt, short and long videos produce safe errors.
- [ ] Invalid timestamps and an unscored featured event are rejected.
- [ ] Overlong narration and missing FFmpeg/FFprobe produce safe errors.
- [ ] After every failure, the user can retry or select another moment.

## Story safety

- [ ] Gaze, thought, knowledge, feeling, smell, desire and intent claims fail.
- [ ] Unknown event IDs and unsupported declared object labels fail.
- [ ] Changed featured-event IDs fail.
- [ ] Scripts outside 40-to-60 words fail.
- [ ] Missing fictional-voice notice and unexpected fields fail.

## Device matrix

| Device | Browser | Portrait input | Landscape input | Playback | Audio | Download | Box alignment | Repeated-render memory |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Desktop | Chrome | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| Android phone | Chrome | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| iPhone | Safari | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |

## Performance

- [ ] Record Gemini scene-analysis time.
- [ ] Record story-generation plus ElevenLabs narration time.
- [ ] Record video-composition time.
- [ ] Complete Story Reel request finishes within the 45-second target on the
  intended demo backend.

Phase 5 is release-ready only after this checklist and CI are both green.
