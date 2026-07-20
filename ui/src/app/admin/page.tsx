"use client";

import Alert from "@mui/material/Alert";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import FleetLogsTab from "@/components/admin/FleetLogsTab";
import FleetOverviewTab from "@/components/admin/FleetOverviewTab";
import { useMe } from "@/lib/api";

const TABS = ["Overview", "Reconciler logs"] as const;

export default function AdminDashboard() {
  const { data: me, isLoading } = useMe();
  const [tab, setTab] = useState(0);

  if (isLoading || !me) return <Skeleton variant="rounded" height={320} />;

  if (me.role !== "admin")
    return (
      <Alert severity="warning" sx={{ maxWidth: 480 }}>
        This page is restricted to platform admins.
      </Alert>
    );

  return (
    <>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Admin
      </Typography>

      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}
      >
        {TABS.map((t) => (
          <Tab key={t} label={t} />
        ))}
      </Tabs>

      {tab === 0 && <FleetOverviewTab readOnly={false} />}
      {tab === 1 && (
        <Stack spacing={1}>
          <Typography variant="body2" color="text.secondary">
            Live tail of the control plane&apos;s in-memory log buffer (reconciler + API). Resets
            when the control plane restarts; with multiple replicas, only the replica serving this
            request is shown.
          </Typography>
          <FleetLogsTab />
        </Stack>
      )}
    </>
  );
}
