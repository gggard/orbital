"use client";

import TableRowsOutlinedIcon from "@mui/icons-material/TableRowsOutlined";
import ViewModuleOutlinedIcon from "@mui/icons-material/ViewModuleOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Link from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Snackbar from "@mui/material/Snackbar";
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
import NextLink from "next/link";
import { useState } from "react";
import AppCard from "@/components/AppCard";
import { ChartStatHeader } from "@/components/charts/SeriesChart";
import StateChip from "@/components/StateChip";
import { useAdminOverview } from "@/lib/api";
import { fmtCpu, fmtMem } from "@/lib/format";
import { mono } from "@/theme";

export default function FleetOverviewTab({ readOnly }: { readOnly: boolean }) {
  const { data, error, isLoading } = useAdminOverview();
  const [view, setView] = useState<"cards" | "table">("table");
  const [snack, setSnack] = useState("");

  if (error) return <Alert severity="error">failed to load fleet overview: {error.message}</Alert>;
  if (isLoading || !data) return <Skeleton variant="rounded" height={320} />;

  const { totals, apps } = data;

  return (
    <Stack spacing={2}>
      <Box
        sx={{
          display: "grid",
          gap: 2,
          gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" },
        }}
      >
        <Card>
          <CardContent>
            <ChartStatHeader title="Apps" value={String(totals.app_count)} />
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <ChartStatHeader title="Running" value={String(totals.running_count)} />
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <ChartStatHeader
              title="CPU"
              value={fmtCpu(totals.cpu)}
              sub={totals.cpu_limit ? `of ${fmtCpu(totals.cpu_limit)} allocated` : undefined}
            />
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <ChartStatHeader
              title="Memory"
              value={fmtMem(totals.mem)}
              sub={totals.mem_limit ? `of ${fmtMem(totals.mem_limit)} allocated` : undefined}
            />
          </CardContent>
        </Card>
      </Box>

      <Stack direction="row" sx={{ justifyContent: "flex-end" }}>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={view}
          onChange={(_, v) => v && setView(v)}
          aria-label="apps view"
        >
          <ToggleButton value="cards" aria-label="cards">
            <Tooltip title="Cards">
              <ViewModuleOutlinedIcon fontSize="small" />
            </Tooltip>
          </ToggleButton>
          <ToggleButton value="table" aria-label="table">
            <Tooltip title="Table">
              <TableRowsOutlinedIcon fontSize="small" />
            </Tooltip>
          </ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      {view === "cards" ? (
        <Box
          sx={{
            display: "grid",
            gap: 2,
            gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "1fr 1fr 1fr" },
          }}
        >
          {apps.map((app) => (
            <AppCard key={app.id} app={app} readOnly={readOnly} onAction={setSnack} />
          ))}
        </Box>
      ) : (
        <TableContainer component={Card}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Slug</TableCell>
                <TableCell>State</TableCell>
                <TableCell>Owner groups</TableCell>
                <TableCell align="right">CPU</TableCell>
                <TableCell align="right">Memory</TableCell>
                <TableCell>Updated</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {apps.map((app) => (
                <TableRow key={app.id} hover>
                  <TableCell>
                    <Link component={NextLink} href={`/apps/${app.id}`} underline="hover">
                      {app.slug}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <StateChip state={app.state} />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {app.owner_groups.join(", ") || "—"}
                    </Typography>
                  </TableCell>
                  <TableCell align="right" sx={{ fontFamily: mono }}>
                    {app.cpu === null ? "—" : fmtCpu(app.cpu)}
                  </TableCell>
                  <TableCell align="right" sx={{ fontFamily: mono }}>
                    {app.mem === null ? "—" : fmtMem(app.mem)}
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {new Date(app.updated_at).toLocaleString()}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {apps.length === 0 && (
        <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
          No apps deployed yet.
        </Typography>
      )}

      <Snackbar
        open={!!snack}
        autoHideDuration={4000}
        onClose={() => setSnack("")}
        message={snack}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      />
    </Stack>
  );
}
