"use client";

import CloseIcon from "@mui/icons-material/Close";
import SearchIcon from "@mui/icons-material/Search";
import Autocomplete from "@mui/material/Autocomplete";
import Card from "@mui/material/Card";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { useMemo } from "react";
import type { AdminAppOut, AppState } from "@/lib/types";

export interface AppsFilter {
  search: string;
  states: AppState[];
  owners: string[];
}

export const EMPTY_FILTER: AppsFilter = { search: "", states: [], owners: [] };

export function filterCount(filter: AppsFilter): number {
  return (filter.search ? 1 : 0) + filter.states.length + filter.owners.length;
}

export function applyFilter(apps: AdminAppOut[], filter: AppsFilter): AdminAppOut[] {
  const needle = filter.search.trim().toLowerCase();
  return apps.filter((app) => {
    if (needle && !app.slug.toLowerCase().includes(needle)) return false;
    if (filter.states.length && !filter.states.includes(app.state)) return false;
    if (filter.owners.length && !app.owner_groups.some((g) => filter.owners.includes(g)))
      return false;
    return true;
  });
}

/** Compact filter toolbar: name search + State/Owner multi-select, options
 * scoped to whatever's currently loaded so nothing offered ever matches
 * zero apps. Lives inside a `Collapse` in the caller — see AppsOverview. */
export default function AppsFilterBar({
  apps,
  filter,
  onChange,
}: {
  apps: AdminAppOut[];
  filter: AppsFilter;
  onChange: (filter: AppsFilter) => void;
}) {
  const stateOptions = useMemo(() => [...new Set(apps.map((a) => a.state))].sort(), [apps]);
  const ownerOptions = useMemo(
    () => [...new Set(apps.flatMap((a) => a.owner_groups))].sort(),
    [apps],
  );

  return (
    <Card variant="outlined" sx={{ p: 1.5, mb: 2 }}>
      <Stack direction="row" spacing={1.5} sx={{ flexWrap: "wrap", rowGap: 1.5 }}>
        <TextField
          size="small"
          placeholder="Search by name…"
          value={filter.search}
          onChange={(e) => onChange({ ...filter, search: e.target.value })}
          sx={{ minWidth: 200, flexGrow: 1, maxWidth: 280 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
              endAdornment: filter.search && (
                <InputAdornment position="end">
                  <IconButton size="small" onClick={() => onChange({ ...filter, search: "" })}>
                    <CloseIcon fontSize="inherit" />
                  </IconButton>
                </InputAdornment>
              ),
            },
          }}
        />
        <Autocomplete
          multiple
          size="small"
          options={stateOptions}
          value={filter.states}
          onChange={(_, v) => onChange({ ...filter, states: v })}
          renderInput={(params) => (
            <TextField {...params} label="State" placeholder={filter.states.length ? undefined : "Any"} />
          )}
          sx={{ minWidth: 180, flex: "1 1 180px" }}
        />
        <Autocomplete
          multiple
          size="small"
          options={ownerOptions}
          value={filter.owners}
          onChange={(_, v) => onChange({ ...filter, owners: v })}
          renderInput={(params) => (
            <TextField {...params} label="Owner" placeholder={filter.owners.length ? undefined : "Any"} />
          )}
          sx={{ minWidth: 180, flex: "1 1 180px" }}
        />
      </Stack>
    </Card>
  );
}
