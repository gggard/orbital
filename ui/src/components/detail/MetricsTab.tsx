"use client";

import TableRowsOutlinedIcon from "@mui/icons-material/TableRowsOutlined";
import TimelineOutlinedIcon from "@mui/icons-material/TimelineOutlined";
import Alert from "@mui/material/Alert";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { ChartStatHeader, SeriesChart } from "@/components/charts/SeriesChart";
import { useAppMetrics } from "@/lib/api";
import { fmtCpu, fmtMem } from "@/lib/format";
import type { MetricsPoint } from "@/lib/types";
import { mono } from "@/theme";

// -- tab -------------------------------------------------------------------

export default function MetricsTab({ appId }: { readonly appId: string }) {
  const { data, error, isLoading } = useAppMetrics(appId);
  const [view, setView] = useState<"charts" | "table">("charts");

  if (error) return <Alert severity="error">failed to load metrics: {error.message}</Alert>;
  if (isLoading || !data) return <Skeleton variant="rounded" height={240} />;

  if (!data.available || data.series.length === 0)
    return (
      <Alert severity="info">
        No metrics yet. Samples appear ~15&thinsp;s after the app is running; if this persists,
        the cluster&apos;s metrics-server may not be installed.
      </Alert>
    );

  const { series, current, limits } = data;
  const cpuPct = current ? Math.round((current.cpu / limits.cpu) * 100) : 0;
  const memPct = current ? Math.round((current.mem / limits.mem) * 100) : 0;

  return (
    <Stack spacing={2}>
      <Stack direction="row" sx={{ justifyContent: "flex-end" }}>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={view}
          onChange={(_, v) => v && setView(v)}
          aria-label="metrics view"
        >
          <ToggleButton value="charts" aria-label="charts">
            <Tooltip title="Charts">
              <TimelineOutlinedIcon fontSize="small" />
            </Tooltip>
          </ToggleButton>
          <ToggleButton value="table" aria-label="table">
            <Tooltip title="Table">
              <TableRowsOutlinedIcon fontSize="small" />
            </Tooltip>
          </ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      {view === "charts" ? (
        <Stack
          spacing={2}
          direction={{ xs: "column", lg: "row" }}
          sx={(theme) => ({
            alignItems: "stretch",
            // dataviz reference palette, slots 1 (blue) and 7 (violet);
            // chart furniture rides the MUI theme tokens
            "--chart-grid": (theme.vars ?? theme).palette.divider,
            "--chart-text": (theme.vars ?? theme).palette.text.secondary,
            "--chart-text-strong": (theme.vars ?? theme).palette.text.primary,
            "--chart-surface": (theme.vars ?? theme).palette.background.paper,
            "--cpu-series": "#2a78d6",
            "--mem-series": "#4a3aa7",
            ...theme.applyStyles("dark", {
              "--cpu-series": "#3987e5",
              "--mem-series": "#9085e9",
            }),
          })}
        >
          <Card sx={{ flex: 1, width: "100%", "--chart-series": "var(--cpu-series)" }}>
            <CardContent>
              <ChartStatHeader
                title="CPU"
                value={current ? `${fmtCpu(current.cpu)} · ${cpuPct}%` : "—"}
                sub={`limit ${fmtCpu(limits.cpu)} core${limits.cpu === 1 ? "" : "s"}`}
              />
              <SeriesChart
                points={series.map((p) => ({ t: p.t, v: p.cpu }))}
                fmt={fmtCpu}
                ariaLabel="CPU usage over time"
              />
            </CardContent>
          </Card>

          <Card sx={{ flex: 1, width: "100%", "--chart-series": "var(--mem-series)" }}>
            <CardContent>
              <ChartStatHeader
                title="Memory"
                value={current ? `${fmtMem(current.mem)} · ${memPct}%` : "—"}
                sub={`limit ${fmtMem(limits.mem)}`}
              />
              <SeriesChart
                points={series.map((p) => ({ t: p.t, v: p.mem }))}
                fmt={fmtMem}
                ariaLabel="Memory usage over time"
              />
            </CardContent>
          </Card>
        </Stack>
      ) : (
        <TableContainer component={Card} sx={{ maxHeight: 420 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Time</TableCell>
                <TableCell align="right">CPU (cores)</TableCell>
                <TableCell align="right">Memory</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {[...series].reverse().map((p: MetricsPoint) => (
                <TableRow key={p.t} hover>
                  <TableCell>{new Date(p.t * 1000).toLocaleTimeString()}</TableCell>
                  <TableCell align="right" sx={{ fontFamily: mono }}>
                    {p.cpu.toFixed(3)}
                  </TableCell>
                  <TableCell align="right" sx={{ fontFamily: mono }}>
                    {fmtMem(p.mem)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Typography variant="caption" color="text.secondary">
        Sampled every 15&thinsp;s from the cluster&apos;s metrics-server; the last ~30 minutes are
        kept. Usage is summed over the app&apos;s pods.
      </Typography>
    </Stack>
  );
}
