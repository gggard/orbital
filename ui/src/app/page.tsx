"use client";

import AddIcon from "@mui/icons-material/Add";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Skeleton from "@mui/material/Skeleton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import AppCard from "@/components/AppCard";
import CreateAppDialog from "@/components/CreateAppDialog";
import Logo from "@/components/Logo";
import { useApps, useMe } from "@/lib/api";

export default function AppsOverview() {
  const { data: apps, error, isLoading } = useApps();
  const { data: me } = useMe();
  const [createOpen, setCreateOpen] = useState(false);
  const [snack, setSnack] = useState("");
  const canCreate = me?.can_create ?? false;
  const readOnly = me?.role === "viewer";

  return (
    <>
      <Stack direction="row" sx={{ alignItems: "center", mb: 3 }}>
        <Typography variant="h5">Apps</Typography>
        <Box sx={{ flexGrow: 1 }} />
        {canCreate && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            New app
          </Button>
        )}
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          control plane unreachable: {String(error.message ?? error)}
        </Alert>
      )}

      <Box
        sx={{
          display: "grid",
          gap: 2,
          gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "1fr 1fr 1fr" },
        }}
      >
        {isLoading && [0, 1, 2].map((i) => <Skeleton key={i} variant="rounded" height={150} />)}
        {apps?.map((app) => (
          <AppCard key={app.id} app={app} readOnly={readOnly} onAction={setSnack} />
        ))}
      </Box>

      {apps?.length === 0 && (
        <Stack spacing={2} sx={{ alignItems: "center", py: 10, color: "text.secondary" }}>
          <Box sx={{ opacity: 0.55 }}>
            <Logo size={64} variant="tile" />
          </Box>
          <Typography>
            {canCreate
              ? "No apps yet — deploy your first Streamlit app from a git repository."
              : "No apps are shared with your groups yet."}
          </Typography>
          {canCreate && (
            <Button variant="outlined" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
              Deploy your first app
            </Button>
          )}
        </Stack>
      )}

      <CreateAppDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      <Snackbar
        open={!!snack}
        autoHideDuration={4000}
        onClose={() => setSnack("")}
        message={snack}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      />
    </>
  );
}
