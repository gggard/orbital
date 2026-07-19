"use client";

import SaveIcon from "@mui/icons-material/Save";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import GroupPicker from "@/components/GroupPicker";
import { patchApp, useMe } from "@/lib/api";
import type { AppOut } from "@/lib/types";

function ViewerAccessCard({ app, onSaved }: { app: AppOut; onSaved: () => void }) {
  const { data: me } = useMe();
  const [isPublic, setIsPublic] = useState(app.public);
  const [groups, setGroups] = useState<string[]>(app.allowed_groups);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // platform policy: making a private app public may be restricted by group
  const publishBlocked = !app.public && !(me?.can_publish ?? true);

  const dirty =
    isPublic !== app.public ||
    JSON.stringify(groups) !== JSON.stringify(app.allowed_groups);

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await patchApp(app.id, { public: isPublic, allowed_groups: isPublic ? [] : groups });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Viewer access
        </Typography>
        <Stack spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}
          <FormControlLabel
            control={
              <Switch
                checked={isPublic}
                disabled={publishBlocked}
                onChange={(e) => setIsPublic(e.target.checked)}
              />
            }
            label={
              publishBlocked
                ? "Private — public sharing is restricted to specific groups on this platform"
                : isPublic
                  ? "Public — anyone with the URL"
                  : "Private — sign-in required"
            }
          />
          {!isPublic && (
            <GroupPicker
              value={groups}
              onChange={setGroups}
              label="Allowed viewer groups"
              helperText="type to filter — OIDC groups allowed to open the app; empty means any signed-in user"
            />
          )}
          <Typography variant="body2" color="text.secondary">
            Changes apply immediately — no rebuild.
          </Typography>
          <Stack direction="row">
            <Button variant="contained" startIcon={<SaveIcon />} disabled={!dirty} loading={busy} onClick={save}>
              Save
            </Button>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

function OwnershipCard({ app, onSaved }: { app: AppOut; onSaved: () => void }) {
  const { data: me } = useMe();
  const [ownerGroups, setOwnerGroups] = useState<string[]>(app.owner_groups);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const isAdmin = me?.role === "admin";

  const dirty = JSON.stringify(ownerGroups) !== JSON.stringify(app.owner_groups);
  // non-admins must keep at least one of their own groups (server enforces too)
  const lockedOut =
    !isAdmin && !ownerGroups.some((g) => (me?.groups ?? []).includes(g));

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await patchApp(app.id, { owner_groups: ownerGroups });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Ownership
        </Typography>
        <Stack spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}
          <GroupPicker
            value={ownerGroups}
            onChange={setOwnerGroups}
            label="Owner groups"
            helperText="type to filter — groups whose members can see and manage this app (admins always can)"
            extraOptions={[...(me?.groups ?? []), ...app.owner_groups]}
          />
          {lockedOut && (
            <Alert severity="warning">
              {ownerGroups.length === 0
                ? "Owner groups cannot be empty — the app would become visible to admins only."
                : "You must keep at least one of your own groups, or you would lose access. Ask an admin to transfer ownership entirely."}
            </Alert>
          )}
          {isAdmin && ownerGroups.length === 0 && (
            <Alert severity="info">
              With no owner groups, only admins will see this app.
            </Alert>
          )}
          <Stack direction="row">
            <Button
              variant="contained"
              startIcon={<SaveIcon />}
              disabled={!dirty || lockedOut}
              loading={busy}
              onClick={save}
            >
              Save ownership
            </Button>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function SharingTab({
  app,
  onSaved,
}: {
  app: AppOut;
  onSaved: () => void;
}) {
  return (
    <Stack spacing={3} sx={{ maxWidth: 560 }}>
      <ViewerAccessCard app={app} onSaved={onSaved} />
      <OwnershipCard app={app} onSaved={onSaved} />
    </Stack>
  );
}
