"use client";

import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import { useState } from "react";
import LogPane from "@/components/LogPane";
import StateChip from "@/components/StateChip";
import { useBuildLogs, useBuilds } from "@/lib/api";
import { mono } from "@/theme";

function duration(start: string, end: string | null): string {
  if (!end) return "—";
  const s = (new Date(end).getTime() - new Date(start).getTime()) / 1000;
  return s < 90 ? `${Math.round(s)}s` : `${Math.round(s / 60)}m ${Math.round(s % 60)}s`;
}

export default function BuildsTab({ appId }: { readonly appId: string }) {
  const { data: builds } = useBuilds(appId);
  const [selected, setSelected] = useState<string | null>(null);
  const { data: buildLogs } = useBuildLogs(appId, selected);

  const rows = [...(builds ?? [])].reverse();

  return (
    <Stack spacing={2}>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Build</TableCell>
              <TableCell>Commit</TableCell>
              <TableCell>Phase</TableCell>
              <TableCell>Started</TableCell>
              <TableCell>Duration</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((b) => (
              <TableRow
                key={b.id}
                hover
                selected={selected === b.id}
                sx={{ cursor: "pointer" }}
                onClick={() => setSelected(selected === b.id ? null : b.id)}
              >
                <TableCell sx={{ fontFamily: mono, fontSize: "0.75rem" }}>{b.id}</TableCell>
                <TableCell sx={{ fontFamily: mono, fontSize: "0.75rem" }}>
                  {b.commit_sha?.slice(0, 10) ?? "—"}
                </TableCell>
                <TableCell>
                  <StateChip state={b.phase} />
                </TableCell>
                <TableCell>{new Date(b.created_at).toLocaleString()}</TableCell>
                <TableCell>{duration(b.created_at, b.finished_at)}</TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>
                  <Typography variant="body2" color="text.secondary">
                    no builds yet
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <Collapse in={!!selected} unmountOnExit>
        <Typography variant="subtitle2" gutterBottom sx={{ fontFamily: mono }}>
          build {selected}
        </Typography>
        <LogPane text={buildLogs ?? "loading…"} maxHeight="50vh" />
      </Collapse>
    </Stack>
  );
}
