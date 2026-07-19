"use client";

import SaveIcon from "@mui/icons-material/Save";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useRouter } from "next/navigation";
import { useState } from "react";
import ConfirmDialog from "@/components/ConfirmDialog";
import CopyField from "@/components/CopyField";
import { deleteApp, patchApp } from "@/lib/api";
import type { AppOut } from "@/lib/types";

const PYTHON_VERSIONS = ["3.12"];

export default function SettingsTab({
  app,
  onSaved,
}: {
  app: AppOut;
  onSaved: (msg: string) => void;
}) {
  const router = useRouter();
  const [branch, setBranch] = useState(app.branch);
  const [mainFile, setMainFile] = useState(app.main_file);
  const [python, setPython] = useState(app.python_version);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const dirty =
    branch !== app.branch || mainFile !== app.main_file || python !== app.python_version;

  const webhookUrl =
    typeof window !== "undefined" ? `${window.location.origin}${app.webhook_path}` : app.webhook_path;

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await patchApp(app.id, { branch, main_file: mainFile, python_version: python });
      onSaved("settings saved — rebuild scheduled");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack spacing={3} sx={{ maxWidth: 640 }}>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Source
          </Typography>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          <Stack spacing={2}>
            <Stack direction="row" spacing={2}>
              <TextField
                label="Branch"
                size="small"
                fullWidth
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
              />
              <TextField
                label="Main file"
                size="small"
                fullWidth
                value={mainFile}
                onChange={(e) => setMainFile(e.target.value)}
              />
              <TextField
                label="Python"
                size="small"
                select
                sx={{ minWidth: 100 }}
                value={python}
                onChange={(e) => setPython(e.target.value)}
              >
                {[...new Set([...PYTHON_VERSIONS, app.python_version])].map((v) => (
                  <MenuItem key={v} value={v}>
                    {v}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Button variant="contained" startIcon={<SaveIcon />} disabled={!dirty} loading={busy} onClick={save}>
                Save
              </Button>
              {dirty && (
                <Typography variant="caption" color="text.secondary">
                  saving triggers a rebuild + redeploy
                </Typography>
              )}
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Deploy webhook
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Add this URL as a push webhook (GitHub / GitLab / Gitea) to redeploy on every
            push to <b>{app.branch}</b>:
          </Typography>
          <CopyField value={webhookUrl} />
        </CardContent>
      </Card>

      <Card sx={{ borderColor: "error.main" }}>
        <CardContent>
          <Typography variant="h6" color="error" gutterBottom>
            Danger zone
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Deleting removes the app, its builds, images and secrets. This cannot be undone.
          </Typography>
          <Button variant="outlined" color="error" onClick={() => setConfirmDelete(true)}>
            Delete this app
          </Button>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete ${app.slug}?`}
        text={`Type the app slug ("${app.slug}") to confirm deletion.`}
        confirmLabel="Delete forever"
        requireText={app.slug}
        onClose={() => setConfirmDelete(false)}
        onConfirm={async () => {
          setConfirmDelete(false);
          await deleteApp(app.id);
          router.push("/");
        }}
      />
    </Stack>
  );
}
