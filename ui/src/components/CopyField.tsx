"use client";

import CheckIcon from "@mui/icons-material/Check";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { mono } from "@/theme";

export default function CopyField({ value, href }: { value: string; href?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Stack direction="row" spacing={0.5} sx={{ alignItems: "center", minWidth: 0 }}>
      <Typography
        variant="body2"
        component={href ? "a" : "span"}
        {...(href ? { href, target: "_blank", rel: "noreferrer" } : {})}
        sx={{
          fontFamily: mono,
          fontSize: "0.8rem",
          color: href ? "primary.main" : "text.secondary",
          textDecoration: "none",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          "&:hover": href ? { textDecoration: "underline" } : {},
        }}
      >
        {value}
      </Typography>
      <Tooltip title={copied ? "Copied!" : "Copy"}>
        <IconButton
          size="small"
          onClick={() => {
            navigator.clipboard.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? <CheckIcon fontSize="inherit" /> : <ContentCopyIcon fontSize="inherit" />}
        </IconButton>
      </Tooltip>
    </Stack>
  );
}
