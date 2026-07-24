const MI = 2 ** 20;
const GI = 2 ** 30;

export function fmtCpu(cores: number): string {
  if (cores < 0.9995) return `${Math.round(cores * 1000)}m`;
  return `${cores.toFixed(cores < 10 ? 2 : 1)}`;
}

export function fmtMem(bytes: number): string {
  if (bytes < GI) return `${Math.round(bytes / MI)} MiB`;
  return `${(bytes / GI).toFixed(2)} GiB`;
}

const AGO_UNITS: [seconds: number, singular: string][] = [
  [60, "minute"],
  [60 * 60, "hour"],
  [60 * 60 * 24, "day"],
  [60 * 60 * 24 * 30, "month"],
  [60 * 60 * 24 * 365, "year"],
];

/** Relative time ("just now", "12 minutes ago", "3 days ago"). */
export function fmtAgo(iso: string, now: Date = new Date()): string {
  const diffSec = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  if (diffSec < 60) return "just now";

  let unitSeconds = 1;
  let label = "second";
  for (const [size, name] of AGO_UNITS) {
    if (diffSec < size) break;
    unitSeconds = size;
    label = name;
  }
  const count = Math.round(diffSec / unitSeconds);
  return `${count} ${label}${count === 1 ? "" : "s"} ago`;
}
