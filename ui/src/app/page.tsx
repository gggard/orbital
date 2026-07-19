"use client";

import AddIcon from "@mui/icons-material/Add";
import LaunchIcon from "@mui/icons-material/Launch";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import ReplayIcon from "@mui/icons-material/Replay";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Skeleton from "@mui/material/Skeleton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useRouter } from "next/navigation";
import { useState } from "react";
import ConfirmDialog from "@/components/ConfirmDialog";
import CreateAppDialog from "@/components/CreateAppDialog";
import Logo from "@/components/Logo";
import StateChip from "@/components/StateChip";
import { deleteApp, deployApp, rebootApp, useApps, useMe } from "@/lib/api";
import type { AppOut } from "@/lib/types";
import { mono } from "@/theme";

function AppCard({
  app,
  readOnly,
  onAction,
}: {
  app: AppOut;
  readOnly: boolean;
  onAction: (msg: string) => void;
}) {
  const router = useRouter();
  const [menuEl, setMenuEl] = useState<null | HTMLElement>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try {
      await fn();
      onAction(msg);
    } catch (e) {
      onAction(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Card sx={{ display: "flex", flexDirection: "column" }}>
      <CardActionArea
        onClick={() => router.push(`/apps/${app.id}`)}
        sx={{ p: 2, flexGrow: 1, alignItems: "stretch" }}
      >
        <Stack spacing={1}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <Typography variant="subtitle1" noWrap sx={{ fontWeight: 700 }}>
              {app.slug}
            </Typography>
            {!app.public && (
              <Tooltip
                title={
                  app.allowed_groups.length
                    ? `restricted to: ${app.allowed_groups.join(", ")}`
                    : "any signed-in user"
                }
              >
                <LockOutlinedIcon sx={{ fontSize: 16, color: "text.secondary" }} />
              </Tooltip>
            )}
            <Box sx={{ flexGrow: 1 }} />
            <StateChip state={app.state} />
          </Stack>
          <Typography
            variant="body2"
            color="text.secondary"
            noWrap
            sx={{ fontFamily: mono, fontSize: "0.75rem" }}
          >
            {app.repo_url.replace(/^https?:\/\//, "")}
          </Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {app.branch} · {app.main_file} · py{app.python_version}
          </Typography>
          {app.error && (
            <Tooltip title={app.error}>
              <Typography variant="caption" color="error" noWrap>
                {app.error}
              </Typography>
            </Tooltip>
          )}
        </Stack>
      </CardActionArea>
      <Stack direction="row" spacing={0.5} sx={{ px: 1, pb: 1 }}>
        <Tooltip title="Open app">
          <span>
            <IconButton
              size="small"
              disabled={app.state !== "running"}
              component="a"
              href={app.url}
              target="_blank"
              rel="noreferrer"
            >
              <LaunchIcon fontSize="inherit" />
            </IconButton>
          </span>
        </Tooltip>
        {!readOnly && (
          <Tooltip title="Redeploy (rebuild from git)">
            <IconButton
              size="small"
              onClick={() => act(() => deployApp(app.id), `redeploying ${app.slug}`)}
            >
              <ReplayIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
        <Box sx={{ flexGrow: 1 }} />
        {!readOnly && (
          <IconButton size="small" onClick={(e) => setMenuEl(e.currentTarget)}>
            <MoreVertIcon fontSize="inherit" />
          </IconButton>
        )}
        <Menu anchorEl={menuEl} open={!!menuEl} onClose={() => setMenuEl(null)}>
          <MenuItem
            onClick={() => {
              setMenuEl(null);
              act(() => rebootApp(app.id), `rebooting ${app.slug}`);
            }}
          >
            Reboot
          </MenuItem>
          <MenuItem
            sx={{ color: "error.main" }}
            onClick={() => {
              setMenuEl(null);
              setConfirmDelete(true);
            }}
          >
            Delete…
          </MenuItem>
        </Menu>
      </Stack>
      <ConfirmDialog
        open={confirmDelete}
        title={`Delete ${app.slug}?`}
        text="The app, its builds and its secrets will be removed permanently."
        confirmLabel="Delete"
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => {
          setConfirmDelete(false);
          act(() => deleteApp(app.id), `deleting ${app.slug}`);
        }}
      />
    </Card>
  );
}

export default function AppsOverview() {
  const { data: apps, error, isLoading } = useApps();
  const { data: me } = useMe();
  const [createOpen, setCreateOpen] = useState(false);
  const [snack, setSnack] = useState("");
  const canCreate = me?.can_create ?? false;
  const readOnly = me?.role === "viewer";

  return (
    <>
      <Stack direction="row" sx={{ alignItems: "center", mb: 3 }}>
        <Typography variant="h5">Apps</Typography>
        <Box sx={{ flexGrow: 1 }} />
        {canCreate && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            New app
          </Button>
        )}
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          control plane unreachable: {String(error.message ?? error)}
        </Alert>
      )}

      <Box
        sx={{
          display: "grid",
          gap: 2,
          gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "1fr 1fr 1fr" },
        }}
      >
        {isLoading && [0, 1, 2].map((i) => <Skeleton key={i} variant="rounded" height={150} />)}
        {apps?.map((app) => (
          <AppCard key={app.id} app={app} readOnly={readOnly} onAction={setSnack} />
        ))}
      </Box>

      {apps?.length === 0 && (
        <Stack spacing={2} sx={{ alignItems: "center", py: 10, color: "text.secondary" }}>
          <Box sx={{ opacity: 0.55 }}>
            <Logo size={64} variant="tile" />
          </Box>
          <Typography>
            {canCreate
              ? "No apps yet — deploy your first Streamlit app from a git repository."
              : "No apps are shared with your groups yet."}
          </Typography>
          {canCreate && (
            <Button variant="outlined" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
              Deploy your first app
            </Button>
          )}
        </Stack>
      )}

      <CreateAppDialog open={createOpen} onClose={() => setCreateOpen(false)} />
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
