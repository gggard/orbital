"use client";

import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useRouter } from "next/navigation";
import { useState } from "react";
import GroupPicker from "@/components/GroupPicker";
import TagPicker from "@/components/TagPicker";
import { createApp, useMe } from "@/lib/api";
import type { AppType } from "@/lib/types";
import { mono } from "@/theme";

const SLUG_RE = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;
const PYTHON_VERSIONS = ["3.12"];

export default function CreateAppDialog({
  open,
  onClose,
}: {
  readonly open: boolean;
  readonly onClose: () => void;
}) {
  const router = useRouter();
  const { data: me } = useMe();
  const mayPublish = me?.can_publish ?? true;
  const [slug, setSlug] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [appType, setAppType] = useState<AppType>("streamlit");
  const [mainFile, setMainFile] = useState("streamlit_app.py");
  const [python, setPython] = useState(PYTHON_VERSIONS[0]);
  const [buildCommand, setBuildCommand] = useState("");
  const [outputDir, setOutputDir] = useState(".");
  const [isPublic, setIsPublic] = useState(true);
  const [groups, setGroups] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [secrets, setSecrets] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const isStatic = appType === "static";
  const slugOk = SLUG_RE.test(slug);
  const canSubmit = slugOk && repoUrl.trim() !== "" && !busy;

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const effectivePublic = isPublic && mayPublish;
      const app = await createApp({
        slug,
        repo_url: repoUrl.trim(),
        branch: branch.trim() || "main",
        app_type: appType,
        ...(isStatic
          ? { build_command: buildCommand.trim() || undefined, output_dir: outputDir.trim() || "." }
          : { main_file: mainFile.trim() || "streamlit_app.py", python_version: python }),
        public: effectivePublic,
        allowed_groups: effectivePublic ? [] : groups,
        tags,
        secrets_toml: isStatic ? undefined : secrets.trim() || undefined,
      });
      onClose();
      router.push(`/apps/${app.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Deploy a new app</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            label="Slug"
            required
            size="small"
            value={slug}
            onChange={(e) => setSlug(e.target.value.toLowerCase())}
            error={slug !== "" && !slugOk}
            helperText={`the app URL becomes <slug>.<apps-domain>${
              slug && !slugOk ? " — lowercase letters, digits and dashes only" : ""
            }`}
          />
          <TextField
            label="Git repository URL"
            required
            size="small"
            placeholder="https://github.com/org/repo"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
          />
          <Stack direction="row" spacing={2}>
            <TextField
              label="Branch"
              size="small"
              fullWidth
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
            />
            <TextField
              label="App type"
              size="small"
              select
              sx={{ minWidth: 140 }}
              value={appType}
              onChange={(e) => setAppType(e.target.value as AppType)}
            >
              <MenuItem value="streamlit">Streamlit</MenuItem>
              <MenuItem value="static">Static site</MenuItem>
            </TextField>
          </Stack>
          {isStatic ? (
            <Stack direction="row" spacing={2}>
              <TextField
                label="Build command (optional)"
                size="small"
                fullWidth
                placeholder="npm run build"
                value={buildCommand}
                onChange={(e) => setBuildCommand(e.target.value)}
                helperText="leave empty to serve the repo's files as-is"
              />
              <TextField
                label="Output directory"
                size="small"
                fullWidth
                value={outputDir}
                onChange={(e) => setOutputDir(e.target.value)}
              />
            </Stack>
          ) : (
            <Stack direction="row" spacing={2}>
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
                {PYTHON_VERSIONS.map((v) => (
                  <MenuItem key={v} value={v}>
                    {v}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
          )}
          <TagPicker
            value={tags}
            onChange={setTags}
            helperText="type to search existing tags or add a new one and press Enter"
          />
          <FormControlLabel
            control={
              <Switch
                checked={isPublic && mayPublish}
                disabled={!mayPublish}
                onChange={(e) => setIsPublic(e.target.checked)}
              />
            }
            label={
              <Typography variant="body2">
                {mayPublish
                  ? "Public — anyone with the URL can open the app"
                  : "Public sharing is restricted to specific groups on this platform"}
              </Typography>
            }
          />
          {!(isPublic && mayPublish) && (
            <GroupPicker
              value={groups}
              onChange={setGroups}
              label="Allowed groups"
              helperText="type to filter or add a group and press Enter — empty means any signed-in user"
            />
          )}
          {!isStatic && (
            <Accordion variant="outlined" disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="body2">Secrets (optional)</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <TextField
                  fullWidth
                  multiline
                  minRows={5}
                  placeholder={'api_key = "..."\n\n[db]\nhost = "..."'}
                  value={secrets}
                  onChange={(e) => setSecrets(e.target.value)}
                  slotProps={{
                    input: { sx: { fontFamily: mono, fontSize: "0.8rem" } },
                  }}
                  helperText="TOML, exposed to the app via st.secrets"
                />
              </AccordionDetails>
            </Accordion>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" loading={busy} disabled={!canSubmit} onClick={submit}>
          Deploy
        </Button>
      </DialogActions>
    </Dialog>
  );
}
