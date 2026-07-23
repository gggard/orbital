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

export type AppType = "streamlit" | "static";

export type ScanStatus = "pending" | "running" | "succeeded" | "failed";

export type Severity = "critical" | "high" | "medium" | "low" | "unknown";

export interface ScanOut {
  id: string;
  app_id: string;
  build_id: string | null;
  image: string;
  status: ScanStatus;
  trivy_version: string | null;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  unknown_count: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface AdminScanOut extends ScanOut {
  slug: string;
}

export interface VulnerabilityOut {
  vuln_id: string;
  pkg_name: string;
  installed_version: string;
  fixed_version: string | null;
  severity: Severity;
  title: string | null;
  target: string | null;
}

export interface AppOut {
  id: string;
  slug: string;
  repo_url: string;
  branch: string;
  app_type: AppType;
  main_file: string | null;
  python_version: string | null;
  build_command: string | null;
  output_dir: string;
  public: boolean;
  allowed_groups: string[];
  owner_groups: string[];
  tags: string[];
  state: AppState;
  error: string | null;
  current_build_id: string | null;
  latest_scan: ScanOut | null;
  url: string;
  webhook_path: string;
  hibernate_enabled: boolean;
  hibernate_after_seconds: number | null;
  poll_enabled: boolean;
  poll_interval_seconds: number | null;
  last_polled_at: string | null;
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
  app_type?: AppType; // defaults to "streamlit"
  main_file?: string; // streamlit only; defaults to "streamlit_app.py"
  python_version?: string; // streamlit only
  build_command?: string; // static only; unset = serve output_dir as-is
  output_dir?: string; // static only; defaults to "."
  public: boolean;
  allowed_groups: string[];
  tags?: string[];
  secrets_toml?: string;
  hibernate_enabled?: boolean;
  hibernate_after_seconds?: number;
  poll_enabled?: boolean;
  poll_interval_seconds?: number;
}

export interface Me {
  authenticated: boolean;
  auth_enabled: boolean;
  email: string;
  groups: string[];
  role: "admin" | "creator" | "viewer";
  can_create: boolean;
  can_publish: boolean;
  git_poll_default_interval_seconds: number;
  git_poll_min_interval_seconds: number;
  hibernation_timeout_seconds: number;
  hibernation_max_timeout_seconds: number;
  api_token_max_ttl_days: number;
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

export interface AdminAppOut extends AppOut {
  cpu: number | null; // cores, latest sample
  mem: number | null; // bytes, latest sample
}

export interface AdminTotals {
  app_count: number;
  running_count: number;
  cpu: number; // consumption, not a mutualized pool — apps have per-app limits, not a shared cap
  mem: number;
}

export interface AdminOverviewOut {
  totals: AdminTotals;
  apps: AdminAppOut[];
}

export interface AppUpdate {
  branch?: string;
  main_file?: string;
  python_version?: string;
  build_command?: string;
  output_dir?: string;
  public?: boolean;
  allowed_groups?: string[];
  owner_groups?: string[];
  tags?: string[];
  hibernate_enabled?: boolean;
  hibernate_after_seconds?: number;
  poll_enabled?: boolean;
  poll_interval_seconds?: number;
}

export interface TokenCreate {
  name: string;
  ttl_days?: number;
}

export interface TokenCreated {
  id: string;
  name: string;
  token: string; // raw secret, shown once
  created_at: string;
  expires_at: string;
}

export interface TokenOut {
  id: string;
  name: string;
  created_at: string;
  expires_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}
