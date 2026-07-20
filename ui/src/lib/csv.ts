import { fmtCpu, fmtMem } from "@/lib/format";
import type { AdminAppOut } from "@/lib/types";

function csvCell(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

export function appsToCsv(apps: AdminAppOut[]): string {
  const header = ["Slug", "State", "Owner groups", "CPU", "Memory", "Updated"];
  const rows = apps.map((app) => [
    app.slug,
    app.state,
    app.owner_groups.join("; "),
    app.cpu === null ? "" : fmtCpu(app.cpu),
    app.mem === null ? "" : fmtMem(app.mem),
    new Date(app.updated_at).toISOString(),
  ]);
  return [header, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
}

export function downloadCsv(filename: string, csv: string) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
