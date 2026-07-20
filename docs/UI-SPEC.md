# UI Specification: Orbital Management Console

**Status:** v1 · **Stack:** Next.js (App Router, TypeScript) + MUI (Material UI) + SWR
**Replaces:** the minimal single-file dashboard served by FastAPI at `/`.

---

## 1. Goals & principles

- A **management console** for the platform: everything the REST API offers,
  discoverable and safe to use — deploy, observe, configure, share, delete.
- **Live by default**: app states, logs, and build progress refresh
  automatically (SWR polling; no manual reload).
- **Calm Material design**: MUI components, light/dark mode, a single accent
  color (Streamlit red `#e74c3c` family), generous whitespace, no visual noise.
- **Non-blocking**: long operations (build/deploy) are reflected as state
  chips + progress indicators; the UI never freezes on them.
- Destructive actions always require explicit confirmation.

## 2. Information architecture

```
/                     Apps overview (home)
/apps/<id>            App detail
  ├─ tab: Overview    state, URL, repo info, current build, quick actions
  ├─ tab: Metrics     CPU/memory usage charts vs. limits
  ├─ tab: Logs        live runtime logs
  ├─ tab: Builds      build history + per-build logs
  ├─ tab: Secrets     TOML editor
  ├─ tab: Sharing     public/private + allowed groups
  └─ tab: Settings    branch/main file/python, webhook, danger zone
/admin                Reconciler logs (admins only)
```

Top-level layout: slim AppBar (product name, admin shield icon for admins,
theme toggle) + content container (max-width `lg`). No side nav — two levels
only.

## 3. Screens

### 3.1 Apps overview (`/`)

- **Header row**: "Apps" title + card/table view toggle + primary button
  **New app**.
- **App grid** (default view): one MUI `Card` per app:
  - Slug (title) + lock icon when private, app id (caption, monospace).
  - **StateChip** (color-coded: running=green, building/deploying=amber with
    spinner, failed=red, sleeping/deleting=grey).
  - Repo (shortened), branch · main file.
  - Error preview line when failed (truncated, tooltip with full text).
  - Actions: **Open** (external link, disabled unless running), **Redeploy**,
    overflow menu (Reboot, Delete).
  - Card click → app detail.
- **Table view**: alternative to the grid — slug (link), state, owner
  groups, CPU, memory, last updated. For admins, CPU/memory/owner span every
  app and come from `GET /api/v1/admin/overview` (which also feeds a stat
  row above the toggle: app count, running count, total CPU/memory against
  platform limits). Other roles see the same table scoped to their own
  visible apps, with the CPU/memory columns rendering "—" (no bulk metrics
  endpoint outside the admin role) and no stat row.
- Empty state: centered illustration-ish box + "Deploy your first app" CTA.
- Data: `GET /api/v1/apps`, SWR `refreshInterval: 4s`; admins additionally
  poll `GET /api/v1/admin/overview` every 5s.

### 3.2 New app dialog

MUI `Dialog` from the overview:
- Fields: slug*, repo URL*, branch (default `main`), main file (default
  `streamlit_app.py`), Python version (`Select`, from `GET /platform` config —
  v1: static "3.12"), visibility (`public` switch), allowed groups
  (`Autocomplete freeSolo multiple` chips, shown only when private),
  secrets TOML (optional, collapsible, monospace multiline).
- Client-side validation: slug pattern `[a-z0-9-]`, required fields.
- Submit → `POST /api/v1/apps` → close + navigate to the new app's detail.
- API errors shown inline (409 slug taken, 422 validation).

### 3.3 App detail (`/apps/<id>`)

Header: slug + StateChip + private badge · URL as copyable link · action
buttons: **Open**, **Redeploy**, **Reboot**, overflow (Delete).
Below: MUI `Tabs`.

- **Overview**: definition list (repo, branch, main file, python, created,
  updated) · current build card (id, commit sha, phase, started/finished,
  link to logs) · error alert when `*_failed` with the stored message.
