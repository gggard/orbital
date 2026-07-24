"use client";

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMemo, useRef, useState } from "react";
import { mono } from "@/theme";

/**
 * Single-series area chart (dataviz: 2px line, ~10% wash fill, hairline solid
 * gridlines, end-dot with surface ring, crosshair tooltip, no legend - a lone
 * series needs no legend box, the title names it). Shared by Metrics and
 * Analytics; the caller sets `--chart-series` (+ the chrome vars) via sx on a
 * wrapping element and picks a slot from the dataviz reference palette.
 */

const W = 600; // viewBox width; SVG stretches to the card
const H = 170; // plot height (x-axis band added below, per container contract)
const PAD_TOP = 12;
const PAD_RIGHT = 14;
const AXIS_W = 48; // left band for y tick labels
const AXIS_H = 22; // bottom band for time labels

const defaultFmtTime = (t: number) =>
  new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

/** Round up to a "clean" value: 1/2/5 × 10^k. */
function niceCeil(v: number): number {
  if (v <= 0) return 1;
  const exp = Math.floor(Math.log10(v));
  const base = 10 ** exp;
  for (const m of [1, 2, 5, 10]) {
    if (m * base >= v) return m * base;
  }
  return 10 * base;
}

export interface SeriesPoint {
  t: number;
  v: number;
}

interface SeriesChartProps {
  readonly points: SeriesPoint[];
  readonly fmt: (v: number) => string;
  readonly ariaLabel: string;
  readonly fmtTime?: (t: number) => string;
}

export function SeriesChart({ points, fmt, ariaLabel, fmtTime = defaultFmtTime }: SeriesChartProps) {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const { max, path, area, xs, ys, gridVals } = useMemo(() => {
    const dataMax = Math.max(...points.map((p) => p.v), 1e-9);
    const max = niceCeil(dataMax * 1.15);
    const t0 = points[0].t;
    const t1 = points[points.length - 1].t;
    const span = Math.max(t1 - t0, 1);
    const plotW = W - AXIS_W - PAD_RIGHT;
    const plotH = H - PAD_TOP;
    const xs = points.map((p) => AXIS_W + ((p.t - t0) / span) * plotW);
    const ys = points.map((p) => PAD_TOP + (1 - p.v / max) * plotH);
    const path = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join("");
    const area = `${path}L${xs[xs.length - 1].toFixed(1)},${H}L${xs[0].toFixed(1)},${H}Z`;
    const gridVals = [max / 2, max]; // baseline drawn separately at 0
    return { max, path, area, xs, ys, gridVals };
  }, [points]);

  const yFor = (v: number) => PAD_TOP + (1 - v / max) * (H - PAD_TOP);

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0;
    for (let i = 1; i < xs.length; i++) {
      if (Math.abs(xs[i] - x) < Math.abs(xs[best] - x)) best = i;
    }
    setHover(best);
  };

  const last = points.length - 1;
  const h = hover;
  // time labels: ends only (middle would crowd at this width)
  const timeTicks = [0, last];

  return (
    <Box sx={{ position: "relative" }}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H + AXIS_H}`}
        role="img"
        aria-label={ariaLabel}
        style={{ display: "block", width: "100%", height: "auto" }}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {/* gridlines: hairline, solid, recessive; baseline at 0 */}
        {gridVals.map((v) => (
          <g key={v}>
            <line
              x1={AXIS_W}
              x2={W - PAD_RIGHT}
              y1={yFor(v)}
              y2={yFor(v)}
              stroke="var(--chart-grid)"
              strokeWidth={1}
            />
            <text
              x={AXIS_W - 8}
              y={yFor(v) + 3.5}
              textAnchor="end"
              fontSize={11}
              fill="var(--chart-text)"
            >
              {fmt(v)}
            </text>
          </g>
        ))}
        <line
          x1={AXIS_W}
          x2={W - PAD_RIGHT}
          y1={H}
          y2={H}
          stroke="var(--chart-grid)"
          strokeWidth={1}
        />
        <text x={AXIS_W - 8} y={H + 3.5} textAnchor="end" fontSize={11} fill="var(--chart-text)">
          0
        </text>

        {/* area wash + 2px line */}
        <path d={area} fill="var(--chart-series)" fillOpacity={0.1} />
        <path
          d={path}
          fill="none"
          stroke="var(--chart-series)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* crosshair + hovered dot */}
        {h !== null && (
          <>
            <line
              x1={xs[h]}
              x2={xs[h]}
              y1={PAD_TOP}
              y2={H}
              stroke="var(--chart-grid)"
              strokeWidth={1}
            />
            <circle
              cx={xs[h]}
              cy={ys[h]}
              r={4}
              fill="var(--chart-series)"
              stroke="var(--chart-surface)"
              strokeWidth={2}
            />
          </>
        )}

        {/* end-dot with surface ring + direct label for the latest value */}
        {h === null && (
          <>
            <circle
              cx={xs[last]}
              cy={ys[last]}
              r={4}
              fill="var(--chart-series)"
              stroke="var(--chart-surface)"
              strokeWidth={2}
            />
            <text
              x={Math.min(xs[last], W - PAD_RIGHT)}
              y={Math.max(ys[last] - 10, 11)}
              textAnchor="end"
              fontSize={11.5}
              fontWeight={600}
              fill="var(--chart-text-strong)"
            >
              {fmt(points[last].v)}
            </text>
          </>
        )}

        {/* time axis */}
        {timeTicks.map((i, k) => (
          <text
            key={i}
            x={xs[i]}
            y={H + 16}
            textAnchor={k === 0 ? "start" : "end"}
            fontSize={11}
            fill="var(--chart-text)"
          >
            {fmtTime(points[i].t)}
          </text>
        ))}
      </svg>

      {/* tooltip: value leads, time follows */}
      {h !== null && (
        <Box
          sx={{
            position: "absolute",
            left: `${(xs[h] / W) * 100}%`,
            top: 0,
            transform: `translateX(${xs[h] > W * 0.75 ? "-108%" : "8%"})`,
            bgcolor: "background.paper",
            border: 1,
            borderColor: "divider",
            borderRadius: 1,
            px: 1,
            py: 0.5,
            pointerEvents: "none",
            boxShadow: 1,
            whiteSpace: "nowrap",
          }}
        >
          <Typography component="span" variant="body2" sx={{ fontWeight: 650 }}>
            {fmt(points[h].v)}
          </Typography>
          <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.75 }}>
            {fmtTime(points[h].t)}
          </Typography>
        </Box>
      )}
    </Box>
  );
}

export function ChartStatHeader({
  title,
  value,
  sub,
}: {
  readonly title: string;
  readonly value: string;
  readonly sub?: string;
}) {
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "baseline", mb: 1 }}>
      <Typography variant="subtitle2" color="text.secondary">
        {title}
      </Typography>
      <Typography variant="h6" sx={{ fontFamily: mono, fontSize: "1.05rem" }}>
        {value}
      </Typography>
      {sub && (
        <Typography variant="caption" color="text.secondary">
          {sub}
        </Typography>
      )}
    </Stack>
  );
}
