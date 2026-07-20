"use client";

import Alert from "@mui/material/Alert";
import Link from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import NextLink from "next/link";
import FleetLogsTab from "@/components/admin/FleetLogsTab";
import { useMe } from "@/lib/api";

export default function AdminDashboard() {
  const { data: me, isLoading } = useMe();

  if (isLoading || !me) return <Skeleton variant="rounded" height={320} />;

  if (me.role !== "admin")
    return (
      <Alert severity="warning" sx={{ maxWidth: 480 }}>
        This page is restricted to platform admins.
      </Alert>
    );

  return (
    <Stack spacing={1}>
      <Typography variant="h5">Reconciler logs</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Live tail of the control plane&apos;s in-memory log buffer (reconciler + API). Resets when
        the control plane restarts; with multiple replicas, only the replica serving this request
        is shown. Fleet-wide app status and resource usage are on the{" "}
        <Link component={NextLink} href="/">
          home page
        </Link>
        &apos;s table view.
      </Typography>
      <FleetLogsTab />
    </Stack>
  );
}
