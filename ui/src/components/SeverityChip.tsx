"use client";

import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import type { ScanOut } from "@/lib/types";

type ChipColor = "success" | "warning" | "error" | "default";

function summarize(scan: ScanOut | null | undefined): {
  label: string;
  color: ChipColor;
  busy?: boolean;
} {
  if (!scan) return { label: "not scanned", color: "default" };
  if (scan.status === "pending" || scan.status === "running")
    return { label: "scanning…", color: "default", busy: true };
  if (scan.status === "failed") return { label: "scan failed", color: "default" };
  if (scan.critical_count > 0) return { label: `${scan.critical_count} critical`, color: "error" };
  if (scan.high_count > 0) return { label: `${scan.high_count} high`, color: "error" };
  if (scan.medium_count > 0) return { label: `${scan.medium_count} medium`, color: "warning" };
  if (scan.low_count > 0) return { label: `${scan.low_count} low`, color: "default" };
  return { label: "clean", color: "success" };
}

/** Small chip summarizing an app's latest vulnerability scan, in order of
 * severity (critical > high > medium > low > clean).
 */
export default function SeverityChip({ scan }: { scan: ScanOut | null | undefined }) {
  const { label, color, busy } = summarize(scan);
  return (
    <Chip
      size="small"
      color={color}
      variant="outlined"
      label={label}
      icon={busy ? <CircularProgress size={12} color="inherit" /> : undefined}
      sx={{ fontWeight: 600 }}
    />
  );
}
