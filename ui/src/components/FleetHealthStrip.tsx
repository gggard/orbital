"use client";

import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Typography from "@mui/material/Typography";
import type { AppsFilter } from "@/components/AppsFilterBar";
import { fmtCpu, fmtMem } from "@/lib/format";
import type { AdminAppOut, AppState } from "@/lib/types";
import { chartColors, mono } from "@/theme";

type Category = "running" | "in_progress" | "failed" | "sleeping";

const CATEGORY_STATES: Record<Category, AppState[]> = {
  running: ["running"],
  in_progress: ["created", "building", "deploying"],
  failed: ["build_failed", "deploy_failed"],
  sleeping: ["sleeping"],
};

function sameStates(a: AppState[], b: AppState[]): boolean {
  return a.length === b.length && b.every((s) => a.includes(s));
}

function countCategory(apps: AdminAppOut[], category: Category): number {
  const states = CATEGORY_STATES[category];
  return apps.filter((a) => states.includes(a.state)).length;
}

/** Fleet-wide health summary: 6 stat cards above the app grid/table. The
 * first four (Running/In progress/Failed/Sleeping) double as quick filters,
 * toggling the same `AppsFilter.states` the State dropdown in
 * AppsFilterBar edits - clicking the active one again clears it. */
export default function FleetHealthStrip({
  apps,
  totals,
  filter,
  onChange,
}: {
  readonly apps: AdminAppOut[];
  readonly totals: { cpu: number; mem: number } | null;
  readonly filter: AppsFilter;
  readonly onChange: (filter: AppsFilter) => void;
}) {
  const toggle = (category: Category) => {
    const states = CATEGORY_STATES[category];
    const active = sameStates(filter.states, states);
    onChange({ ...filter, states: active ? [] : states });
  };

  const cards: {
    key: Category | "cpu" | "mem";
    label: string;
    value: string;
    dotColor: string;
    valueColor?: string;
    category?: Category;
  }[] = [
    {
      key: "running",
      label: "Running",
      value: String(countCategory(apps, "running")),
      dotColor: "success.main",
      valueColor: "success.main",
      category: "running",
    },
    {
      key: "in_progress",
      label: "In progress",
      value: String(countCategory(apps, "in_progress")),
      dotColor: "warning.main",
      valueColor: "warning.main",
      category: "in_progress",
    },
    {
      key: "failed",
      label: "Failed",
      value: String(countCategory(apps, "failed")),
      dotColor: "error.main",
      valueColor: "error.main",
      category: "failed",
    },
    {
      key: "sleeping",
      label: "Sleeping",
      value: String(countCategory(apps, "sleeping")),
      dotColor: "text.disabled",
      category: "sleeping",
    },
    {
      key: "cpu",
      label: "Total cpu",
      value: totals ? fmtCpu(totals.cpu) : "—",
      dotColor: chartColors.cpu,
    },
    {
      key: "mem",
      label: "Total memory",
      value: totals ? fmtMem(totals.mem) : "—",
      dotColor: chartColors.mem,
    },
  ];

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: {
          xs: "repeat(2, 1fr)",
          sm: "repeat(3, 1fr)",
          md: "repeat(6, 1fr)",
        },
        gap: 1.5,
        mb: 3,
      }}
    >
      {cards.map((card) => {
        const active = card.category ? sameStates(filter.states, CATEGORY_STATES[card.category]) : false;
        const content = (
          <>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
              <Box
                sx={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  bgcolor: card.dotColor,
                  flexShrink: 0,
                }}
              />
              <Typography variant="caption" color="text.secondary" noWrap>
                {card.label}
              </Typography>
            </Box>
            <Typography
              sx={{
                fontFamily: mono,
                fontSize: "0.9rem",
                fontWeight: 600,
                color: card.valueColor ?? "text.primary",
              }}
              noWrap
            >
              {card.value}
            </Typography>
          </>
        );
        const sx = {
          border: 1,
          borderColor: "divider",
          borderRadius: 1.25,
          bgcolor: "background.paper",
          p: 1.25,
          display: "flex",
          flexDirection: "column",
          gap: 0.5,
          minWidth: 0,
          width: "100%",
          textAlign: "left",
          outline: active ? "2px solid" : "none",
          outlineColor: "primary.main",
          outlineOffset: "-1px",
        } as const;

        if (!card.category) {
          return (
            <Box key={card.key} sx={sx}>
              {content}
            </Box>
          );
        }
        return (
          <ButtonBase
            key={card.key}
            onClick={() => toggle(card.category as Category)}
            sx={sx}
            aria-pressed={active}
          >
            {content}
          </ButtonBase>
        );
      })}
    </Box>
  );
}
