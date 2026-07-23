"use client";

import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import type { AppState, BuildPhase, ScanStatus } from "@/lib/types";

type ChipColor = "success" | "warning" | "error" | "info" | "default";

const STYLES: Record<string, { color: ChipColor; busy?: boolean; label?: string }> = {
  created: { color: "info", busy: true, label: "queued" },
  building: { color: "warning", busy: true },
  deploying: { color: "warning", busy: true },
  running: { color: "success" },
  sleeping: { color: "default" },
  build_failed: { color: "error", label: "build failed" },
  deploy_failed: { color: "error", label: "deploy failed" },
  deleting: { color: "default", busy: true },
  // build phases
  pending: { color: "info", busy: true },
  succeeded: { color: "success" },
  failed: { color: "error" },
};

export default function StateChip({
  state,
  size = "small",
}: {
  state: AppState | BuildPhase | ScanStatus;
  size?: "small" | "medium";
}) {
  const s = STYLES[state] ?? { color: "default" as ChipColor };
  return (
    <Chip
      size={size}
      color={s.color}
      variant="outlined"
      label={s.label ?? state}
      icon={s.busy ? <CircularProgress size={12} color="inherit" /> : undefined}
      sx={{ fontWeight: 600, textTransform: "capitalize" }}
    />
  );
}
