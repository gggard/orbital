"use client";

import Alert from "@mui/material/Alert";
import Link from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import NextLink from "next/link";
import { useState } from "react";
import FleetLogsTab from "@/components/admin/FleetLogsTab";
import FleetScansTab from "@/components/admin/FleetScansTab";
import { useMe } from "@/lib/api";

const TABS = ["Logs", "Vulnerabilities"] as const;

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
    <Stack spacing={1}>
      <Typography variant="h5">Fleet admin</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Reconciler logs and vulnerability scan results across all apps. Fleet-wide app status and
        resource usage are on the{" "}
        <Link component={NextLink} href="/">
          home page
        </Link>
        &apos;s table view.
      </Typography>
      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}
      >
        {TABS.map((t) => (
          <Tab key={t} label={t} />
        ))}
      </Tabs>
      {TABS[tab] === "Logs" && <FleetLogsTab />}
      {TABS[tab] === "Vulnerabilities" && <FleetScansTab />}
    </Stack>
  );
}
