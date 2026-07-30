"use client";

import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import GroupsOutlinedIcon from "@mui/icons-material/GroupsOutlined";
import LaunchIcon from "@mui/icons-material/Launch";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import ReplayIcon from "@mui/icons-material/Replay";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import Chip from "@mui/material/Chip";
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
import Sparkline from "@/components/Sparkline";
import StateChip from "@/components/StateChip";
import { deleteApp, deployApp, rebootApp } from "@/lib/api";
import { fmtAgo, fmtCpu, fmtMem } from "@/lib/format";
import type { AdminAppOut } from "@/lib/types";
import { chartColors, mono } from "@/theme";

export default function AppCard({
  app,
  readOnly,
  onAction,
}: {
  readonly app: AdminAppOut;
  readonly readOnly: boolean;
  readonly onAction: (msg: string) => void;
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

  const metaLine =
    app.app_type === "static"
      ? [app.branch, app.output_dir, app.build_command && `build: ${app.build_command}`]
          .filter(Boolean)
          .join(" · ")
      : `${app.branch} · py${app.python_version}`;
  const hasRestarts = !!app.restarts;

  return (
    <Card sx={{ display: "flex", flexDirection: "column" }}>
      <CardActionArea
        onClick={() => router.push(`/apps/${app.id}`)}
        sx={{
          p: 2,
          flexGrow: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "stretch",
          // CardActionArea centers its content vertically by default; when a
          // grid row stretches this card to match a taller sibling (e.g. one
          // with an error line), that leftover space must collect below the
          // content, not get split above it and push the header down.
          justifyContent: "flex-start",
        }}
      >
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

        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "1fr auto",
            gridTemplateRows: "auto auto",
            columnGap: 1.25,
            rowGap: 0.5,
            mt: 0.75,
            alignItems: "center",
          }}
        >
          <Typography
            sx={{
              gridColumn: 1,
              gridRow: 1,
              minWidth: 0,
              fontFamily: mono,
              fontSize: "0.75rem",
              color: "text.secondary",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {app.repo_url.replace(/^https?:\/\//, "")}
          </Typography>
          <Stack
            direction="row"
            spacing={0.5}
            sx={{
              gridColumn: 2,
              gridRow: 1,
              justifySelf: "end",
              flexWrap: "wrap",
              justifyContent: "flex-end",
              rowGap: 0.5,
              maxWidth: 130,
            }}
          >
            {app.tags.map((tag) => (
              <Chip key={tag} size="small" variant="outlined" label={tag} sx={{ height: 20 }} />
            ))}
          </Stack>
          <Stack
            direction="row"
            spacing={0.5}
            sx={{
              gridColumn: 1,
              gridRow: 2,
              minWidth: 0,
              alignItems: "center",
              color: "text.secondary",
            }}
          >
            <AccountTreeOutlinedIcon sx={{ fontSize: 13, opacity: 0.8, flexShrink: 0 }} />
            <Typography
              variant="caption"
              noWrap
              sx={{ overflow: "hidden", textOverflow: "ellipsis" }}
            >
              {metaLine}
            </Typography>
          </Stack>
          <Stack
            direction="row"
            spacing={0.5}
            sx={{
              gridColumn: 2,
              gridRow: 2,
              justifySelf: "end",
              maxWidth: 130,
              alignItems: "center",
              color: "text.secondary",
            }}
          >
            <GroupsOutlinedIcon sx={{ fontSize: 13, opacity: 0.8, flexShrink: 0 }} />
            <Typography variant="caption" noWrap>
              {app.owner_groups.join(", ") || "—"}
            </Typography>
          </Stack>
        </Box>

        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            columnGap: 1.25,
            rowGap: 0.75,
            mt: 1,
          }}
        >
          <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
            <Sparkline values={app.cpu_series} color={chartColors.cpu} />
            <Typography variant="caption" color="text.secondary" noWrap>
              cpu {app.cpu !== null ? fmtCpu(app.cpu) : "—"}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
            <Sparkline values={app.mem_series} color={chartColors.mem} />
            <Typography variant="caption" color="text.secondary" noWrap>
              mem {app.mem !== null ? fmtMem(app.mem) : "—"}
            </Typography>
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ gridColumn: 1 }} noWrap>
            updated {fmtAgo(app.updated_at)}
          </Typography>
          {hasRestarts && (
            <Tooltip title={`${app.restarts} container restart${app.restarts === 1 ? "" : "s"}`}>
              <Typography
                variant="caption"
                color="warning"
                sx={{ gridColumn: 2, fontWeight: 600 }}
                noWrap
              >
                ⟳ {app.restarts} restart{app.restarts === 1 ? "" : "s"}
              </Typography>
            </Tooltip>
          )}
        </Box>

        {app.error && (
          <Tooltip title={app.error}>
            <Typography variant="caption" color="error" noWrap sx={{ display: "block", mt: 1 }}>
              {app.error}
            </Typography>
          </Tooltip>
        )}
      </CardActionArea>
      <Stack direction="row" spacing={0.5} sx={{ px: 1, pb: 1, pt: 1, borderTop: 1, borderColor: "divider" }}>
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
