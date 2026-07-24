"use client";

import Box from "@mui/material/Box";
import { useEffect, useRef } from "react";
import { mono } from "@/theme";

export default function LogPane({
  text,
  follow = false,
  maxHeight = 480,
}: {
  readonly text: string;
  readonly follow?: boolean;
  readonly maxHeight?: number | string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (follow && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [text, follow]);

  return (
    <Box
      ref={ref}
      sx={{
        fontFamily: mono,
        fontSize: "0.75rem",
        lineHeight: 1.55,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        p: 2,
        borderRadius: 2,
        border: 1,
        borderColor: "divider",
        bgcolor: "background.paper",
        overflow: "auto",
        maxHeight,
        minHeight: 120,
      }}
    >
      {text || "— no output —"}
    </Box>
  );
}
