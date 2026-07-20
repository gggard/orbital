import type { AdminAppOut } from "@/lib/types";

export type SortKey = "slug" | "state" | "owner_groups" | "cpu" | "mem" | "updated_at";
export type SortDir = "asc" | "desc";

export interface AppsSort {
  key: SortKey;
  dir: SortDir;
}

export const DEFAULT_SORT: AppsSort = { key: "updated_at", dir: "desc" };

export const SORT_LABELS: Record<SortKey, string> = {
  slug: "Name",
  state: "State",
  owner_groups: "Owner",
  cpu: "CPU",
  mem: "Memory",
  updated_at: "Last update",
};

function sortValue(app: AdminAppOut, key: SortKey): string | number | null {
  switch (key) {
    case "slug":
      return app.slug.toLowerCase();
    case "state":
      return app.state;
    case "owner_groups":
      return app.owner_groups.join(", ").toLowerCase();
    case "cpu":
      return app.cpu;
    case "mem":
      return app.mem;
    case "updated_at":
      return app.updated_at;
  }
}

/** Nulls (unavailable CPU/mem for non-admin roles) always sort last, regardless of direction. */
export function applySort(apps: AdminAppOut[], sort: AppsSort): AdminAppOut[] {
  const mul = sort.dir === "asc" ? 1 : -1;
  return [...apps].sort((a, b) => {
    const va = sortValue(a, sort.key);
    const vb = sortValue(b, sort.key);
    if (va === null) return vb === null ? 0 : 1;
    if (vb === null) return -1;
    if (typeof va === "string") return mul * va.localeCompare(vb as string);
    return mul * (va - (vb as number));
  });
}

export function toggleSort(current: AppsSort, key: SortKey): AppsSort {
  if (current.key === key) return { key, dir: current.dir === "asc" ? "desc" : "asc" };
  return { key, dir: "asc" };
}
