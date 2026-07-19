export type AppState =
  | "created"
  | "building"
  | "deploying"
  | "running"
  | "sleeping"
  | "build_failed"
  | "deploy_failed"
  | "deleting";

export type BuildPhase = "pending" | "running" | "succeeded" | "failed";

export interface AppOut {
  id: string;
  slug: string;
  repo_url: string;
  branch: string;
  main_file: string;
  python_version: string;
  public: boolean;
  allowed_groups: string[];
  owner_groups: string[];
  state: AppState;
  error: string | null;
  current_build_id: string | null;
  url: string;
  webhook_path: string;
  hibernate_enabled: boolean;
  hibernate_after_seconds: number | null;
  last_active_at: string;
  created_at: string;
  updated_at: string;
}

export interface BuildOut {
  id: string;
  app_id: string;
  commit_sha: string | null;
  image: string | null;
  phase: BuildPhase;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface AppCreate {
  slug: string;
  repo_url: string;
  branch: string;
  main_file: string;
  python_version?: string;
  public: boolean;
  allowed_groups: string[];
  secrets_toml?: string;
  hibernate_enabled?: boolean;
  hibernate_after_seconds?: number;
}

export interface Me {
  authenticated: boolean;
  auth_enabled: boolean;
  email: string;
  groups: string[];
  role: "admin" | "creator" | "viewer";
  can_create: boolean;
  can_publish: boolean;
}

export interface MetricsPoint {
  t: number; // unix seconds
  cpu: number; // cores
  mem: number; // bytes
}

export interface MetricsOut {
  available: boolean;
  limits: { cpu: number; mem: number };
  current: MetricsPoint | null;
  series: MetricsPoint[];
}

export interface AnalyticsDailyPoint {
  date: string; // YYYY-MM-DD (UTC)
  views: number;
  unique_viewers: number;
}

export interface AnalyticsViewer {
  viewer: string;
  views: number;
  last_seen: string;
}

export interface AnalyticsOut {
  total_views: number;
  unique_viewers_1d: number;
  unique_viewers_7d: number;
  unique_viewers_30d: number;
  last_viewed_at: string | null;
  daily: AnalyticsDailyPoint[];
  viewers: AnalyticsViewer[];
}

export interface AppUpdate {
  branch?: string;
  main_file?: string;
  python_version?: string;
  public?: boolean;
  allowed_groups?: string[];
  owner_groups?: string[];
  hibernate_enabled?: boolean;
  hibernate_after_seconds?: number;
}
