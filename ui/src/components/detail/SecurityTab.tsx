"use client";

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
import VulnerabilityTable from "@/components/VulnerabilityTable";
import { useAppScans, useScanVulnerabilities } from "@/lib/api";
import { mono } from "@/theme";

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
        <VulnerabilityTable vulnerabilities={vulnerabilities} />
      </Collapse>
    </Stack>
  );
}
