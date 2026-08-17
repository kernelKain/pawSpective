# AI Disclosure

## Purpose and scope

PawSpective uses generative AI to identify visible scene elements and to help
create an artistic Story Reel. It also uses deterministic computer-vision and
media-processing code. The product separates these result types in the user
interface:

- **Research-grounded:** deterministic color transformation, image sampling,
  relative contrast calculations, salience weighting, and fixed-palette color
  comparisons.
- **AI-inferred:** visible-object labels, approximate bounding boxes, motion
  levels, visible evidence, possible attention cues, and animation art
  direction.
- **Just for fun:** fictional first-person narration and playful story framing.

PawSpective does not determine a dog's exact sight, gaze, thoughts, emotions,
intent, smell, medical state, or behavior. Its output must not be used for
medical, veterinary, training, safety, or purchasing decisions.

## AI and media services

| Service | Data submitted | Purpose |
| --- | --- | --- |
| Google Gemini scene analysis | A normalized, silent copy of the uploaded 5-15 second video and a structured analysis prompt | Return visible objects, approximate boxes, timestamps, visible evidence, and ordinal motion levels |
| Google Gemini story generation | Selected style, variation identifiers, animation seed, dog profile fields excluding `owner_name`, and user-reviewed visible events | Produce structured art direction; spoken claims are replaced with server-grounded narration before rendering |
| Google Gemini Omni animation | The normalized, silent source clip and a grounding prompt derived from reviewed events | Create an artistic 9:16 edit of the supplied scene |
| Google Veo animation | Up to three JPEG reference frames and the same grounded animation prompt | Create an artistic 9:16 scene when Veo is selected |
| ElevenLabs text-to-speech | The final fictional narration text and configured voice/model identifiers | Generate narration audio; no source video is sent to ElevenLabs |

Gemini structured interaction requests set `store=False`. This application
does not explicitly control or guarantee provider-side logging, abuse
monitoring, temporary processing, or retention. Gemini Omni uploads a clip
through the provider's file API, and the application currently closes the
client without explicitly deleting that remote file. Operators and users
should review the current Google and ElevenLabs terms, privacy notices, and
data-processing settings before using live credentials or sensitive footage.

Provider model names are configurable and may differ between deployments. The
defaults are documented in [.env.example](../.env.example); deployment owners
are responsible for confirming model availability, pricing, and data terms.

## Local data processing and retention

- OpenCV and NumPy perform video-quality inspection, color sampling, canine
  color transformation, relative contrast scoring, and Toy Color Lab
  calculations locally in the backend.
- FFmpeg and FFprobe normalize uploads and compose the completed video locally.
- Analysis and visibility request files use temporary directories that are
  removed after the request finishes.
- Story Reel jobs persist the source clip, job metadata, and final MP4 on the
  configured backend volume. SQLite stores job status and provenance, not the
  video bytes.
- Completed and abandoned job artifacts are eligible for cleanup after
  `PAWSPECTIVE_JOB_TTL_SECONDS`, which defaults to 3,600 seconds and cannot be
  configured below 300 seconds. Cleanup runs when the job manager starts and
  during relevant job API operations.
- Cancelling a job removes its job directory. Successful jobs remove
  intermediate files and retain the completed reel until expiration cleanup.
- The browser holds the selected clip and downloaded result for the active
  session. PawSpective does not provide user accounts or a cloud media library.

The deployment operator controls the backend storage volume, backups, logs,
access policies, deletion schedule, and any infrastructure-level retention.
Do not upload footage without the permission of its owner, and avoid footage
containing people, private locations, identifying documents, or confidential
audio.

## Controlled demo and fallbacks

Demo mode can use local sample analysis and deterministic story fallbacks
without calling live AI providers. Generic sample detections are visibly
labeled and cannot be submitted for scientific scoring against an unrelated
clip.

The optional controlled demo uses a manifest and SHA-256 fingerprint to bind
cached analysis, narration, and the completed reel to one exact rehearsal
clip. Controlled-demo geometry is accepted only after clip and event
validation. Saved narration and visuals remain labeled as cached demo output.

When live story or animation generation is unavailable, the backend may use a
grounded local template or local animation fallback if deployment settings
allow it. Provenance fields identify Gemini, cached, template, and local
fallback results so the interface can present the correct disclosure.

## Safeguards

- Gemini scene analysis must match a strict Pydantic/JSON Schema contract.
- Users can remove or rename AI-detected objects before scoring or storytelling.
- Corrected events become the source of truth for downstream processing.
- Deterministic scoring operates on measured pixels and never treats an AI
  confidence value as a scientific probability.
- Story validation rejects unsupported objects and prohibited claims about
  gaze, thoughts, feelings, smell, intent, or exact perception.
- The server derives final spoken lines from reviewed events even when Gemini
  supplies animation art direction.
- Generated video, narration, cached output, and local fallbacks carry explicit
  provenance in the API and interface.
- Malformed or unavailable provider responses produce a labeled fallback or a
  recoverable error rather than being silently presented as live output.

These controls reduce risk but do not make AI output factual or scientifically
exact. Bounding boxes can be imprecise, visible objects can be missed or
misidentified, generated animation can alter scene details, and voice or video
providers can fail, time out, or change behavior.

## Responsible use

Review every detected object before using visibility, color, or Story Reel
features. Treat Curiosity Map entries only as possible visual cues. Treat the
Story Reel as fiction. Keep a human in control of publishing and remove any
result that reveals private information, misrepresents a real event, or could
reasonably be mistaken for evidence of an animal's internal state.

For the binding product language and prohibited claims, see the
[product contract](product-contract.md). For deployment privacy and security
checks, see the [release checklist](release-checklist.md).
