"use client";

import PublicOutlinedIcon from "@mui/icons-material/PublicOutlined";
import TerminalOutlinedIcon from "@mui/icons-material/TerminalOutlined";
import Tooltip from "@mui/material/Tooltip";
import type { AppType } from "@/lib/types";

/** Small icon distinguishing streamlit (a running app) from static (served files). */
export default function AppTypeIcon({
  appType,
  fontSize = 16,
}: {
  readonly appType: AppType;
  readonly fontSize?: number;
}) {
  const isStatic = appType === "static";
  return (
    <Tooltip title={isStatic ? "Static site" : "Streamlit app"}>
      {isStatic ? (
        <PublicOutlinedIcon sx={{ fontSize, color: "text.secondary" }} />
      ) : (
        <TerminalOutlinedIcon sx={{ fontSize, color: "text.secondary" }} />
      )}
    </Tooltip>
  );
}
