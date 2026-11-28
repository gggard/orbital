import type { AppOut, BuildOut, Me, ScanOut, TokenOut, VulnerabilityOut } from "@/lib/types";

export function makeApp(overrides: Partial<AppOut> = {}): AppOut {
  return {
    id: "a1",
    slug: "my-app",
    repo_url: "https://example.com/repo.git",
    branch: "main",
    app_type: "streamlit",
    main_file: "app.py",
    python_version: "3.12",
    build_command: null,
    output_dir: "dist",
    public: false,
    allowed_groups: [],
    owner_groups: [],
    tags: [],
    state: "running",
    error: null,
    current_build_id: null,
    latest_scan: null,
    url: "https://my-app.example.com",
    webhook_path: "/webhooks/a1/token",
    hibernate_enabled: false,
    hibernate_after_seconds: null,
    poll_enabled: false,
    poll_interval_seconds: null,
    last_polled_at: null,
    last_active_at: "",
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-01T10:00:00Z",
    ...overrides,
  };
}

export function makeMe(overrides: Partial<Me> = {}): Me {
  return {
    authenticated: true,
    auth_enabled: true,
    email: "dev@example.com",
    groups: ["team"],
    role: "creator",
    can_create: true,
    can_publish: true,
    git_poll_default_interval_seconds: 600,
    git_poll_min_interval_seconds: 300,
    hibernation_timeout_seconds: 7200,
    hibernation_max_timeout_seconds: 86400,
    api_token_max_ttl_days: 90,
    ...overrides,
  };
}

export function makeBuild(overrides: Partial<BuildOut> = {}): BuildOut {
  return {
    id: "b1",
    app_id: "a1",
    commit_sha: "abcdef1234567890",
    image: "registry/app:b1",
    phase: "succeeded",
    error: null,
    created_at: "2026-11-01T10:00:00Z",
    finished_at: "2026-11-01T10:05:00Z",
    ...overrides,
  };
}

export function makeScan(overrides: Partial<ScanOut> = {}): ScanOut {
  return {
    id: "s1",
    app_id: "a1",
    build_id: "b1",
    image: "registry/app:b1",
    status: "succeeded",
    trivy_version: "0.60.0",
    critical_count: 1,
    high_count: 2,
    medium_count: 0,
    low_count: 3,
    unknown_count: 0,
    error: null,
    created_at: "2026-11-01T10:00:00Z",
    finished_at: "2026-11-01T10:01:00Z",
    ...overrides,
  };
}

export function makeVuln(overrides: Partial<VulnerabilityOut> = {}): VulnerabilityOut {
  return {
    vuln_id: "CVE-2026-0001",
    pkg_name: "openssl",
    installed_version: "3.0.0",
    fixed_version: "3.0.1",
    severity: "high",
    title: "Buffer overflow",
    target: "debian",
    ...overrides,
  };
}

export function makeToken(overrides: Partial<TokenOut> = {}): TokenOut {
  return {
    id: "t1",
    name: "ci",
    created_at: "2026-11-01T10:00:00Z",
    expires_at: "2027-01-30T10:00:00Z",
    last_used_at: null,
    revoked_at: null,
    ...overrides,
  };
}
