# PawSpective Product Contract

## Product promise

PawSpective helps dog owners see an approximation of canine vision,
understand which visible objects stand out in a scene, and turn the
moment into a fictional narrated story.

PawSpective does not claim to reproduce a dog's exact vision, gaze,
thoughts, emotions, or sense of smell.

## Primary journey
1. The owner creates one dog profile.
2. The camera opens in Human View.
3. The owner moves a comparison slider into Dog Vision.
4. The owner records or uploads a 5–10 second clip.
5. PawSpective identifies three to five visible objects.
6. The owner reviews and corrects those objects.
7. PawSpective displays one dog-visible contrast insight.
8. PawSpective displays possible attention cues in a Curiosity Map.
9. PawSpective generates one narrated vertical Story Reel.
10. The owner downloads the reel.

## Information labels
Every generated result must use one of these labels.

### Research-grounded
Used for deterministic transformations and calculations:
- Canine color transformation
- Foreground/background contrast calculation
- Motion calculation
- Salience formula

### AI-inferred
Used for model-generated scene interpretation:
- Object identification
- Bounding boxes
- Object categories
- Visible scene evidence
- Possible attention cues

### Just for fun
Used for fictional output:
- Dog narration
- Cat dialogue
- Scent animations
- Story framing

## Approved language
Use:
- Canine-vision approximation
- Dog-visible contrast
- AI-detected object
- Possible attention cue
- Approximate point of view
- Fictional voice
- Visible evidence suggests
- Relative visibility score

## Prohibited language
Do not use:
- This is exactly how your dog sees
- Your dog is looking at
- Your dog thinks
- Your dog feels
- Your dog smells
- We detected your dog's gaze
- Scientifically exact visibility
- Behavioral or medical diagnosis

## Must ship
- One dog profile
- Live Dog Lens
- Human/Dog comparison slider
- Short recording or upload
- Three to five detected objects when supported by the scene
- User correction of detected objects
- One visibility result
- Curiosity Map
- One story style
- One predefined fictional dog voice
- Downloadable vertical video
- Accuracy Drawer

## Explicitly deferred
- Authentication
- Multiple profiles
- Custom voice generation
- Breed-specific vision filters
- Exact head or gaze tracking
- Alternative toy-color simulation
- Multiple languages
- Community feed
- Full video editor
- Native mobile application
- Behavioral recommendations

## Demo constraints
- Input video: 5–10 seconds
- Maximum accepted duration: 15 seconds
- Target detected events: 3–5
- Maximum accepted events: 12
- Story duration: 15–25 seconds
- Story length: approximately 40–65 words
- Video format: 9:16 MP4
- Story style: nature documentary
- Dog voice: predefined and cached

## Target performance
These are product targets, not guaranteed scientific measurements.
- Live filter should feel immediate on the demo device.
- Scene analysis target: under 20 seconds.
- Complete video target: under 45 seconds.
- A cached demo result must be available if an external service fails.

## Gemini contract
Gemini may report only visibly supported scene information.
Every event must contain:
- Stable event ID
- Timestamp
- Object label
- Object category
- Normalized bounding box
- Confidence
- Visible evidence
- Motion level

Gemini must not infer:
- Gaze
- Thoughts
- Emotions
- Intent
- Smell
- Medical or behavioral state

All Gemini output must pass strict schema validation before use.

## User correction contract
Before scoring or storytelling, the user must be able to:
- Remove an incorrect event
- Rename an object
- Choose the object used for visibility analysis

Corrected data becomes the source of truth for later processing.

## Scoring contract
A dog-visible contrast score is a relative product score. It is not a
probability and must not be presented as a scientifically exact measure.

Curiosity Map salience is calculated from:
- Motion
- Dog-visible contrast
- Apparent proximity
- Optional profile relevance

Profile relevance may provide only a small bonus and must never override
visible evidence.

## Story contract
The story generator receives only:
- The validated and user-corrected scene timeline
- The dog profile fields permitted for Story Mode
- The selected story style

The generated story must:
- Mention only supported scene objects
- Remain fictional and playful
- Avoid claims about emotions, thoughts, gaze, smell, or intent
- Fit the target video duration
- Identify the voice as fictional

## Phase 0 exit criteria
Phase 0 is complete when:

- This contract is approved.
- The Gemini response model exists.
- The example response passes validation.
- Invalid bounding boxes fail validation.
- Impossible timestamps fail validation.
- Unexpected fields fail validation.
- The JSON Schema can be generated from the Python model.
- The demo team agrees on the must-ship and deferred lists.