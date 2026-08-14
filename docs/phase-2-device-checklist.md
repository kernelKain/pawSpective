# Phase 2 physical-device verification

Complete this checklist on an HTTPS deployment before declaring Phase 2
release-ready. Record the phone, operating system, browser, deployment URL,
and test date with the results.

## Camera lifecycle

- [ ] Allow camera permission and confirm the live preview starts.
- [ ] Deny camera permission and confirm recovery instructions appear.
- [ ] Confirm **Switch camera** changes between rear and front cameras.
- [ ] Confirm the front-camera preview is mirrored.
- [ ] Confirm the browser camera indicator turns off after **Stop**.
- [ ] Confirm the camera indicator turns off after continuing to mock analysis.
- [ ] Confirm the camera indicator turns off after returning to the profile.

## Renderer state

- [ ] Change Dog Vision and detail-reduction sliders.
- [ ] Stop and restart the camera.
- [ ] Confirm both displayed slider values still match the rendered filter.
- [ ] Confirm the alignment guide is visible over the live preview.
- [ ] Test the WebGL-disabled or hardware-acceleration-disabled error state.

## Device behavior

- [ ] Run the live lens continuously for at least five minutes.
- [ ] Record whether the preview remains responsive.
- [ ] Record noticeable device heating or battery impact.
- [ ] Repeat camera switching at least five times.

If a browser repeatedly returns the same camera, replace the current
`facingMode: { ideal: ... }` strategy with `videoinput` enumeration and
`deviceId` selection, or try exact facing mode before falling back to ideal.
