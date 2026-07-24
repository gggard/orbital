"use client";

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
import Typography from "@mui/material/Typography";
import { ChartStatHeader, SeriesChart } from "@/components/charts/SeriesChart";
import { useAppAnalytics } from "@/lib/api";
import type { AnalyticsViewer } from "@/lib/types";
import { mono } from "@/theme";

const fmtInt = (n: number) => n.toLocaleString();

const fmtDay = (t: number) =>
  new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric" });

function dayToUnix(date: string): number {
  return new Date(`${date}T00:00:00Z`).getTime() / 1000;
}

function StatTile({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <Card sx={{ flex: 1, minWidth: 140 }}>
      <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
        <Typography variant="caption" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h6" sx={{ fontFamily: mono, fontSize: "1.15rem", mt: 0.25 }}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  );
}

export default function AnalyticsTab({ appId }: { readonly appId: string }) {
  const { data, error, isLoading } = useAppAnalytics(appId);

  if (error) return <Alert severity="error">failed to load analytics: {error.message}</Alert>;
  if (isLoading || !data) return <Skeleton variant="rounded" height={240} />;

  if (data.total_views === 0)
    return (
      <Alert severity="info">
        No views recorded yet. Views are counted from real traffic once the app is running.
      </Alert>
    );

  const dailyPoints = data.daily.map((d) => ({ t: dayToUnix(d.date), v: d.views }));
  const uniquePoints = data.daily.map((d) => ({ t: dayToUnix(d.date), v: d.unique_viewers }));

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
        <StatTile label="Total views" value={fmtInt(data.total_views)} />
        <StatTile label="Unique viewers today" value={fmtInt(data.unique_viewers_1d)} />
        <StatTile label="Unique viewers (7d)" value={fmtInt(data.unique_viewers_7d)} />
        <StatTile label="Unique viewers (30d)" value={fmtInt(data.unique_viewers_30d)} />
        <StatTile
          label="Last visited"
          value={data.last_viewed_at ? new Date(data.last_viewed_at).toLocaleString() : "—"}
        />
      </Stack>

      {dailyPoints.length > 1 && (
        <Stack
          spacing={2}
          direction={{ xs: "column", lg: "row" }}
          sx={(theme) => ({
            alignItems: "stretch",
            // dataviz reference palette, slots 5 (aqua) and 6 (orange) - distinct
            // from Metrics' CPU/Mem (slots 1/7); chrome rides the MUI theme tokens
            "--chart-grid": (theme.vars ?? theme).palette.divider,
            "--chart-text": (theme.vars ?? theme).palette.text.secondary,
            "--chart-text-strong": (theme.vars ?? theme).palette.text.primary,
            "--chart-surface": (theme.vars ?? theme).palette.background.paper,
            "--views-series": "#1baf7a",
            "--viewers-series": "#eb6834",
            ...theme.applyStyles("dark", {
              "--views-series": "#199e70",
              "--viewers-series": "#d95926",
            }),
          })}
        >
          <Card sx={{ flex: 1, width: "100%", "--chart-series": "var(--views-series)" }}>
            <CardContent>
              <ChartStatHeader title="Views per day" value={fmtInt(dailyPoints.at(-1)!.v)} />
              <SeriesChart
                points={dailyPoints}
                fmt={fmtInt}
                fmtTime={fmtDay}
                ariaLabel="Views per day"
              />
            </CardContent>
          </Card>

          <Card sx={{ flex: 1, width: "100%", "--chart-series": "var(--viewers-series)" }}>
            <CardContent>
              <ChartStatHeader
                title="Unique viewers per day"
                value={fmtInt(uniquePoints.at(-1)!.v)}
              />
              <SeriesChart
                points={uniquePoints}
                fmt={fmtInt}
                fmtTime={fmtDay}
                ariaLabel="Unique viewers per day"
              />
            </CardContent>
          </Card>
        </Stack>
      )}

      {data.viewers.length > 0 && (
        <TableContainer component={Card} sx={{ maxHeight: 420 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Viewer</TableCell>
                <TableCell align="right">Views</TableCell>
                <TableCell align="right">Last seen</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.viewers.map((v: AnalyticsViewer) => (
                <TableRow key={v.viewer} hover>
                  <TableCell>{v.viewer}</TableCell>
                  <TableCell align="right" sx={{ fontFamily: mono }}>
                    {fmtInt(v.views)}
                  </TableCell>
                  <TableCell align="right">{new Date(v.last_seen).toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Typography variant="caption" color="text.secondary">
        Views are recorded from real app traffic and deduped per viewer within a 30-minute
        window. Private-app viewers are identified by their signed-in email; public-app viewers
        are counted anonymously.
      </Typography>
    </Stack>
  );
}
