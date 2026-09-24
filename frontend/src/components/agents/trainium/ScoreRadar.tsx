import type { Score } from "@/components/agents/trainium/reportTypes";

const SIZE = 248;
const C = SIZE / 2;
const R = 88;
const RINGS = 5;

/** Point on the radar for axis `i` of `n`, at `value` on a 1-5 scale.
 *  Starts at twelve o'clock and goes clockwise. */
function point(i: number, n: number, value: number, radius = R) {
  const angle = -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const r = (radius * value) / 5;
  return { x: C + r * Math.cos(angle), y: C + r * Math.sin(angle) };
}

/** Short label for an axis: full competency names collide at this radius. */
function shortLabel(label: string): string {
  const first = label.split(/\s+/)[0];
  return first.length > 11 ? `${first.slice(0, 10)}.` : first;
}

/** The whole assessed profile in one shape.
 *
 *  Only criteria that were actually scored appear. Plotting an undetermined
 *  one would need a stand-in value, and a polygon with invented vertices is
 *  exactly the confusion that separating undetermined from a 3 avoids.
 */
export function ScoreRadar({ scores }: { scores: Score[] }) {
  // Under three axes there is no polygon to draw, only a line or a dot.
  if (scores.length < 3) return null;

  const n = scores.length;
  const outline = scores.map((s, i) => point(i, n, s.score));
  const polygon = outline.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  return (
    <svg
      width={SIZE}
      height={SIZE}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="shrink-0"
      role="img"
      aria-label={`Profile across ${n} assessed criteria. ${scores
        .map((s) => `${s.label} ${s.score} out of 5`)
        .join(". ")}.`}
    >
      {Array.from({ length: RINGS }, (_, i) => (
        <circle
          key={i}
          cx={C}
          cy={C}
          r={(R * (i + 1)) / RINGS}
          fill="none"
          stroke="currentColor"
          className="text-slate-200"
          strokeWidth="1"
        />
      ))}

      {scores.map((s, i) => {
        const end = point(i, n, 5);
        return (
          <line
            key={s.competency_key}
            x1={C}
            y1={C}
            x2={end.x}
            y2={end.y}
            stroke="currentColor"
            className="text-slate-200"
            strokeWidth="1"
          />
        );
      })}

      <polygon
        points={polygon}
        className="fill-indigo-600/15 stroke-indigo-600"
        strokeWidth="2"
        strokeLinejoin="round"
      />

      {outline.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3.4" className="fill-indigo-600" />
      ))}

      {scores.map((s, i) => {
        // Labels sit outside the outer ring, nudged so the top and bottom
        // ones clear the shape rather than resting on it.
        const at = point(i, n, 5, R + 17);
        const above = at.y < C - 1;
        return (
          <text
            key={s.competency_key}
            x={at.x}
            y={at.y + (above ? -1 : 5)}
            textAnchor="middle"
            className="fill-slate-500 font-mono"
            fontSize="8.5"
          >
            {shortLabel(s.label)}
          </text>
        );
      })}
    </svg>
  );
}
