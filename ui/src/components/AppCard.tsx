"use client";

import LaunchIcon from "@mui/icons-material/Launch";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import ReplayIcon from "@mui/icons-material/Replay";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useRouter } from "next/navigation";
import { useState } from "react";
import AppTypeIcon from "@/components/AppTypeIcon";
import ConfirmDialog from "@/components/ConfirmDialog";
import StateChip from "@/components/StateChip";
import { deleteApp, deployApp, rebootApp } from "@/lib/api";
import { fmtCpu, fmtMem } from "@/lib/format";
import type { AdminAppOut } from "@/lib/types";
import { mono } from "@/theme";

export default function AppCard({
  app,
  readOnly,
  onAction,
}: {
  app: AdminAppOut;
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
            <AppTypeIcon appType={app.app_type} />
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
            {app.app_type === "static"
              ? [app.branch, app.output_dir, app.build_command && `build: ${app.build_command}`]
                  .filter(Boolean)
                  .join(" · ")
              : `${app.branch} · ${app.main_file} · py${app.python_version}`}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <Typography variant="caption" color="text.secondary" noWrap sx={{ flexGrow: 1 }}>
              owner: {app.owner_groups.join(", ") || "—"}
            </Typography>
            {(app.cpu !== null || app.mem !== null) && (
              <Typography variant="caption" color="text.secondary" noWrap sx={{ fontFamily: mono }}>
                {app.cpu !== null ? fmtCpu(app.cpu) : "—"} · {app.mem !== null ? fmtMem(app.mem) : "—"}
              </Typography>
            )}
          </Stack>
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
              disabled={!["running", "sleeping"].includes(app.state)}
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
