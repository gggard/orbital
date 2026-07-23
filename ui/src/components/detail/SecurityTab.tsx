"use client";

import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import SeverityChip from "@/components/SeverityChip";
import StateChip from "@/components/StateChip";
import { useAppScans, useScanVulnerabilities } from "@/lib/api";
import type { Severity } from "@/lib/types";
import { mono } from "@/theme";

const SEVERITY_COLOR: Record<Severity, "error" | "warning" | "default"> = {
  critical: "error",
  high: "error",
  medium: "warning",
  low: "default",
  unknown: "default",
};

export default function SecurityTab({ appId }: { appId: string }) {
  const { data: scans } = useAppScans(appId);
  const [selected, setSelected] = useState<string | null>(null);
  const { data: vulnerabilities } = useScanVulnerabilities(appId, selected);

  const rows = scans ?? [];

  return (
    <Stack spacing={2}>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Scan</TableCell>
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
                <TableCell sx={{ fontFamily: mono, fontSize: "0.75rem" }}>{scan.id}</TableCell>
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
        <Typography variant="subtitle2" gutterBottom sx={{ fontFamily: mono }}>
          scan {selected}
        </Typography>
        {vulnerabilities && vulnerabilities.length === 0 && (
          <Alert severity="success">no vulnerabilities found</Alert>
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
