"use client";

import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import type { Severity } from "@/lib/types";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "unknown"];

const ACCENT: Partial<Record<Severity, "error" | "warning">> = {
  critical: "error",
  high: "error",
  medium: "warning",
};

/** Multi-select severity toggle bar for CVE tables. Empty selection means
 * "no filter" (show every severity) - same convention as AppsFilter's
 * facets on the dashboard.
 */
export default function SeverityFilter({
  value,
  onChange,
}: {
  readonly value: Severity[];
  readonly onChange: (value: Severity[]) => void;
}) {
  return (
    <ToggleButtonGroup
      value={value}
      onChange={(_, next: Severity[]) => onChange(next)}
      size="small"
      aria-label="filter by severity"
    >
      {SEVERITIES.map((s) => {
        const accent = ACCENT[s];
        return (
          <ToggleButton
            key={s}
            value={s}
            aria-label={s}
            sx={{
              textTransform: "capitalize",
              ...(accent && {
                "&.Mui-selected": {
                  color: `${accent}.main`,
                  borderColor: `${accent}.main`,
                },
                "&.Mui-selected:hover": { borderColor: `${accent}.main` },
              }),
            }}
          >
            {s}
          </ToggleButton>
        );
      })}
    </ToggleButtonGroup>
  );
}
