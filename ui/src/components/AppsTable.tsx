"use client";

import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import NextLink from "next/link";
import AppTypeIcon from "@/components/AppTypeIcon";
import SeverityChip from "@/components/SeverityChip";
import StateChip from "@/components/StateChip";
import { fmtCpu, fmtMem } from "@/lib/format";
import type { AdminAppOut } from "@/lib/types";
import { mono } from "@/theme";

/**
 * Table alternative to the card grid. `cpu`/`mem` are only populated for
 * admins (from GET /api/v1/admin/overview); other roles pass apps with those
 * fields set to null and the columns render "—".
 */
export default function AppsTable({ apps }: { readonly apps: AdminAppOut[] }) {
  return (
    <TableContainer component={Card}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell padding="checkbox" />
            <TableCell>Slug</TableCell>
            <TableCell>State</TableCell>
            <TableCell>Owner groups</TableCell>
            <TableCell>Tags</TableCell>
            <TableCell>Vulnerabilities</TableCell>
            <TableCell align="right">CPU</TableCell>
            <TableCell align="right">Memory</TableCell>
            <TableCell>Updated</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {apps.map((app) => (
            <TableRow key={app.id} hover>
              <TableCell padding="checkbox">
                <AppTypeIcon appType={app.app_type} />
              </TableCell>
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
              <TableCell>
                {app.tags.length > 0 ? (
                  <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", rowGap: 0.5 }}>
                    {app.tags.map((tag) => (
                      <Chip key={tag} size="small" variant="outlined" label={tag} />
                    ))}
                  </Stack>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    —
                  </Typography>
                )}
              </TableCell>
              <TableCell>
                <SeverityChip scan={app.latest_scan} />
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
