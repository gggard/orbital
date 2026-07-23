"use client";

import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CopyField from "@/components/CopyField";
import StateChip from "@/components/StateChip";
import { useBuilds, useMe } from "@/lib/api";
import type { AppOut } from "@/lib/types";
import { mono } from "@/theme";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Stack direction="row" spacing={2} sx={{ alignItems: "baseline" }}>
      <Typography variant="body2" color="text.secondary" sx={{ width: 120, flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography variant="body2" component="div" sx={{ minWidth: 0 }}>
        {children}
      </Typography>
    </Stack>
  );
}

function visibilityLabel(app: AppOut): string {
  if (app.public) return "public";
  const scope = app.allowed_groups.length ? app.allowed_groups.join(", ") : "any signed-in user";
  return `private — ${scope}`;
}

function hibernationLabel(app: AppOut, hibernateHours: number | null): string {
  if (!app.hibernate_enabled) return "disabled";
  if (app.hibernate_after_seconds) return `sleeps after ${hibernateHours!.toFixed(1)}h idle`;
  if (hibernateHours !== null) {
    return `sleeps after ${hibernateHours.toFixed(1)}h (platform default) idle`;
  }
  return "sleeps after the platform default idle";
}

function DefinitionFields({ app }: Readonly<{ app: AppOut }>) {
  if (app.app_type === "static") {
    return (
      <>
        <Row label="Output directory">
          <span style={{ fontFamily: mono, fontSize: "0.8rem" }}>{app.output_dir}</span>
        </Row>
        {app.build_command && (
          <Row label="Build command">
            <span style={{ fontFamily: mono, fontSize: "0.8rem" }}>{app.build_command}</span>
          </Row>
        )}
      </>
    );
  }
  return (
    <>
      <Row label="Main file">
        <span style={{ fontFamily: mono, fontSize: "0.8rem" }}>{app.main_file}</span>
      </Row>
      <Row label="Python">{app.python_version}</Row>
    </>
  );
}

export default function OverviewTab({ app }: { app: AppOut }) {
  const { data: builds } = useBuilds(app.id);
  const { data: me } = useMe();
  const current = builds?.find((b) => b.id === app.current_build_id);
  const hibernateHours = app.hibernate_after_seconds
    ? app.hibernate_after_seconds / 3600
    : me
      ? me.hibernation_timeout_seconds / 3600
      : null;

  return (
    <Stack spacing={2} direction={{ xs: "column", md: "row" }} sx={{ alignItems: "flex-start" }}>
      <Card sx={{ flex: 2, width: "100%" }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Definition
          </Typography>
          <Stack spacing={1.2}>
            <Row label="Repository">
              <CopyField value={app.repo_url} href={app.repo_url} />
            </Row>
            <Row label="Branch">{app.branch}</Row>
            <DefinitionFields app={app} />
            <Row label="Visibility">{visibilityLabel(app)}</Row>
            <Row label="Owned by">
              {app.owner_groups.length ? app.owner_groups.join(", ") : "admins only"}
            </Row>
            {app.tags.length > 0 && (
              <Row label="Tags">
                <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", rowGap: 0.5 }}>
                  {app.tags.map((tag) => (
                    <Chip key={tag} size="small" variant="outlined" label={tag} />
                  ))}
                </Stack>
              </Row>
            )}
            <Row label="Hibernation">{hibernationLabel(app, hibernateHours)}</Row>
            {app.state !== "sleeping" && (
              <Row label="Last active">{new Date(app.last_active_at).toLocaleString()}</Row>
            )}
            <Row label="Created">{new Date(app.created_at).toLocaleString()}</Row>
            <Row label="Updated">{new Date(app.updated_at).toLocaleString()}</Row>
          </Stack>
        </CardContent>
      </Card>

      <Card sx={{ flex: 1, width: "100%" }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Current build
          </Typography>
          {current ? (
            <Stack spacing={1.2}>
              <Row label="Build">
                <span style={{ fontFamily: mono, fontSize: "0.8rem" }}>{current.id}</span>
              </Row>
              <Row label="Commit">
                <span style={{ fontFamily: mono, fontSize: "0.8rem" }}>
                  {current.commit_sha?.slice(0, 10) ?? "—"}
                </span>
              </Row>
              <Row label="Phase">
                <StateChip state={current.phase} />
              </Row>
              <Row label="Started">{new Date(current.created_at).toLocaleString()}</Row>
              <Row label="Finished">
                {current.finished_at ? new Date(current.finished_at).toLocaleString() : "—"}
              </Row>
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              no build yet
            </Typography>
          )}
        </CardContent>
      </Card>
    </Stack>
  );
}
