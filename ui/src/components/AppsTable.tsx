"use client";

import Card from "@mui/material/Card";
import Link from "@mui/material/Link";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TableSortLabel from "@mui/material/TableSortLabel";
import Typography from "@mui/material/Typography";
import NextLink from "next/link";
import StateChip from "@/components/StateChip";
import { fmtCpu, fmtMem } from "@/lib/format";
import type { AppsSort, SortKey } from "@/lib/sort";
import type { AdminAppOut } from "@/lib/types";
import { mono } from "@/theme";

const COLUMNS: { key: SortKey; label: string; align?: "right" }[] = [
  { key: "slug", label: "Slug" },
  { key: "state", label: "State" },
  { key: "owner_groups", label: "Owner groups" },
  { key: "cpu", label: "CPU", align: "right" },
  { key: "mem", label: "Memory", align: "right" },
  { key: "updated_at", label: "Updated" },
];

/**
 * Table alternative to the card grid. `cpu`/`mem` are only populated for
 * admins (from GET /api/v1/admin/overview); other roles pass apps with those
 * fields set to null and the columns render "—".
 */
export default function AppsTable({
  apps,
  sort,
  onSortChange,
}: {
  apps: AdminAppOut[];
  sort: AppsSort;
  onSortChange: (key: SortKey) => void;
}) {
  return (
    <TableContainer component={Card}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            {COLUMNS.map((col) => (
              <TableCell key={col.key} align={col.align}>
                <TableSortLabel
                  active={sort.key === col.key}
                  direction={sort.key === col.key ? sort.dir : "asc"}
                  onClick={() => onSortChange(col.key)}
                >
                  {col.label}
                </TableSortLabel>
              </TableCell>
            ))}
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
  );
}
