"use client";

import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import { useState } from "react";

export default function ConfirmDialog({
  open,
  title,
  text,
  confirmLabel = "Confirm",
  requireText,
  onClose,
  onConfirm,
}: {
  readonly open: boolean;
  readonly title: string;
  readonly text: string;
  readonly confirmLabel?: string;
  /** if set, user must type this string to enable the confirm button */
  readonly requireText?: string;
  readonly onClose: () => void;
  readonly onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const blocked = !!requireText && typed !== requireText;
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText>{text}</DialogContentText>
        {requireText && (
          <TextField
            autoFocus
            fullWidth
            size="small"
            margin="dense"
            placeholder={requireText}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            sx={{ mt: 2 }}
          />
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          color="error"
          variant="contained"
          disabled={blocked}
          onClick={() => {
            onConfirm();
            setTyped("");
          }}
        >
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
