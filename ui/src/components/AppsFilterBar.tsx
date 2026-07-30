"use client";

import CloseIcon from "@mui/icons-material/Close";
import SearchIcon from "@mui/icons-material/Search";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useMemo } from "react";
import type { AdminAppOut, AppState } from "@/lib/types";

export interface AppsFilter {
  search: string;
  states: AppState[];
  owners: string[];
  tags: string[];
}

export const EMPTY_FILTER: AppsFilter = { search: "", states: [], owners: [], tags: [] };

export function filterCount(filter: AppsFilter): number {
  return (
    (filter.search ? 1 : 0) + filter.states.length + filter.owners.length + filter.tags.length
  );
}

export function applyFilter(apps: AdminAppOut[], filter: AppsFilter): AdminAppOut[] {
  const needle = filter.search.trim().toLowerCase();
  return apps.filter((app) => {
    if (
      needle &&
      !app.slug.toLowerCase().includes(needle) &&
      !app.repo_url.toLowerCase().includes(needle)
    )
      return false;
    if (filter.states.length && !filter.states.includes(app.state)) return false;
    if (filter.owners.length && !app.owner_groups.some((g) => filter.owners.includes(g)))
      return false;
    if (filter.tags.length && !app.tags.some((t) => filter.tags.includes(t))) return false;
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
  readonly apps: AdminAppOut[];
  readonly filter: AppsFilter;
  readonly onChange: (filter: AppsFilter) => void;
}) {
  const stateOptions = useMemo(
    () => [...new Set(apps.map((a) => a.state))].sort((a, b) => a.localeCompare(b)),
    [apps],
  );
  const ownerOptions = useMemo(
    () => [...new Set(apps.flatMap((a) => a.owner_groups))].sort((a, b) => a.localeCompare(b)),
    [apps],
  );
  const tagOptions = useMemo(
    () => [...new Set(apps.flatMap((a) => a.tags))].sort((a, b) => a.localeCompare(b)),
    [apps],
  );

  const toggleTag = (tag: string) =>
    onChange({
      ...filter,
      tags: filter.tags.includes(tag)
        ? filter.tags.filter((t) => t !== tag)
        : [...filter.tags, tag],
    });

  return (
    <Card variant="outlined" sx={{ p: 1.5, mb: 2 }}>
      <Stack direction="row" spacing={1.5} sx={{ flexWrap: "wrap", rowGap: 1.5, mb: tagOptions.length ? 1.5 : 0 }}>
        <TextField
          size="small"
          placeholder="Search by name or repo…"
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
      {tagOptions.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
            Tags
          </Typography>
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap", rowGap: 0.75 }}>
            {tagOptions.map((tag) => {
              const active = filter.tags.includes(tag);
              return (
                <Chip
                  key={tag}
                  size="small"
                  label={tag}
                  onClick={() => toggleTag(tag)}
                  variant={active ? "filled" : "outlined"}
                  color={active ? "primary" : "default"}
                  sx={active ? undefined : { borderColor: "divider" }}
                />
              );
            })}
          </Stack>
        </Box>
      )}
    </Card>
  );
}
