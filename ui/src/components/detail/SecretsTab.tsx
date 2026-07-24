"use client";

import SaveIcon from "@mui/icons-material/Save";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";
import { putSecrets, useSecrets } from "@/lib/api";
import { mono } from "@/theme";

export default function SecretsTab({
  appId,
  onSaved,
}: {
  readonly appId: string;
  readonly onSaved: () => void;
}) {
  const { data: current, isLoading, mutate } = useSecrets(appId);
  const [value, setValue] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (value === null && current !== undefined) setValue(current);
  }, [current, value]);

  if (isLoading || value === null) return <Skeleton variant="rounded" height={280} />;

  const dirty = value !== current;

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await putSecrets(appId, value);
      await mutate(value, { revalidate: false });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack spacing={2} sx={{ maxWidth: 720 }}>
      <Typography variant="body2" color="text.secondary">
        TOML exposed to the app as <code>st.secrets</code> (mounted at{" "}
        <code>.streamlit/secrets.toml</code>). Saving restarts the app — no rebuild.
      </Typography>
      {error && <Alert severity="error">{error}</Alert>}
      <TextField
        multiline
        minRows={12}
        maxRows={28}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={'api_key = "..."\n\n[db]\nhost = "..."'}
        slotProps={{ input: { sx: { fontFamily: mono, fontSize: "0.8rem" } } }}
      />
      <Stack direction="row" spacing={1}>
        <Button
          variant="contained"
          startIcon={<SaveIcon />}
          disabled={!dirty}
          loading={busy}
          onClick={save}
        >
          Save & restart app
        </Button>
        <Button disabled={!dirty || busy} onClick={() => setValue(current ?? "")}>
          Discard changes
        </Button>
      </Stack>
    </Stack>
  );
}
