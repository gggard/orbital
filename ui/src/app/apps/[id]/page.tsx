"use client";

import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import BoltIcon from "@mui/icons-material/Bolt";
import LaunchIcon from "@mui/icons-material/Launch";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import ReplayIcon from "@mui/icons-material/Replay";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Skeleton from "@mui/material/Skeleton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import CopyField from "@/components/CopyField";
import StateChip from "@/components/StateChip";
import AnalyticsTab from "@/components/detail/AnalyticsTab";
import BuildsTab from "@/components/detail/BuildsTab";
import LogsTab from "@/components/detail/LogsTab";
import MetricsTab from "@/components/detail/MetricsTab";
import OverviewTab from "@/components/detail/OverviewTab";
import SecretsTab from "@/components/detail/SecretsTab";
import SettingsTab from "@/components/detail/SettingsTab";
import SharingTab from "@/components/detail/SharingTab";
import { deployApp, rebootApp, useApp, useMe, wakeApp } from "@/lib/api";

const ALL_TABS =
  ["Overview", "Metrics", "Analytics", "Logs", "Builds", "Secrets", "Sharing", "Settings"] as const;
const VIEWER_TABS = ["Overview", "Metrics", "Analytics", "Logs", "Builds"] as const;

export default function AppDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: app, error, isLoading, mutate } = useApp(id);
  const { data: me } = useMe();
  const [tab, setTab] = useState(0);
  const [snack, setSnack] = useState("");
  const readOnly = me?.role === "viewer";
  const tabs = readOnly ? VIEWER_TABS : ALL_TABS;

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try {
      await fn();
      setSnack(msg);
      mutate();
    } catch (e) {
      setSnack(e instanceof Error ? e.message : String(e));
    }
  };

  if (error)
    return (
      <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
        <Alert severity="error">app not found ({String(error.message ?? error)})</Alert>
        <Button component={Link} href="/" startIcon={<ArrowBackIcon />}>
          Back to apps
        </Button>
      </Stack>
    );

  if (isLoading || !app) return <Skeleton variant="rounded" height={320} />;

  return (
    <>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", mb: 0.5 }}>
        <IconButton component={Link} href="/" size="small" aria-label="back">
          <ArrowBackIcon fontSize="small" />
        </IconButton>
        <Typography variant="h5">{app.slug}</Typography>
        {!app.public && (
          <Chip
            size="small"
            icon={<LockOutlinedIcon />}
            label={app.allowed_groups.length ? app.allowed_groups.join(", ") : "signed-in users"}
            variant="outlined"
          />
        )}
        <StateChip state={app.state} />
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title="Open app">
          <span>
            <Button
              size="small"
              startIcon={<LaunchIcon />}
              disabled={!["running", "sleeping"].includes(app.state)}
              component="a"
              href={app.url}
              target="_blank"
              rel="noreferrer"
            >
              Open
            </Button>
          </span>
        </Tooltip>
        {!readOnly && (
          <>
            {app.state === "sleeping" && (
              <Button
                size="small"
                variant="contained"
                startIcon={<BoltIcon />}
                onClick={() => act(() => wakeApp(app.id), "waking up")}
              >
                Wake now
              </Button>
            )}
            <Button
              size="small"
              startIcon={<ReplayIcon />}
              onClick={() => act(() => deployApp(app.id), "redeploy scheduled")}
            >
              Redeploy
            </Button>
            <Button
              size="small"
              startIcon={<RestartAltIcon />}
              disabled={!["running", "deploy_failed"].includes(app.state)}
              onClick={() => act(() => rebootApp(app.id), "reboot scheduled")}
            >
              Reboot
            </Button>
          </>
        )}
      </Stack>

      <Box sx={{ ml: 5.5, mb: 2 }}>
        <CopyField
          value={app.url}
          href={["running", "sleeping"].includes(app.state) ? app.url : undefined}
        />
      </Box>

      {app.error && (
        <Alert severity="error" sx={{ mb: 2, whiteSpace: "pre-wrap" }}>
          {app.error}
        </Alert>
      )}

      <Tabs
        value={Math.min(tab, tabs.length - 1)}
        onChange={(_, v) => setTab(v)}
        sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}
      >
        {tabs.map((t) => (
          <Tab key={t} label={t} />
        ))}
      </Tabs>

      {tabs[Math.min(tab, tabs.length - 1)] === "Overview" && <OverviewTab app={app} />}
      {tabs[tab] === "Metrics" && <MetricsTab appId={app.id} />}
      {tabs[tab] === "Analytics" && <AnalyticsTab appId={app.id} />}
      {tabs[tab] === "Logs" && <LogsTab appId={app.id} />}
      {tabs[tab] === "Builds" && <BuildsTab appId={app.id} />}
      {tabs[tab] === "Secrets" && (
        <SecretsTab appId={app.id} onSaved={() => setSnack("secrets saved — app restarting")} />
      )}
      {tabs[tab] === "Sharing" && (
        <SharingTab app={app} onSaved={() => { setSnack("sharing updated"); mutate(); }} />
      )}
      {tabs[tab] === "Settings" && (
        <SettingsTab app={app} onSaved={(m) => { setSnack(m); mutate(); }} />
      )}

      <Snackbar
        open={!!snack}
        autoHideDuration={4000}
        onClose={() => setSnack("")}
        message={snack}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      />
    </>
  );
}
