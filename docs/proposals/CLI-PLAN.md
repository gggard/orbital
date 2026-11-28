# Proposal: `orbital` command-line interface

Status: **proposal, for review**. Nothing described here is built yet.
The user-facing documentation for the planned CLI is in
[CLI.md](../CLI.md). Review that file as the contract, and this file
as the plan for meeting it.

## 1. Why

Today a CI pipeline or an AI agent drives Orbital with raw `curl` calls
against `/api/v1` (see [API.md](../API.md)). That works, but every caller
ends up rewriting the same glue:

- **Slug to id.** Every endpoint takes the app id (`a1b2c3...`), but
  people and pipelines know the slug (`my-app`).
- **Waiting.** `POST /apps/{id}/deploy` returns `202` right away. To
  fail a pipeline when a build breaks, the caller has to poll
  `GET /apps/{id}` and decide which states count as success or failure.
- **Error handling.** Turning HTTP 401/404/409/422 into a clear message
  and a meaningful process exit code.
- **Secrets.** Uploading a TOML file without quoting it into JSON by
  hand.
- **Creating or updating.** "Create this app if it doesn't exist,
  otherwise update its settings and redeploy" takes several calls and
  branches today.

The CLI packages this glue once, tests it, and gives it a stable
contract (flags, JSON output, exit codes) that scripts and agents can
depend on.

## 2. Goals and non-goals

**Goals**

1. Cover the whole user-facing REST API (apps, deploy, reboot, wake,
   logs, builds, secrets, metrics, analytics, scans, tokens) plus the
   read-only admin endpoints.
2. Work well **unattended**: it never prompts when there is no TTY,
   offers JSON output on every command, documents its exit codes, and
   is configured through environment variables.
3. Provide **blocking deploys** (`--wait`) that exit non-zero when the
   build or rollout fails, with build logs streamed to stderr.
4. Provide a **declarative `apply`** that creates or updates an app from
   an `orbital.toml` committed next to the app's code.
5. Be small to install: a few pure-Python dependencies, none of the
   server's dependencies (no `kubernetes`, `sqlalchemy`, ...).

**Non-goals (for this iteration)**

- Running the control plane or managing the cluster. Helm stays the
  install path.
- A browser OIDC login (device flow) inside the CLI. Phase 1 uses
  personal API tokens, which already exist. See §9.
- A TUI or interactive dashboard.
- Anything the REST API cannot do. The CLI is a client only; it never
  talks to Kubernetes directly.

## 3. Packaging and distribution

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python ≥ 3.12 | Same toolchain, lint, typecheck and CI as the control plane; contributors already know it. |
| Location | `cli/` at the repo root, its own `pyproject.toml`, package `orbital_cli` | A separate distribution keeps the server's heavy dependencies out of CI images. It lives in the same repo so CLI and API change in the same PR. |
| Distribution name | `orbital-cli` on PyPI; console script `orbital` | `uvx orbital-cli` / `pipx install orbital-cli` work without a venv. |
| Container image | `ghcr.io/gggard/orbital/cli:<version>` | For CI systems that run steps in containers (GitLab CI, Tekton, Argo). Built by the existing release workflow next to `control-plane` and `console`. |
| Runtime deps | `httpx` (already used server-side), `typer` | Typer gives subcommands, typed options, `--help` and shell completion with little code. Config and manifest parsing use stdlib `tomllib`. Table output is hand-rolled, so no `rich` dependency. |
| Versioning | Released with the platform, same `vX.Y.Z` tag | One version number. The CLI sends `User-Agent: orbital-cli/<version>`, so the server can log it and later warn about clients that are too old. |
| GitHub Action | `gggard/orbital/cli@vX` (composite action: install, then `orbital deploy --wait`) | Phase 3. Thin wrapper; the CLI does the work. |

Proposed layout:

```text
cli/
  pyproject.toml
  src/orbital_cli/
    __init__.py        # __version__
    main.py            # Typer app, global options, exit-code mapping
    config.py          # env + config file + profiles resolution
    client.py          # httpx wrapper: auth header, base URL, error -> exception
    output.py          # table / json / yaml(-ish) renderers
    resolve.py         # slug-or-id -> app id
    wait.py            # state polling, build-log follow, timeouts
    manifest.py        # orbital.toml parsing + diff against AppOut
    commands/
      auth.py apps.py deploy.py logs.py builds.py secrets.py
      scans.py metrics.py tokens.py admin.py apply.py
  tests/
```

## 4. Command surface

The full reference is in [CLI.md](../CLI.md#command-reference). Summary:

| Group | Commands | Endpoint(s) |
|---|---|---|
| auth | `login`, `logout`, `whoami` | `GET /me` (token validation) |
| apps | `list`, `get`, `create`, `update`, `delete`, `open` | `/apps`, `/apps/{id}` |
| lifecycle | `deploy`, `reboot`, `wake`, `wait`, `status` | `/apps/{id}/deploy`, `/reboot`, `/wake`, polling `GET /apps/{id}` |
| logs | `logs [-f] [--tail N]` | `/apps/{id}/logs` |
| builds | `builds list`, `builds logs [BUILD]` | `/apps/{id}/builds`, `/builds/{b}/logs` |
| secrets | `secrets get`, `secrets set (-f FILE \| -)` | `/apps/{id}/secrets` |
| observability | `metrics`, `analytics` | `/apps/{id}/metrics`, `/analytics` |
| security | `scans list`, `scans show`, `scans run [--wait]` | `/apps/{id}/scans`, `/scan` |
| tokens | `tokens list`, `tokens create`, `tokens revoke` | `/me/tokens` |
| declarative | `apply -f orbital.toml [--wait] [--dry-run]` | composite |
| admin | `admin overview`, `admin activity`, `admin logs`, `admin scans` | `/admin/*` |
| misc | `version`, `completion <shell>`, `health` | `/healthz` |

Design rules:

- **`APP` is a slug or an id.** Resolution: if the value matches an id
  exactly, use it; otherwise look it up by slug. Phase 1 resolves the
  slug client-side with `GET /apps`. §6 proposes a server filter so this
  stays cheap on large fleets.
- **Verbs at the top level** for frequent actions (`orbital deploy my-app`),
  nouns for CRUD (`orbital apps create`).
- **One flag per API field**, named after the field with dashes
  (`--hibernate-after-seconds`). List fields repeat (`--tag a --tag b`).
- **Destructive commands** (`apps delete`, `tokens revoke`) prompt for
  confirmation only on a TTY. Otherwise they need `--yes` and fail with
  exit code 2 without it.

## 5. Cross-cutting behaviour

### 5.1 Configuration resolution

Highest precedence first:

1. Command-line flags: `--url`, `--token`, `--profile`
2. Environment variables: `ORBITAL_URL`, `ORBITAL_TOKEN`, `ORBITAL_PROFILE`,
   `ORBITAL_OUTPUT`
3. Config file `$XDG_CONFIG_HOME/orbital/config.toml` (default
   `~/.config/orbital/config.toml`), with named profiles

Tokens written by `orbital login` go to the config file with mode
`0600`. The CLI warns if the file is readable by others. `--token`
works but is discouraged in the docs, because the value ends up in
shell history and process listings. `--token-stdin` is offered instead.

### 5.2 Output

- `-o/--output table|json|yaml|name`. The default is `table`, unless
  `ORBITAL_OUTPUT` says otherwise.
- `json` output is the **API response unchanged** (`AppOut`, `BuildOut`,
  ...). The CLI does not reshape it, so the JSON schema is the
  OpenAPI schema and `jq` recipes from API.md keep working.
- `name` prints one identifier per line (slug for apps, id for builds,
  tokens, scans), for `xargs` pipelines.
- Data goes to stdout; progress, build logs streamed during `--wait`,
  and errors go to stderr. With `-o json`, stdout carries exactly one
  JSON document.
- Colour only on a TTY; honours `NO_COLOR`.

### 5.3 Exit codes (stable contract)

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unexpected error (network failure, 5xx, bug) |
| 2 | Usage error (bad flags, missing `--yes`, invalid manifest) |
| 3 | Authentication or authorization failure (401/403) |
| 4 | Not found (404, unknown slug) |
| 5 | Conflict (409: build already running, slug taken, wrong state) |
| 6 | Validation rejected by the server (422) |
| 7 | `--wait` timed out |
| 8 | The awaited operation failed (`build_failed`, `deploy_failed`, scan failed) |

With `-o json`, errors are also written to stderr as one JSON object:
`{"error": {"code": 5, "http_status": 409, "message": "a build is already in progress"}}`.
An agent can then branch on structured data instead of parsing text.

### 5.4 Waiting (`--wait`)

`deploy --wait`, `apply --wait`, `wake --wait`, `reboot --wait`,
`scans run --wait` and `orbital wait` share one implementation:

1. Record the latest build id **before** triggering the action, so that
   "the new build" can be identified afterwards. Without this, a fast
   poll could see the *previous* `running` state and report success
   too early. §6 removes this workaround.
2. Poll `GET /apps/{id}` with backoff (1 s, growing to 5 s).
3. Success when the app state is `running` and `current_build_id` is the
   new build (`deploy`/`apply`). For `wake`: state `running`. For
   `reboot`: back to `running` after leaving it, or after the
   restart-count increase seen in `GET /metrics`.
4. Failure (exit 8) on `build_failed` / `deploy_failed`. The app's
   `error` field and the last 50 lines of build logs are printed to stderr.
5. `--timeout` (default 15 min) gives exit 7. The deploy keeps running
   server-side, and the message says so.
6. `--follow` streams build logs, then runtime logs, while waiting.
   Phase 1 does this by polling the build-logs endpoint (the server
   offers no build-log streaming today).

### 5.5 Non-interactive detection

The CLI treats the session as non-interactive when stdin is not a TTY,
`CI` is set, or `--no-input` is passed. In that mode it never prompts,
never opens a browser (`apps open` prints the URL instead), and
disables colour and spinners.

### 5.6 `apply` and `orbital.toml`

A manifest committed to the app's repo:

```toml
slug = "sales-dashboard"
repo_url = "https://github.com/acme/sales-dashboard"
branch = "main"
app_type = "streamlit"
main_file = "app.py"
python_version = "3.13"
public = false
allowed_groups = ["sales"]
tags = ["team:sales"]

[hibernate]
enabled = true
after_seconds = 3600
```

`orbital apply -f orbital.toml`:

1. Validate the manifest locally against the same field rules as
   `AppCreate` (types; streamlit-only vs static-only fields).
2. Look up the slug. If it is missing: `POST /apps`.
3. If it exists: compute the diff against `AppOut` and `PATCH` only the
   changed fields. `repo_url`, `slug` and `app_type` cannot be changed
   in `PATCH`; a change to them is an error (exit 2) with a hint.
4. `--redeploy` (default on for CI use, `--no-redeploy` to skip)
   triggers `POST /deploy` when nothing in the PATCH already caused a
   rebuild.
5. `--dry-run` prints the planned create/patch/deploy and exits 0
   without changing anything. `-o json` prints the plan as JSON
   (`{"action": "update", "changes": {...}}`) for review bots.

Secrets are **never** read from `orbital.toml`, because the manifest is
committed. They are pushed separately with
`orbital secrets set APP -f -` from a CI secret.

## 6. Server-side changes this plan relies on

None of these block Phase 1, which has client-side workarounds. They
make the CLI simpler and more reliable, and each would be a small,
separate PR:

| # | Change | Why | Workaround until then |
|---|---|---|---|
| S1 | `GET /apps?slug=<slug>` filter (or `GET /apps/by-slug/{slug}`) | Resolve a slug without listing every visible app | List all apps and filter client-side |
| S2 | `POST /apps/{id}/deploy` returns the id of the build it scheduled (reconciler creates the `Build` row eagerly, or returns a correlation id) | Reliable `--wait`: wait for *this* build | Snapshot the latest build id before deploying (§5.4) |
| S3 | `POST /apps/{id}/deploy` accepts an optional `{"commit": "<sha>"}` (already listed in SPEC §7) | Deploy exactly the commit CI tested, not the branch head at reconcile time | Not available: the CLI documents that it deploys the branch head |
| S4 | Streaming build logs (`?follow=true` on build logs, like runtime logs) | `--follow` without polling | Poll every 2 s and print only the new lines |
| S5 | Log `User-Agent` in activity events | Audit which actions came from CI or agents | None needed |
| S6 | Token scopes (e.g. `deploy:my-app` only) | Least privilege for CI tokens: today a token has all of its owner's rights | Document: create a dedicated token with the shortest TTL that works |

## 7. Testing strategy

- **Unit tests**: `httpx.MockTransport` for the client, covering error
  mapping to exit codes, output renderers, config precedence, slug
  resolution, wait state machine (including the "stale running state"
  race), and manifest diffing.
- **Contract tests against the real API in-process**: mount the FastAPI
  app from `orbital.main` via `httpx.ASGITransport` (reusing
  `tests/conftest.py` fixtures, auth disabled) and run CLI commands
  through Typer's `CliRunner`. This catches drift between CLI and API
  in the same PR that causes it, with no cluster needed.
- **Snapshot test of `orbital --help` trees**, so command or flag
  renames are deliberate and show up in review.
- **CI**: new `test-cli` job in `.github/workflows/ci.yml` (ruff, mypy,
  pytest for `cli/`), plus coverage reporting to SonarCloud like the
  other jobs.
- **Smoke test on minikube** (manual, documented in DEVELOPMENT.md):
  `orbital apply` and `deploy --wait` against the example repo.

## 8. Delivery phases

Each phase is one or more PRs, shippable on its own.

**Phase 1: CI deploy MVP**
- Package skeleton, config/profiles, client, output, exit codes
- `login`/`logout`/`whoami`, `version`, `health`
- `apps list|get`, `status`, `deploy [--wait] [--follow] [--timeout]`,
  `reboot`, `wake`, `wait`
- `logs [-f]`, `builds list|logs`
- Unit and contract tests, CI job, docs page published

**Phase 2: full app management**
- `apps create|update|delete`, `secrets get|set`
- `apply` with `orbital.toml` (+ `--dry-run`)
- Server: S1, S2

**Phase 3: ecosystem**
- `metrics`, `analytics`, `scans`, `tokens`, `admin *`
- `completion`, container image, PyPI publishing in `release.yml`
- GitHub Action wrapper, GitLab CI example
- Server: S3, S4, S5

**Later / separate proposals**: OIDC device-flow login (§9), token
scopes (S6), `orbital rollback` once `POST /apps/{id}/rollback` exists.

## 9. Open questions for reviewers

1. **Separate distribution vs. extra of the server package.** This plan
   proposes `orbital-cli` as a separate distribution in `cli/`. The
   alternative, `pip install orbital[cli]`, would pull every server
   dependency into CI images. Agreed?
2. **Typer vs. stdlib `argparse`.** Typer adds one dependency (plus
   Click), and in return gives completions and a cleaner codebase. Is
   that acceptable?
3. **Default output.** Should the CLI switch to `json` automatically
   when stdout is not a TTY? The proposal says *no*, because silently
   changing output by context surprises people; `ORBITAL_OUTPUT=json`
   is the explicit opt-in.
4. **Login.** Phase 1 asks the user to paste a personal API token. Is an
   OIDC device-authorization flow (`orbital login --browser`) wanted,
   given that not every OIDC provider supports the device grant?
5. **`apply --redeploy` default.** On (a push to main means "ship it")
   or off (apply only changes settings)? The proposal says on, since
   the main use case is CI on push.
6. **Manifest name and format.** `orbital.toml` (stdlib parser,
   consistent with `secrets.toml` and `pyproject.toml`) vs.
   `orbital.yaml`.
