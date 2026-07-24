"use client";

import SaveIcon from "@mui/icons-material/Save";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useRouter } from "next/navigation";
import { useState } from "react";
import ConfirmDialog from "@/components/ConfirmDialog";
import CopyField from "@/components/CopyField";
import TagPicker from "@/components/TagPicker";
import { deleteApp, patchApp, useMe } from "@/lib/api";
import type { AppOut } from "@/lib/types";

const PYTHON_VERSIONS = ["3.12"];

// trims to at most 1 decimal, e.g. 10 -> "10", 0.5 -> "0.5"
const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

function computeDirty(
  app: AppOut,
  isStatic: boolean,
  fields: { branch: string; mainFile: string; python: string; buildCommand: string; outputDir: string },
): boolean {
  if (isStatic) {
    return (
      fields.branch !== app.branch ||
      fields.buildCommand !== (app.build_command ?? "") ||
      fields.outputDir !== app.output_dir
    );
  }
  return (
    fields.branch !== app.branch ||
    fields.mainFile !== (app.main_file ?? "") ||
    fields.python !== (app.python_version ?? "")
  );
}

function computeHibernateDirty(app: AppOut, hibernateEnabled: boolean, hibernateHours: string): boolean {
  return (
    hibernateEnabled !== app.hibernate_enabled ||
    (hibernateHours !== "" && Number(hibernateHours) * 3600 !== app.hibernate_after_seconds)
  );
}

function computePollDirty(app: AppOut, pollEnabled: boolean, pollMinutes: string): boolean {
  return (
    pollEnabled !== app.poll_enabled ||
    (pollMinutes !== "" && Number(pollMinutes) * 60 !== app.poll_interval_seconds)
  );
}

// Shared helper text for the poll-interval and hibernate-timeout fields: an
// error message when the value is out of range, otherwise the platform
// default/limit (or a generic hint if neither is known yet).
function intervalHelperText(outOfRange: string | false, hints: (string | false)[]): string {
  if (outOfRange) return outOfRange;
  return hints.filter(Boolean).join(" · ") || "leave blank to use the platform default";
}

function SourceFields({
  app,
  isStatic,
  branch,
  setBranch,
  mainFile,
  setMainFile,
  python,
  setPython,
  buildCommand,
  setBuildCommand,
  outputDir,
  setOutputDir,
}: Readonly<{
  app: AppOut;
  isStatic: boolean;
  branch: string;
  setBranch: (v: string) => void;
  mainFile: string;
  setMainFile: (v: string) => void;
  python: string;
  setPython: (v: string) => void;
  buildCommand: string;
  setBuildCommand: (v: string) => void;
  outputDir: string;
  setOutputDir: (v: string) => void;
}>) {
  return (
    <>
      <TextField
        label="Branch"
        size="small"
        fullWidth
        value={branch}
        onChange={(e) => setBranch(e.target.value)}
      />
      {isStatic ? (
        <>
          <TextField
            label="Build command (optional)"
            size="small"
            fullWidth
            placeholder="npm run build"
            value={buildCommand}
            onChange={(e) => setBuildCommand(e.target.value)}
          />
          <TextField
            label="Output directory"
            size="small"
            fullWidth
            value={outputDir}
            onChange={(e) => setOutputDir(e.target.value)}
          />
        </>
      ) : (
        <>
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
            {[...new Set([...PYTHON_VERSIONS, app.python_version ?? PYTHON_VERSIONS[0]])].map((v) => (
              <MenuItem key={v} value={v}>
                {v}
              </MenuItem>
            ))}
          </TextField>
        </>
      )}
    </>
  );
}

