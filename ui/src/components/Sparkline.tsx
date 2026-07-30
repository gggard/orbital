const VIEW_W = 100;
const VIEW_H = 32;

function sparkPaths(values: number[]): { line: string; area: string } {
  const max = Math.max(...values, 1e-6);
  const min = Math.min(...values, 0);
  const span = Math.max(max - min, 1e-6);
  const xs = values.map((_, i) => (values.length > 1 ? (i / (values.length - 1)) * VIEW_W : 0));
  const ys = values.map((v) => VIEW_H - ((v - min) / span) * (VIEW_H - 4) - 2);
  const line = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join("");
  const area = `${line}L${xs[xs.length - 1].toFixed(1)},${VIEW_H}L${xs[0].toFixed(1)},${VIEW_H}Z`;
  return { line, area };
}

/** Tiny inline trend line (cpu/mem history on an app card): a single-series
 * line + faint area fill, no charting library needed at this size. */
export default function Sparkline({
  values,
  color,
  width = 36,
  height = 14,
}: {
  readonly values: number[];
  readonly color: string;
  readonly width?: number;
  readonly height?: number;
}) {
  if (values.length < 2) {
    return (
      <svg width={width} height={height} viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} aria-hidden="true">
        <line
          x1={0}
          y1={VIEW_H / 2}
          x2={VIEW_W}
          y2={VIEW_H / 2}
          stroke={color}
          strokeWidth={2}
          strokeOpacity={0.25}
        />
      </svg>
    );
  }
  const { line, area } = sparkPaths(values);
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path d={area} fill={color} fillOpacity={0.12} stroke="none" />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
