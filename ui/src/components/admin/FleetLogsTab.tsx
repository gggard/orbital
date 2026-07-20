"use client";

import RefreshIcon from "@mui/icons-material/Refresh";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import LogPane from "@/components/LogPane";
import { useAdminLogs } from "@/lib/api";

export default function FleetLogsTab() {
  const { data: logs, mutate } = useAdminLogs();

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
      <LogPane text={logs ?? "loading…"} follow maxHeight="65vh" />
    </Stack>
  );
}
