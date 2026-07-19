"use client";

import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CopyField from "@/components/CopyField";
import StateChip from "@/components/StateChip";
import { useBuilds } from "@/lib/api";
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

export default function OverviewTab({ app }: { app: AppOut }) {
  const { data: builds } = useBuilds(app.id);
  const current = builds?.find((b) => b.id === app.current_build_id);

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
            <Row label="Main file">
              <span style={{ fontFamily: mono, fontSize: "0.8rem" }}>{app.main_file}</span>
            </Row>
            <Row label="Python">{app.python_version}</Row>
            <Row label="Visibility">
              {app.public
                ? "public"
                : `private — ${app.allowed_groups.length ? app.allowed_groups.join(", ") : "any signed-in user"}`}
            </Row>
            <Row label="Owned by">
              {app.owner_groups.length ? app.owner_groups.join(", ") : "admins only"}
            </Row>
            <Row label="Hibernation">
              {app.hibernate_enabled
                ? `sleeps after ${app.hibernate_after_seconds ? `${(app.hibernate_after_seconds / 3600).toFixed(1)}h` : "the platform default"} idle`
                : "disabled"}
            </Row>
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
