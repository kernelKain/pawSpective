# Phase 4 manual acceptance checklist

Complete this checklist on the intended HTTPS deployment and demo hardware.
Do not mark Phase 4 release-ready until every required item passes or has a
documented, approved exception.

## Test record

- Date:
- Tester:
- Commit:
- Deployment URL:
- Backend region/runtime:
- Gemini model:
- Desktop device/browser:
- Android device/browser:
- iPhone/iOS/Safari version:

## Live Gemini and scoring flow

- [ ] Disable demo mode and analyze a real five-to-fifteen-second clip.
- [ ] Confirm the result is labeled as a real Gemini result, not cached demo.
- [ ] Rename one object and remove another before scoring.
- [ ] Calculate visibility and confirm the corrected label appears in
  Visibility Insight and Curiosity Map.
- [ ] Confirm the returned score, color samples, breakdown, and warnings render.
- [ ] Change a corrected event after scoring and confirm all old scores clear.
- [ ] Recalculate and confirm only the new results appear.
- [ ] Start scoring and confirm editing, removal, and **Try another moment** are
  disabled until the request finishes.
- [ ] Navigate away during scoring and confirm no late result reappears.

## Demo-mode safeguards

- [ ] Enable demo mode or force Gemini fallback.
- [ ] Confirm the cached-result notice is visible.
- [ ] Confirm **Calculate visibility & curiosity** is disabled.
- [ ] Confirm no request is sent to `/api/v1/score-visibility`.

## Bounding-box alignment

For each row, seek to at least two events and confirm the box surrounds the
same visible object returned by Gemini. Browser playback controls must remain
outside the overlay coordinate area.

| Device and viewport | Portrait clip | Landscape clip |
| --- | --- | --- |
| Desktop Chrome, wide viewport | [ ] | [ ] |
| Desktop Chrome, narrow responsive viewport | [ ] | [ ] |
| Android Chrome | [ ] | [ ] |
| iPhone Safari | [ ] | [ ] |

- [ ] Confirm video is never cropped or stretched.
- [ ] Confirm boxes remain aligned before and after seeking.
- [ ] Confirm playback, pause, and timeline controls remain usable.

## Errors and resilience

- [ ] Confirm short, long, corrupt, empty, and unsupported uploads show safe
  errors.
- [ ] Confirm a scoring API failure appears as an alert and preserves corrected
  events for retry.
- [ ] Confirm partial frame/region warnings appear without hiding valid scores.
- [ ] Confirm an all-events-failed response does not show stale scores.

## Performance record

Run at least three representative clips on the intended demo hardware.

| Run | Clip/device | Scene analysis | Visibility scoring | Notes |
| --- | --- | ---: | ---: | --- |
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |

- [ ] Scene analysis is normally within the 20-second product target.
- [ ] Visibility scoring latency is acceptable for the live demo.
- [ ] No significant mobile heating, browser crash, or frozen UI occurs.

## Sign-off

- [ ] All required checks passed.
- Tester/sign-off:
- Approved exceptions and follow-up issues:
