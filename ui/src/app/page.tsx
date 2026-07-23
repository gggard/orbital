"use client";

import AddIcon from "@mui/icons-material/Add";
import TableRowsOutlinedIcon from "@mui/icons-material/TableRowsOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import ViewModuleOutlinedIcon from "@mui/icons-material/ViewModuleOutlined";
import Alert from "@mui/material/Alert";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Skeleton from "@mui/material/Skeleton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import AppCard from "@/components/AppCard";
import AppsFilterBar, { applyFilter, EMPTY_FILTER, filterCount } from "@/components/AppsFilterBar";
import AppsTable from "@/components/AppsTable";
import CreateAppDialog from "@/components/CreateAppDialog";
import Logo from "@/components/Logo";
import { useAdminOverview, useApps, useMe } from "@/lib/api";
import { fmtCpu, fmtMem } from "@/lib/format";
import type { AdminAppOut, AppState } from "@/lib/types";

function AppsListBody({
  loading,
  allApps,
  filteredApps,
  canCreate,
  view,
  readOnly,
  onCreate,
  onClearFilters,
  onAction,
}: Readonly<{
  loading: boolean;
  allApps: AdminAppOut[];
  filteredApps: AdminAppOut[];
  canCreate: boolean;
  view: "cards" | "table";
  readOnly: boolean;
  onCreate: () => void;
  onClearFilters: () => void;
  onAction: (msg: string) => void;
}>) {
  const gridSx = {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "1fr 1fr 1fr" },
  };

  if (loading) {
    return (
      <Box sx={gridSx}>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} variant="rounded" height={150} />
        ))}
      </Box>
    );
  }

  if (allApps.length === 0) {
    return (
      <Stack spacing={2} sx={{ alignItems: "center", py: 10, color: "text.secondary" }}>
        <Box sx={{ opacity: 0.55 }}>
          <Logo size={64} variant="tile" />
        </Box>
        <Typography>
          {canCreate
            ? "No apps yet — deploy your first Streamlit app or static site from a git repository."
            : "No apps are shared with your groups yet."}
        </Typography>
        {canCreate && (
          <Button variant="outlined" startIcon={<AddIcon />} onClick={onCreate}>
            Deploy your first app
          </Button>
        )}
      </Stack>
    );
  }

  if (filteredApps.length === 0) {
    return (
      <Stack spacing={1} sx={{ alignItems: "center", py: 8, color: "text.secondary" }}>
        <Typography>No apps match these filters.</Typography>
        <Button size="small" onClick={onClearFilters}>
          Clear filters
        </Button>
      </Stack>
    );
  }

  if (view === "table") {
    return <AppsTable apps={filteredApps} />;
  }

  return (
    <Box sx={gridSx}>
      {filteredApps.map((app) => (
        <AppCard key={app.id} app={app} readOnly={readOnly} onAction={onAction} />
      ))}
    </Box>
  );
}

export default function AppsOverview() {
  const { data: apps, error, isLoading } = useApps();
  const { data: me } = useMe();
  const isAdmin = me?.role === "admin";
  const { data: overview } = useAdminOverview(isAdmin);
  const [createOpen, setCreateOpen] = useState(false);
  const [snack, setSnack] = useState("");
  const [view, setView] = useState<"cards" | "table">("cards");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filter, setFilter] = useState(EMPTY_FILTER);
  const canCreate = me?.can_create ?? false;
  const readOnly = me?.role === "viewer";
  const activeFilters = filterCount(filter);

  // Admins get every app with live CPU/mem from GET /api/v1/admin/overview;
  // everyone else gets the same shape built from their own visible apps, with
  // the CPU/mem fields null (no bulk metrics endpoint outside the admin
  // role) — both views (cards and table) render from this single list.
  const waitingForAdminData = isAdmin && !overview;
  const allApps: AdminAppOut[] =
    isAdmin && overview ? overview.apps : (apps ?? []).map((a) => ({ ...a, cpu: null, mem: null }));
  const filteredApps = applyFilter(allApps, filter);

  const removeState = (s: AppState) =>
    setFilter({ ...filter, states: filter.states.filter((x) => x !== s) });
  const removeOwner = (o: string) =>
    setFilter({ ...filter, owners: filter.owners.filter((x) => x !== o) });
  const removeTag = (t: string) =>
    setFilter({ ...filter, tags: filter.tags.filter((x) => x !== t) });

  return (
    <>
      <Stack direction="row" spacing={2} sx={{ alignItems: "flex-start", mb: 0.5 }}>
        <Box>
          <Typography variant="h5">Apps</Typography>
          {isAdmin && overview && (
            <Typography variant="body2" color="text.secondary">
              {overview.totals.app_count} apps · {overview.totals.running_count} running ·{" "}
              {fmtCpu(overview.totals.cpu)} CPU · {fmtMem(overview.totals.mem)} memory
            </Typography>
          )}
        </Box>
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title="Filters">
          <IconButton
            onClick={() => setFiltersOpen((o) => !o)}
            color={filtersOpen ? "primary" : "default"}
            sx={{ bgcolor: filtersOpen ? "action.selected" : undefined }}
          >
            <Badge badgeContent={activeFilters} color="primary" invisible={activeFilters === 0}>
              <TuneOutlinedIcon fontSize="small" />
            </Badge>
          </IconButton>
        </Tooltip>
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

      {!filtersOpen && activeFilters > 0 && (
        <Stack direction="row" spacing={1} sx={{ mt: 1.5, mb: 1, flexWrap: "wrap", rowGap: 1 }}>
          {filter.search && (
            <Chip
              size="small"
              label={`“${filter.search}”`}
              onDelete={() => setFilter({ ...filter, search: "" })}
            />
          )}
          {filter.states.map((s) => (
            <Chip key={s} size="small" label={s} onDelete={() => removeState(s)} />
          ))}
          {filter.owners.map((o) => (
            <Chip key={o} size="small" label={o} onDelete={() => removeOwner(o)} />
          ))}
          {filter.tags.map((t) => (
            <Chip key={t} size="small" label={t} onDelete={() => removeTag(t)} />
          ))}
          <Chip
            size="small"
            variant="outlined"
            label="Clear all"
            onClick={() => setFilter(EMPTY_FILTER)}
          />
        </Stack>
      )}

      <Box sx={{ mt: 3 }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            control plane unreachable: {String(error.message ?? error)}
          </Alert>
        )}

        <Collapse in={filtersOpen}>
          <AppsFilterBar apps={allApps} filter={filter} onChange={setFilter} />
        </Collapse>

        <AppsListBody
          loading={isLoading || waitingForAdminData}
          allApps={allApps}
          filteredApps={filteredApps}
          canCreate={canCreate}
          view={view}
          readOnly={readOnly}
          onCreate={() => setCreateOpen(true)}
          onClearFilters={() => setFilter(EMPTY_FILTER)}
          onAction={setSnack}
        />
      </Box>

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