export default function SettingsTab({
  app,
  onSaved,
}: Readonly<{
  app: AppOut;
  onSaved: (msg: string) => void;
}>) {
  const router = useRouter();
  const { data: me } = useMe();
  const isStatic = app.app_type === "static";
  const [branch, setBranch] = useState(app.branch);
  const [mainFile, setMainFile] = useState(app.main_file ?? "");
  const [python, setPython] = useState(app.python_version ?? PYTHON_VERSIONS[0]);
  const [buildCommand, setBuildCommand] = useState(app.build_command ?? "");
  const [outputDir, setOutputDir] = useState(app.output_dir);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const [tags, setTags] = useState<string[]>(app.tags);
  const [tagsError, setTagsError] = useState("");
  const [tagsBusy, setTagsBusy] = useState(false);
  const tagsDirty = JSON.stringify(tags) !== JSON.stringify(app.tags);

  const [hibernateEnabled, setHibernateEnabled] = useState(app.hibernate_enabled);
  const [hibernateHours, setHibernateHours] = useState(
    app.hibernate_after_seconds ? String(app.hibernate_after_seconds / 3600) : "",
  );
  const [hibernateBusy, setHibernateBusy] = useState(false);
  const [hibernateError, setHibernateError] = useState("");

  const [pollEnabled, setPollEnabled] = useState(app.poll_enabled);
  const [pollMinutes, setPollMinutes] = useState(
    app.poll_interval_seconds ? String(app.poll_interval_seconds / 60) : "",
  );
  const [pollBusy, setPollBusy] = useState(false);
  const [pollError, setPollError] = useState("");

  const dirty = computeDirty(app, isStatic, { branch, mainFile, python, buildCommand, outputDir });
  const hibernateDirty = computeHibernateDirty(app, hibernateEnabled, hibernateHours);
  const pollDirty = computePollDirty(app, pollEnabled, pollMinutes);

  const pollDefaultMinutes = me ? me.git_poll_default_interval_seconds / 60 : null;
  const pollMinMinutes = me ? me.git_poll_min_interval_seconds / 60 : null;
  const pollBelowMin =
    pollMinutes !== "" && pollMinMinutes !== null && Number(pollMinutes) < pollMinMinutes;

  const hibernateDefaultHours = me ? me.hibernation_timeout_seconds / 3600 : null;
  const hibernateMaxHours = me ? me.hibernation_max_timeout_seconds / 3600 : null;
  const hibernateAboveMax =
    hibernateHours !== "" && hibernateMaxHours !== null && Number(hibernateHours) > hibernateMaxHours;

  const webhookUrl =
    typeof window !== "undefined" ? `${window.location.origin}${app.webhook_path}` : app.webhook_path;

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await patchApp(
        app.id,
        isStatic
          ? { branch, build_command: buildCommand || undefined, output_dir: outputDir }
          : { branch, main_file: mainFile, python_version: python },
      );
      onSaved("settings saved — rebuild scheduled");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const saveTags = async () => {
    setTagsBusy(true);
    setTagsError("");
    try {
      await patchApp(app.id, { tags });
      onSaved("tags saved");
    } catch (e) {
      setTagsError(e instanceof Error ? e.message : String(e));
    } finally {
      setTagsBusy(false);
    }
  };

  const saveHibernation = async () => {
    setHibernateBusy(true);
    setHibernateError("");
    try {
      await patchApp(app.id, {
        hibernate_enabled: hibernateEnabled,
        ...(hibernateHours !== "" && { hibernate_after_seconds: Math.round(Number(hibernateHours) * 3600) }),
      });
      onSaved("hibernation settings saved");
    } catch (e) {
      setHibernateError(e instanceof Error ? e.message : String(e));
    } finally {
      setHibernateBusy(false);
    }
  };

  const savePolling = async () => {
    setPollBusy(true);
    setPollError("");
    try {
      await patchApp(app.id, {
        poll_enabled: pollEnabled,
        ...(pollMinutes !== "" && { poll_interval_seconds: Math.round(Number(pollMinutes) * 60) }),
      });
      onSaved("auto-update settings saved");
    } catch (e) {
      setPollError(e instanceof Error ? e.message : String(e));
    } finally {
      setPollBusy(false);
    }
  };

  return (
    <Stack spacing={3} sx={{ maxWidth: 640 }}>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Tags
          </Typography>
          {tagsError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {tagsError}
            </Alert>
          )}
          <Stack spacing={2}>
            <TagPicker
              value={tags}
              onChange={setTags}
              helperText="type to search existing tags or add a new one and press Enter"
            />
            <Stack direction="row">
              <Button
                variant="contained"
                startIcon={<SaveIcon />}
                disabled={!tagsDirty}
                loading={tagsBusy}
                onClick={saveTags}
              >
                Save
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

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
              <SourceFields
                app={app}
                isStatic={isStatic}
                branch={branch}
                setBranch={setBranch}
                mainFile={mainFile}
                setMainFile={setMainFile}
                python={python}
                setPython={setPython}
                buildCommand={buildCommand}
                setBuildCommand={setBuildCommand}
                outputDir={outputDir}
                setOutputDir={setOutputDir}
              />
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

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Poll for updates
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Fallback for git hosts that can&apos;t deliver the webhook above: periodically
            check <b>{app.branch}</b> for new commits and redeploy if it has moved.
          </Typography>
          {pollError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {pollError}
            </Alert>
          )}
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Switch checked={pollEnabled} onChange={(e) => setPollEnabled(e.target.checked)} />
              <Typography variant="body2">Enable polling</Typography>
            </Stack>
            {pollEnabled && (
              <TextField
                label="Check interval (minutes)"
                type="number"
                size="small"
                sx={{ maxWidth: 260 }}
                placeholder={pollDefaultMinutes !== null ? fmt(pollDefaultMinutes) : "platform default"}
                value={pollMinutes}
                onChange={(e) => setPollMinutes(e.target.value)}
                error={pollBelowMin}
                slotProps={{ htmlInput: { min: pollMinMinutes ?? undefined } }}
                helperText={intervalHelperText(
                  pollBelowMin && `must be at least ${fmt(pollMinMinutes!)} min (platform minimum)`,
                  [
                    pollDefaultMinutes !== null && `platform default: ${fmt(pollDefaultMinutes)} min`,
                    pollMinMinutes !== null && `minimum: ${fmt(pollMinMinutes)} min`,
                  ],
                )}
              />
            )}
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Button
                variant="contained"
                startIcon={<SaveIcon />}
                disabled={!pollDirty || pollBelowMin}
                loading={pollBusy}
                onClick={savePolling}
              >
                Save
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Hibernation
          </Typography>
          {hibernateError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {hibernateError}
            </Alert>
          )}
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Switch
                checked={hibernateEnabled}
                onChange={(e) => setHibernateEnabled(e.target.checked)}
              />
              <Typography variant="body2">
                Sleep when idle (scales to zero, wakes automatically on the next visit)
              </Typography>
            </Stack>
            {hibernateEnabled && (
              <TextField
                label="Idle timeout (hours)"
                type="number"
                size="small"
                sx={{ maxWidth: 260 }}
                placeholder={hibernateDefaultHours !== null ? fmt(hibernateDefaultHours) : "platform default"}
                value={hibernateHours}
                onChange={(e) => setHibernateHours(e.target.value)}
                error={hibernateAboveMax}
                slotProps={{ htmlInput: { max: hibernateMaxHours ?? undefined } }}
                helperText={intervalHelperText(
                  hibernateAboveMax && `must be at most ${fmt(hibernateMaxHours!)}h (platform maximum)`,
                  [
                    hibernateDefaultHours !== null && `platform default: ${fmt(hibernateDefaultHours)}h`,
                    hibernateMaxHours !== null && `maximum: ${fmt(hibernateMaxHours)}h`,
                  ],
                )}
              />
            )}
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Button
                variant="contained"
                startIcon={<SaveIcon />}
                disabled={!hibernateDirty || hibernateAboveMax}
                loading={hibernateBusy}
                onClick={saveHibernation}
              >
                Save
              </Button>
            </Stack>
          </Stack>
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
