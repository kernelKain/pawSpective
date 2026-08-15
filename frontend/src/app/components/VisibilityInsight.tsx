import type {
  SceneEvent,
  VisibilityScore,
} from "../types/sceneAnalysis";

type VisibilityInsightProps = {
  event: SceneEvent | undefined;
  score: VisibilityScore | undefined;
};

function ScoreBar({
  label,
  score,
}: {
  label: string;
  score: number;
}) {
  return (
    <div className="visibility-score-row">
      <div>
        <span>{label}</span>
        <strong>{score}/100</strong>
      </div>

      <div
        className="visibility-score-track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
      >
        <span style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

export function VisibilityInsight({
  event,
  score,
}: VisibilityInsightProps) {
  if (!event || !score) {
    return (
      <p>
        Review the detected objects, then calculate visibility to see a
        deterministic comparison.
      </p>
    );
  }

  return (
    <div className="visibility-insight-content">
      <h3>{event.object_label}</h3>

      <ScoreBar
        label="Human-visible contrast"
        score={score.human_contrast_score}
      />
      <ScoreBar
        label="Approximate dog-visible contrast"
        score={score.dog_contrast_score}
      />

      <div className="color-comparison">
        <div>
          <span>Human sample</span>
          <div className="color-pair">
            <i
              style={{ backgroundColor: score.human_object_color }}
              aria-label="Sampled object color"
            />
            <i
              style={{ backgroundColor: score.human_background_color }}
              aria-label="Sampled background color"
            />
          </div>
        </div>

        <div>
          <span>Dog Vision approximation</span>
          <div className="color-pair">
            <i
              style={{ backgroundColor: score.dog_object_color }}
              aria-label="Transformed object color"
            />
            <i
              style={{ backgroundColor: score.dog_background_color }}
              aria-label="Transformed background color"
            />
          </div>
        </div>
      </div>

      <p>{score.explanation}</p>

      <dl className="salience-breakdown">
        <div>
          <dt>Motion</dt>
          <dd>{score.motion_score}/100</dd>
        </div>
        <div>
          <dt>Contrast</dt>
          <dd>{score.dog_contrast_score}/100</dd>
        </div>
        <div>
          <dt>Apparent size</dt>
          <dd>{score.apparent_size_score}/100</dd>
        </div>
        <div>
          <dt>Profile bonus</dt>
          <dd>
            {Math.round(score.profile_relevance_score * 0.1)}
            /10 maximum
          </dd>
        </div>
      </dl>

      <div className="relative-score-warning">
        This is a relative PawSpective product score—not a probability or
        scientifically exact measure of what a dog notices.
      </div>
    </div>
  );
}