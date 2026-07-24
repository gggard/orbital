"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import CopyField from "@/components/CopyField";
import { createToken, useMe } from "@/lib/api";

export default function CreateTokenDialog({
  open,
  onClose,
  onCreated,
}: {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly onCreated: () => void;
}) {
  const { data: me } = useMe();
  const maxTtlDays = me?.api_token_max_ttl_days;
  const [name, setName] = useState("");
  const [ttlDays, setTtlDays] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<string | null>(null);

  const canSubmit = name.trim() !== "" && !busy;

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const token = await createToken({
        name: name.trim(),
        ttl_days: ttlDays ? Number(ttlDays) : undefined,
      });
      setCreated(token.token);
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setName("");
    setTtlDays("");
    setError("");
    setCreated(null);
  };

  return (
    <Dialog
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle>{created ? "Token created" : "New API token"}</DialogTitle>
      <DialogContent>
        {created ? (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="warning">
              Copy this token now — it won&apos;t be shown again.
            </Alert>
            <CopyField value={created} />
          </Stack>
        ) : (
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            <DialogContentText>
              Use this token to call the API with{" "}
              <Typography component="span" sx={{ fontFamily: "monospace", fontSize: "0.85em" }}>
                Authorization: Bearer &lt;token&gt;
              </Typography>{" "}
              instead of signing in through the browser.
            </DialogContentText>
            <TextField
              label="Name"
              required
              size="small"
              placeholder="e.g. laptop, CI pipeline"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <TextField
              label="Expires in (days)"
              type="number"
              size="small"
              placeholder={maxTtlDays ? String(maxTtlDays) : undefined}
              value={ttlDays}
              onChange={(e) => setTtlDays(e.target.value)}
              slotProps={{ htmlInput: { min: 1, max: maxTtlDays } }}
              helperText={
                maxTtlDays
                  ? `leave blank to use the platform maximum of ${maxTtlDays} days`
                  : "leave blank to use the platform's default (and maximum) TTL"
              }
            />
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {created ? (
          <Button
            onClick={() => {
              reset();
              onClose();
            }}
          >
            Close
          </Button>
        ) : (
          <>
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="contained" loading={busy} disabled={!canSubmit} onClick={submit}>
              Create
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}
