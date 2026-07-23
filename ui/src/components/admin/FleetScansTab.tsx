"use client";

import RefreshIcon from "@mui/icons-material/Refresh";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import NextLink from "next/link";
import { useState } from "react";
import SeverityChip from "@/components/SeverityChip";
import StateChip from "@/components/StateChip";
import { useAdminScanVulnerabilities, useAdminScans } from "@/lib/api";
import type { Severity } from "@/lib/types";
import { mono } from "@/theme";

const SEVERITY_COLOR: Record<Severity, "error" | "warning" | "default"> = {
  critical: "error",
  high: "error",
  medium: "warning",
  low: "default",
  unknown: "default",
};

export default function FleetScansTab() {
  const { data: scans, mutate } = useAdminScans();
  const [selected, setSelected] = useState<string | null>(null);
  const { data: vulnerabilities } = useAdminScanVulnerabilities(selected);

  const rows = scans ?? [];

  return (
    <Stack spacing={1}>
      <Stack direction="row" sx={{ alignItems: "center" }}>
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title="Refresh now">
          <IconButton size="small" onClick={() => mutate()}>
            <RefreshIcon fontSize="inherit" />
          </IconButton>
        </Tooltip>
      </Stack>

      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>App</TableCell>
              <TableCell>Image</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Findings</TableCell>
              <TableCell>Finished</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((scan) => (
              <TableRow
                key={scan.id}
                hover
                selected={selected === scan.id}
                sx={{ cursor: "pointer" }}
                onClick={() => setSelected(selected === scan.id ? null : scan.id)}
              >
                <TableCell>
                  <Link
                    component={NextLink}
                    href={`/apps/${scan.app_id}`}
                    underline="hover"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {scan.slug}
                  </Link>
                </TableCell>
                <TableCell sx={{ fontFamily: mono, fontSize: "0.75rem" }}>
                  {scan.image.split(":").pop()}
                </TableCell>
                <TableCell>
                  <StateChip state={scan.status} />
                </TableCell>
                <TableCell>
                  <SeverityChip scan={scan} />
                </TableCell>
                <TableCell>
                  {scan.finished_at ? new Date(scan.finished_at).toLocaleString() : "—"}
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>
                  <Typography variant="body2" color="text.secondary">
                    no scans yet
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Collapse in={!!selected} unmountOnExit>
        {vulnerabilities && vulnerabilities.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            no vulnerabilities found
          </Typography>
        )}
        {vulnerabilities && vulnerabilities.length > 0 && (
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>CVE</TableCell>
                  <TableCell>Package</TableCell>
                  <TableCell>Installed</TableCell>
                  <TableCell>Fixed in</TableCell>
                  <TableCell>Severity</TableCell>
                  <TableCell>Title</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {vulnerabilities.map((v, i) => (
                  <TableRow key={`${v.vuln_id}-${i}`}>
                    <TableCell sx={{ fontFamily: mono, fontSize: "0.75rem" }}>
                      {v.vuln_id}
                    </TableCell>
                    <TableCell sx={{ fontFamily: mono, fontSize: "0.75rem" }}>
                      {v.pkg_name}
                    </TableCell>
                    <TableCell sx={{ fontFamily: mono, fontSize: "0.75rem" }}>
                      {v.installed_version}
                    </TableCell>
                    <TableCell sx={{ fontFamily: mono, fontSize: "0.75rem" }}>
                      {v.fixed_version ?? "—"}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        variant="outlined"
                        color={SEVERITY_COLOR[v.severity]}
                        label={v.severity}
                        sx={{ textTransform: "capitalize", fontWeight: 600 }}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {v.title ?? "—"}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Collapse>
    </Stack>
  );
}
