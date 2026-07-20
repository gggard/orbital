"use client";

import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlineOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Skeleton from "@mui/material/Skeleton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import ConfirmDialog from "@/components/ConfirmDialog";
import CreateTokenDialog from "@/components/CreateTokenDialog";
import { revokeToken, useTokens } from "@/lib/api";
import type { TokenOut } from "@/lib/types";

export default function TokensPage() {
  const { data: tokens, error, isLoading, mutate } = useTokens();
  const [createOpen, setCreateOpen] = useState(false);
  const [toRevoke, setToRevoke] = useState<TokenOut | null>(null);
  const [snack, setSnack] = useState("");

  const revoke = async () => {
    if (!toRevoke) return;
    try {
      await revokeToken(toRevoke.id);
      setSnack(`Revoked "${toRevoke.name}"`);
      mutate();
    } catch (e) {
      setSnack(e instanceof Error ? e.message : String(e));
    } finally {
      setToRevoke(null);
    }
  };

  return (
    <>
      <Stack direction="row" spacing={2} sx={{ alignItems: "flex-start", mb: 2 }}>
        <Box>
          <Typography variant="h5">My tokens</Typography>
          <Typography variant="body2" color="text.secondary">
            Personal API tokens for scripts and automation — use them with{" "}
            <Typography component="span" sx={{ fontFamily: "monospace", fontSize: "0.85em" }}>
              Authorization: Bearer &lt;token&gt;
            </Typography>{" "}
            instead of a browser session.
          </Typography>
        </Box>
        <Box sx={{ flexGrow: 1 }} />
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
          New token
        </Button>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          control plane unreachable: {String(error.message ?? error)}
        </Alert>
      )}

      {isLoading ? (
        <Skeleton variant="rounded" height={200} />
      ) : !tokens || tokens.length === 0 ? (
        <Stack spacing={1} sx={{ alignItems: "center", py: 8, color: "text.secondary" }}>
          <Typography>No API tokens yet.</Typography>
          <Button size="small" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            Create your first token
          </Button>
        </Stack>
      ) : (
        <TableContainer component={Card}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Created</TableCell>
                <TableCell>Expires</TableCell>
                <TableCell>Last used</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {tokens.map((t) => {
                const revoked = !!t.revoked_at;
                const expired = !revoked && new Date(t.expires_at) < new Date();
                return (
                  <TableRow key={t.id} hover>
                    <TableCell>{t.name}</TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {new Date(t.created_at).toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {new Date(t.expires_at).toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {t.last_used_at ? new Date(t.last_used_at).toLocaleString() : "never"}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {revoked ? (
                        <Chip size="small" label="revoked" />
                      ) : expired ? (
                        <Chip size="small" label="expired" color="warning" />
                      ) : (
                        <Chip size="small" label="active" color="success" variant="outlined" />
                      )}
                    </TableCell>
                    <TableCell align="right">
                      {!revoked && (
                        <Tooltip title="Revoke">
                          <IconButton size="small" onClick={() => setToRevoke(t)}>
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <CreateTokenDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => mutate()}
      />
      <ConfirmDialog
        open={!!toRevoke}
        title="Revoke token"
        text={`Revoke "${toRevoke?.name}"? Anything using it will immediately lose access.`}
        confirmLabel="Revoke"
        onClose={() => setToRevoke(null)}
        onConfirm={revoke}
      />
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
