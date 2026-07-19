"use client";

import DownloadIcon from "@mui/icons-material/Download";
import RefreshIcon from "@mui/icons-material/Refresh";
import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Tooltip from "@mui/material/Tooltip";
import { useState } from "react";
import LogPane from "@/components/LogPane";
import { useAppLogs } from "@/lib/api";

export default function LogsTab({ appId }: { appId: string }) {
  const [follow, setFollow] = useState(true);
  const { data: logs, mutate } = useAppLogs(appId, follow);

  const download = () => {
    const blob = new Blob([logs ?? ""], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${appId}-logs.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <Stack spacing={1}>
      <Stack direction="row" sx={{ alignItems: "center" }}>
        <FormControlLabel
          control={<Switch size="small" checked={follow} onChange={(e) => setFollow(e.target.checked)} />}
          label="Follow"
          slotProps={{ typography: { variant: "body2" } }}
        />
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title="Refresh now">
          <IconButton size="small" onClick={() => mutate()}>
            <RefreshIcon fontSize="inherit" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Download logs">
          <IconButton size="small" onClick={download}>
            <DownloadIcon fontSize="inherit" />
          </IconButton>
        </Tooltip>
      </Stack>
      <LogPane text={logs ?? "loading…"} follow={follow} maxHeight="60vh" />
    </Stack>
  );
}
