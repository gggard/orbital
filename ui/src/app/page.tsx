"use client";

import AddIcon from "@mui/icons-material/Add";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import TableRowsOutlinedIcon from "@mui/icons-material/TableRowsOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import ViewModuleOutlinedIcon from "@mui/icons-material/ViewModuleOutlined";
import Alert from "@mui/material/Alert";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
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
import { appsToCsv, downloadCsv } from "@/lib/csv";
import { fmtCpu, fmtMem } from "@/lib/format";
import { applySort, DEFAULT_SORT, SORT_LABELS, toggleSort, type SortKey } from "@/lib/sort";
import type { AdminAppOut, AppState } from "@/lib/types";

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
  const [sort, setSort] = useState(DEFAULT_SORT);
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
  const sortedApps = applySort(filteredApps, sort);

  const removeState = (s: AppState) =>
    setFilter({ ...filter, states: filter.states.filter((x) => x !== s) });
  const removeOwner = (o: string) =>
    setFilter({ ...filter, owners: filter.owners.filter((x) => x !== o) });

  const handleExport = () => {
    const stamp = new Date().toISOString().slice(0, 10);
    downloadCsv(`orbital-apps-${stamp}.csv`, appsToCsv(sortedApps));
  };

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
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel id="apps-sort-label">Sort by</InputLabel>
          <Select
            labelId="apps-sort-label"
            label="Sort by"
            value={sort.key}
            onChange={(e) => setSort({ key: e.target.value as SortKey, dir: sort.dir })}
          >
            {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
              <MenuItem key={key} value={key}>
                {SORT_LABELS[key]}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Tooltip title={sort.dir === "asc" ? "Ascending" : "Descending"}>
          <IconButton
            onClick={() => setSort({ ...sort, dir: sort.dir === "asc" ? "desc" : "asc" })}
            aria-label="toggle sort direction"
          >
            {sort.dir === "asc" ? (
              <ArrowUpwardIcon fontSize="small" />
            ) : (
              <ArrowDownwardIcon fontSize="small" />
            )}
          </IconButton>
        </Tooltip>
        <Tooltip title="Export CSV">
          <span>
            <IconButton
              onClick={handleExport}
              disabled={sortedApps.length === 0}
              aria-label="export csv"
            >
              <FileDownloadOutlinedIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
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

        {isLoading || waitingForAdminData ? (
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
        ) : allApps.length === 0 ? (
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
        ) : filteredApps.length === 0 ? (
          <Stack spacing={1} sx={{ alignItems: "center", py: 8, color: "text.secondary" }}>
            <Typography>No apps match these filters.</Typography>
            <Button size="small" onClick={() => setFilter(EMPTY_FILTER)}>
              Clear filters
            </Button>
          </Stack>
        ) : view === "cards" ? (
          <Box
            sx={{
              display: "grid",
              gap: 2,
              gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "1fr 1fr 1fr" },
            }}
          >
            {sortedApps.map((app) => (
              <AppCard key={app.id} app={app} readOnly={readOnly} onAction={setSnack} />
            ))}
          </Box>
        ) : (
          <AppsTable
            apps={sortedApps}
            sort={sort}
            onSortChange={(key) => setSort(toggleSort(sort, key))}
          />
        )}
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
