import { describe, expect, it } from "vitest";
import { hibernationLabel, visibilityLabel } from "./OverviewTab";
import type { AppOut } from "@/lib/types";

function app(overrides: Partial<AppOut>): AppOut {
  return {
    id: "1",
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
    webhook_path: "/webhooks/1",
    hibernate_enabled: false,
    hibernate_after_seconds: null,
    poll_enabled: false,
    poll_interval_seconds: null,
    last_polled_at: null,
    last_active_at: "",
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

describe("visibilityLabel", () => {
  it("is 'public' for public apps", () => {
    expect(visibilityLabel(app({ public: true }))).toBe("public");
  });

  it("lists the allowed groups for private apps", () => {
    expect(visibilityLabel(app({ public: false, allowed_groups: ["team-a", "team-b"] }))).toBe(
      "private — team-a, team-b",
    );
  });

  it("falls back to 'any signed-in user' when no groups are set", () => {
    expect(visibilityLabel(app({ public: false, allowed_groups: [] }))).toBe(
      "private — any signed-in user",
    );
  });
});

describe("hibernationLabel", () => {
  it("is 'disabled' when hibernation is off", () => {
    expect(hibernationLabel(app({ hibernate_enabled: false }), 1)).toBe("disabled");
  });

  it("uses the app's own timeout when set", () => {
    const a = app({ hibernate_enabled: true, hibernate_after_seconds: 7200 });
    expect(hibernationLabel(a, 2)).toBe("sleeps after 2.0h idle");
  });

  it("labels the platform default when no timeout is set on the app but one is known", () => {
    const a = app({ hibernate_enabled: true, hibernate_after_seconds: null });
    expect(hibernationLabel(a, 0.5)).toBe("sleeps after 0.5h (platform default) idle");
  });

  it("falls back to a generic message when no default is known yet", () => {
    const a = app({ hibernate_enabled: true, hibernate_after_seconds: null });
    expect(hibernationLabel(a, null)).toBe("sleeps after the platform default idle");
  });
});
