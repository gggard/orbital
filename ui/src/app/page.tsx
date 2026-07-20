"use client";

import AddIcon from "@mui/icons-material/Add";
import TableRowsOutlinedIcon from "@mui/icons-material/TableRowsOutlined";
import ViewModuleOutlinedIcon from "@mui/icons-material/ViewModuleOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import AppCard from "@/components/AppCard";
import AppsTable from "@/components/AppsTable";
import { ChartStatHeader } from "@/components/charts/SeriesChart";
import CreateAppDialog from "@/components/CreateAppDialog";
import Logo from "@/components/Logo";
import { useAdminOverview, useApps, useMe } from "@/lib/api";
import { fmtCpu, fmtMem } from "@/lib/format";
import type { AdminAppOut } from "@/lib/types";

export default function AppsOverview() {
  const { data: apps, error, isLoading } = useApps();
  const { data: me } = useMe();
  const isAdmin = me?.role === "admin";
  const { data: overview } = useAdminOverview(isAdmin);
  const [createOpen, setCreateOpen] = useState(false);
  const [snack, setSnack] = useState("");
  const [view, setView] = useState<"cards" | "table">("cards");
  const canCreate = me?.can_create ?? false;
  const readOnly = me?.role === "viewer";

  // Table view: admins get live CPU/mem + fleet totals from
  // GET /api/v1/admin/overview; everyone else gets the same table built from
  // their own visible apps, with the CPU/mem columns rendering "—" (no bulk
  // metrics endpoint outside the admin role).
  const tableApps: AdminAppOut[] =
    isAdmin && overview ? overview.apps : (apps ?? []).map((a) => ({ ...a, cpu: null, mem: null }));

  return (
    <>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", mb: 3 }}>
        <Typography variant="h5">Apps</Typography>
        <Box sx={{ flexGrow: 1 }} />
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
        {canCreate && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            New app
          </Button>
        )}
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          control plane unreachable: {String(error.message ?? error)}
        </Alert>
      )}

      {isAdmin && overview && (
        <Box
          sx={{
            display: "grid",
            gap: 2,
            gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" },
            mb: 2,
          }}
        >
          <Card>
            <CardContent>
              <ChartStatHeader title="Apps" value={String(overview.totals.app_count)} />
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <ChartStatHeader title="Running" value={String(overview.totals.running_count)} />
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <ChartStatHeader
                title="CPU"
                value={fmtCpu(overview.totals.cpu)}
                sub={
                  overview.totals.cpu_limit
                    ? `of ${fmtCpu(overview.totals.cpu_limit)} allocated`
                    : undefined
                }
              />
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <ChartStatHeader
                title="Memory"
                value={fmtMem(overview.totals.mem)}
                sub={
                  overview.totals.mem_limit
                    ? `of ${fmtMem(overview.totals.mem_limit)} allocated`
                    : undefined
                }
              />
            </CardContent>
          </Card>
        </Box>
      )}

      {isLoading ? (
        <Box
          sx={{
            display: "grid",
            gap: 2,
            gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "1fr 1fr 1fr" },
          }}
        >
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} variant="rounded" height={150} />
          ))}
        </Box>
      ) : apps?.length === 0 ? (
        <Stack spacing={2} sx={{ alignItems: "center", py: 10, color: "text.secondary" }}>
          <Box sx={{ opacity: 0.55 }}>
            <Logo size={64} variant="tile" />
          </Box>
          <Typography>
            {canCreate
              ? "No apps yet — deploy your first Streamlit app from a git repository."
              : "No apps are shared with your groups yet."}
          </Typography>
          {canCreate && (
            <Button variant="outlined" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
              Deploy your first app
            </Button>
          )}
        </Stack>
      ) : view === "cards" ? (
        <Box
          sx={{
            display: "grid",
            gap: 2,
            gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "1fr 1fr 1fr" },
          }}
        >
          {apps?.map((app) => (
            <AppCard key={app.id} app={app} readOnly={readOnly} onAction={setSnack} />
          ))}
        </Box>
      ) : isAdmin && !overview ? (
        <Skeleton variant="rounded" height={320} />
      ) : (
        <AppsTable apps={tableApps} />
      )}

      <CreateAppDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      <Snackbar
        open={!!snack}
        autoHideDuration={4000}
        onClose={() => setSnack("")}
        message={snack}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      />
    </>
  );
}
