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
8. The owner may compare fixed screen colors for one scored object.
9. PawSpective displays possible attention cues in a Curiosity Map.
10. PawSpective generates one animated, narrated vertical dog-height POV Story Reel.
11. The owner downloads the reel.

## Information labels
Every generated result must use one of these labels.

### Research-grounded
Used for deterministic transformations and calculations:
- Canine color transformation
- Foreground/background color sampling
- Foreground/background contrast calculation
- Apparent-size calculation
- Salience weighting and rounding

### AI-inferred
Used for model-generated scene interpretation:
- Object identification
- Bounding boxes
- Object categories
- Visible scene evidence
- Ordinal motion level
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
- Toy Color Lab for corrected, scored Gemini events

## Explicitly deferred
- Authentication
- Multiple profiles
- Custom voice generation
- Breed-specific vision filters
- Exact head or gaze tracking
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
- Story duration: 8–10 seconds
- Live story length: approximately 16–28 words
- Legacy controlled-demo scripts may contain up to 60 words
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

## Toy Color Lab contract

Toy Color Lab compares a fixed set of screen colors against the measured
nearby background of one corrected Gemini event.

The calculation:

1. Seeks to the corrected event timestamp.
2. Reuses the visibility scorer's inner object and surrounding-background regions.
3. Keeps the measured nearby-background color unchanged.
4. Replaces only the object-color input to the contrast formula with one fixed
   palette color.
5. Applies the existing canine color transformation.
6. Calculates human and canine-approximation Lab contrast.
7. Ranks colors by approximate dog-visible contrast.

The result is not:

- Exact canine perception.
- Gemini segmentation.
- A physical recoloring of the source object.
- A guarantee that a physical toy will have the same contrast.
- A behavioral recommendation.

The bounding-box tint is an illustrative preview only. Simulated colors must
never replace corrected scene evidence or enter Story Reel grounding.

## Scoring contract
A dog-visible contrast score is a relative product score. It is not a
probability and must not be presented as a scientifically exact measure.

For each corrected event, the backend:

1. Seeks the normalized video to the event timestamp.
2. Uses the inner 76% of the normalized bounding box as the object sample.
3. Uses the surrounding ring, expanded by 40% of box width and height, as the
   nearby-background sample.
4. Uses per-channel median colors, capped at 50,000 sampled pixels per region.
5. Applies the same canine color matrix and sRGB transfer approximation used
   by the live frontend shader.
6. Converts object/background colors to CIE Lab and maps Delta E 80 or greater
   to the maximum relative contrast score.

Curiosity Map salience is calculated from:

- 35% AI-inferred ordinal motion (`none=0`, `low=33`, `medium=67`,
  `high=100`)
- 35% measured dog-visible contrast
- 20% apparent size, calculated as
  `round(min(1, sqrt(normalized_box_area) / 0.5) * 100)`
- 10% optional profile relevance

The weighted result uses Python's nearest-integer `round` behavior, including
ties-to-even. Scores from 0–33 are low, 34–66 are medium, and 67–100 are high.
The formula and rounding are deterministic; the motion input is AI-inferred
and must be labeled that way.

Profile relevance may provide only a small bonus and must never override
visible evidence. “Sniffing” cannot create a visual profile bonus.

Cached demo bounding boxes do not belong to the uploaded video and must never
be submitted to visibility scoring. Renaming, removing, or replacing an event
invalidates previous scores. Late responses from invalidated requests must be
ignored.

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

The generated animation must:
- Use one continuous first-person dog-height artistic viewpoint
- Preserve corrected visible objects, counts, relationships, and action order
- Avoid external shots of the dog, invented outcomes, text, logos, and generated audio
- Use ElevenLabs for the complete fictional internal monologue
- Carry visual provenance identifying Omni, Veo, local fallback, or saved demo visuals
- Be described as an artistic canine-vision-inspired approximation, never exact sight
