import { chartGeometry, type Day } from "./chart";

const PLOT_W = 560;
const PLOT_H = 220;
const PAD_LEFT = 40;
const PAD_TOP = 8;
const WIDTH = PAD_LEFT + PLOT_W + 16;
const HEIGHT = PAD_TOP + PLOT_H + 32;
const TICK = 8;
const END_DOT = 3;

/** One teal line of Sold Out variants per day: straight segments, four gridlines, no legend. */
export function SoldOutChart({ days }: { days: Day[] }) {
  const g = chartGeometry(days, PLOT_W, PLOT_H);
  const last = days[days.length - 1];
  const label = `Sold Out variants per day, ${days[0].date} to ${last.date}, latest ${last.count}`;
  const end = g.points[g.points.length - 1];
  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={label} className="w-full">
      <g transform={`translate(${PAD_LEFT} ${PAD_TOP})`}>
        {g.gridlines.map((l) => (
          <g key={l.value}>
            <line x1={0} x2={PLOT_W} y1={l.y} y2={l.y} className="stroke-rule" strokeWidth={1} />
            <text x={-TICK} y={l.y} textAnchor="end" dominantBaseline="middle" className="fill-muted text-small">
              {l.value}
            </text>
          </g>
        ))}
        <path d={g.path} className="fill-none stroke-accent" strokeWidth={2} strokeLinejoin="round" />
        <circle cx={end.x} cy={end.y} r={END_DOT} className="fill-accent" />
        {g.xLabels.map((l, i) => (
          <text
            key={l.text}
            x={l.x}
            y={PLOT_H + 20}
            textAnchor={i === 0 ? "start" : i === g.xLabels.length - 1 ? "end" : "middle"}
            className="fill-muted text-small"
          >
            {l.text}
          </text>
        ))}
      </g>
    </svg>
  );
}