- **Metrics**: two single-series area charts (CPU, memory — never dual-axis)
  with current value and % of the platform limit, crosshair tooltips, and a
  table view toggle; polls `GET .../metrics` every 10 s (last ~30 min of
  15 s samples). Info alert when metrics-server is unavailable. Visible to
  all roles, viewers included.
- **Logs**: monospace scrollable pane (`tail=500`), auto-refresh 3 s toggle
  ("Follow"), manual refresh, download button. Auto-scroll to bottom when
  following.
- **Builds**: table (id, commit, phase chip, started, duration); row click
  opens build logs in a collapsible panel below. `GET .../builds`,
  `GET .../builds/<bid>/logs`.
- **Secrets**: monospace `TextField multiline` with the current TOML
  (`GET .../secrets`), Save → `PUT .../secrets` (202 → snackbar "saved —
  app restarting"), client-side hint that saving restarts the app.
- **Sharing**: public/private `Switch` + groups `Autocomplete` (chips) +
  Save. Explains semantics: "empty groups = any signed-in user".
  `PATCH /api/v1/apps/<id>` — applies live, no rebuild (mention in helper
  text).
- **Settings**: form for branch / main file / python version, Save →
  `PATCH` (warns: triggers rebuild) · **Webhook** section: full webhook URL
  with copy button + hint for GitHub/GitLab/Gitea · **Danger zone**:
  outlined red card with Delete (confirm dialog typing the slug).

### 3.4 Reconciler logs (`/admin`)

Admins only (403-style `Alert` for everyone else; the AppBar shield icon is
hidden for non-admins). `LogPane` fed by `GET /api/v1/admin/logs?tail=500`,
polled every 4 s — a simpler sibling of the per-app Logs tab (no
follow-toggle or download, always-on tail). Fleet-wide app status and
resource totals live on the home page's table view (§3.1), not here.

## 4. Components

| Component | Purpose |
|---|---|
| `StateChip` | app/build state → color, label, spinner for transient states |
| `AppCard` | overview grid item |
| `AppsTable` | overview table-view rows (slug, state, owner, CPU, memory, updated) |
| `CreateAppDialog` | new app form |
| `LogPane` | scrollable monospace log viewer w/ follow + download |
| `ConfirmDialog` | generic destructive-action confirmation |
| `CopyField` | read-only value + copy-to-clipboard button |
| `FleetLogsTab` | `/admin` body (reconciler log tail) |
| `useApps / useApp / useBuilds / useLogs / useAdminOverview / useAdminLogs` | SWR hooks in `lib/api.ts` |

## 5. Design system

- MUI default theme, customized: primary `#e74c3c`, shape.borderRadius 10,
  `CssBaseline`; typography: default Roboto stack, `JetBrains Mono, ui-monospace`
  for code/ids/logs.
- **Color scheme**: light + dark via MUI CSS variables
  (`colorSchemes: { light, dark }`), toggle in AppBar, persisted.
- State colors: running `success`, building/deploying `warning`,
  failed `error`, sleeping/deleting `default`, created `info`.
- Feedback: global `Snackbar` (bottom-left) for action results; inline
  `Alert` for form/API errors.

## 6. Data layer & integration

- All calls go to relative `/api/v1/...`; Next.js `rewrites()` proxies to the
  control plane (`CONTROL_PLANE_URL`, default `http://localhost:8000`) — no
  CORS, works in dev and behind the VS Code tunnel.
- SWR global config: `refreshInterval` 4 s on collection/detail, no retry on
  4xx; mutations use optimistic revalidate.
- Errors normalized to `{detail}` (FastAPI convention).

## 7. Out of scope (v1)

Auth for the console itself (the API is currently unauthenticated), analytics
charts, favorites, log websocket streaming (polling suffices), i18n.

## 8. Verification

- `npm run build` passes (type-safe).
- Manual flows against the live control plane on minikube: create app →
  watch build → open app; edit secrets; toggle sharing; delete app.
- Dev server behind VS Code tunnel: forward port 3000.
