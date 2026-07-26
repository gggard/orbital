"use client";

import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Link from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import NextLink from "next/link";
import { useActivity } from "@/lib/api";
import { fmtAgo } from "@/lib/format";
import type { ActivityEvent } from "@/lib/types";

const DOT_COLOR: Record<ActivityEvent["level"], string> = {
  success: "success.main",
  warning: "warning.main",
  error: "error.main",
  info: "info.main",
  default: "text.disabled",
};

/** Sticky "recent activity" rail alongside the app grid/table: a short feed
 * of fleet-wide events (deploys, hibernation, failures…) with who/what
 * triggered them. Admin-only, same gating as the fleet-health cpu/mem
 * totals (both come from admin-only endpoints). */
export default function ActivityRail({ enabled }: { readonly enabled: boolean }) {
  const { data: events, isLoading } = useActivity(enabled);

  if (!enabled) return null;

  return (
    <Card
      variant="outlined"
      sx={{ p: 2, position: "sticky", top: 72, alignSelf: "start" }}
    >
      <Typography variant="subtitle2" sx={{ fontWeight: 650, mb: 1.5 }}>
        Recent activity
      </Typography>
      {isLoading && (
        <Stack spacing={1.5}>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} variant="rounded" height={32} />
          ))}
        </Stack>
      )}
      {!isLoading && (!events || events.length === 0) && (
        <Typography variant="body2" color="text.secondary">
          No recent activity.
        </Typography>
      )}
      {!isLoading && events && events.length > 0 && (
        <Stack spacing={1.5}>
          {events.map((ev) => (
            <Stack key={ev.id} direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  bgcolor: DOT_COLOR[ev.level],
                  mt: 0.75,
                  flexShrink: 0,
                }}
              />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" sx={{ lineHeight: 1.4 }}>
                  <Box component="span" sx={{ fontWeight: 600, fontFamily: "monospace" }}>
                    {ev.slug}
                  </Box>{" "}
                  {ev.text}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {ev.actor} · {fmtAgo(ev.created_at)}
                </Typography>
              </Box>
            </Stack>
          ))}
        </Stack>
      )}
      <Box sx={{ mt: 2, pt: 1.5, borderTop: 1, borderColor: "divider" }}>
        <Link component={NextLink} href="/admin" variant="body2" sx={{ fontWeight: 600 }}>
          View all activity →
        </Link>
      </Box>
    </Card>
  );
}
