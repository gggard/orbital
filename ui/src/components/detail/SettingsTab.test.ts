import { describe, expect, it } from "vitest";
import {
  computeDirty,
  computeHibernateDirty,
  computePollDirty,
  intervalHelperText,
} from "./SettingsTab";
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

describe("computeDirty", () => {
  const fields = { branch: "main", mainFile: "app.py", python: "3.12", buildCommand: "", outputDir: "dist" };

  it("is false when static fields match the app", () => {
    const a = app({ app_type: "static", branch: "main", build_command: null, output_dir: "dist" });
    expect(computeDirty(a, true, fields)).toBe(false);
  });

  it("is true when the static branch changed", () => {
    const a = app({ app_type: "static", branch: "main", build_command: null, output_dir: "dist" });
    expect(computeDirty(a, true, { ...fields, branch: "dev" })).toBe(true);
  });

  it("is true when the static build command changed", () => {
    const a = app({ app_type: "static", branch: "main", build_command: null, output_dir: "dist" });
    expect(computeDirty(a, true, { ...fields, buildCommand: "npm run build" })).toBe(true);
  });

  it("is true when the static output dir changed", () => {
    const a = app({ app_type: "static", branch: "main", build_command: null, output_dir: "dist" });
    expect(computeDirty(a, true, { ...fields, outputDir: "build" })).toBe(true);
  });

  it("is false when streamlit fields match the app", () => {
    const a = app({ branch: "main", main_file: "app.py", python_version: "3.12" });
    expect(computeDirty(a, false, fields)).toBe(false);
  });

  it("is true when the streamlit main file changed", () => {
    const a = app({ branch: "main", main_file: "app.py", python_version: "3.12" });
    expect(computeDirty(a, false, { ...fields, mainFile: "main.py" })).toBe(true);
  });

  it("is true when the streamlit python version changed", () => {
    const a = app({ branch: "main", main_file: "app.py", python_version: "3.12" });
    expect(computeDirty(a, false, { ...fields, python: "3.13" })).toBe(true);
  });
});

describe("computeHibernateDirty", () => {
  it("is false when the toggle and timeout match the app", () => {
    const a = app({ hibernate_enabled: true, hibernate_after_seconds: 3600 });
    expect(computeHibernateDirty(a, true, "1")).toBe(false);
  });

  it("is true when the toggle changed", () => {
    const a = app({ hibernate_enabled: false });
    expect(computeHibernateDirty(a, true, "")).toBe(true);
  });

  it("is true when the timeout changed", () => {
    const a = app({ hibernate_enabled: true, hibernate_after_seconds: 3600 });
    expect(computeHibernateDirty(a, true, "2")).toBe(true);
  });

  it("ignores the timeout field while it's blank", () => {
    const a = app({ hibernate_enabled: true, hibernate_after_seconds: 3600 });
    expect(computeHibernateDirty(a, true, "")).toBe(false);
  });
});

describe("computePollDirty", () => {
  it("is false when the toggle and interval match the app", () => {
    const a = app({ poll_enabled: true, poll_interval_seconds: 120 });
    expect(computePollDirty(a, true, "2")).toBe(false);
  });

  it("is true when the toggle changed", () => {
    const a = app({ poll_enabled: false });
    expect(computePollDirty(a, true, "")).toBe(true);
  });

  it("is true when the interval changed", () => {
    const a = app({ poll_enabled: true, poll_interval_seconds: 120 });
    expect(computePollDirty(a, true, "5")).toBe(true);
  });
});

describe("intervalHelperText", () => {
  it("surfaces the out-of-range message first", () => {
    expect(intervalHelperText("too low", ["platform default: 5 min"])).toBe("too low");
  });

  it("joins the available hints with a middle dot", () => {
    expect(intervalHelperText(false, ["platform default: 5 min", "minimum: 1 min"])).toBe(
      "platform default: 5 min · minimum: 1 min",
    );
  });

  it("drops falsy hints", () => {
    expect(intervalHelperText(false, [false, "minimum: 1 min"])).toBe("minimum: 1 min");
  });

  it("falls back to a generic hint when nothing is known", () => {
    expect(intervalHelperText(false, [false, false])).toBe("leave blank to use the platform default");
  });
});
