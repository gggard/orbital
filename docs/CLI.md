# Orbital — Command-Line Interface

!!! warning "Planned feature, not available yet"
    This page documents the **planned** `orbital` CLI so it can be
    reviewed before it is built. The implementation plan is in
    [proposals/CLI-PLAN.md](proposals/CLI-PLAN.md). Until the CLI ships,
    use the [REST API](API.md).

Audience: anyone who wants to deploy and manage Orbital apps from a
terminal, a CI pipeline, or an AI agent. The CLI is a thin client over
the [REST API](API.md): it can do anything the API can, and nothing it
can't. Your permissions are the same as in the console.

## Install

```bash
# one-off, no install (needs uv)
uvx orbital-cli --help

# persistent install
pipx install orbital-cli        # or: uv tool install orbital-cli

# container image, for CI runners that execute steps in containers
docker run --rm -e ORBITAL_URL -e ORBITAL_TOKEN \
  ghcr.io/gggard/orbital/cli:0.2.0 apps list
```

The package is `orbital-cli`; the command it installs is `orbital`.
Use a CLI version that matches your platform version. `orbital version`
prints both.

## Authenticate

The CLI authenticates with a **personal API token**. Create one in the
console under **My tokens**, or see [API.md](API.md#authentication).

**Interactive use.** Store the token in your config file:

```bash
orbital login --url https://orbital.example.com
# Paste your API token (orbpat_...): ********
# Logged in as alice@example.com (creator) on https://orbital.example.com

orbital whoami
```

The token is saved in `~/.config/orbital/config.toml` (mode `0600`).
`orbital logout` removes it from that file. It does **not** revoke the
token server-side; use `orbital tokens revoke` for that.

**CI and agents.** Use environment variables and nothing else:

```bash
export ORBITAL_URL=https://orbital.example.com
export ORBITAL_TOKEN=orbpat_...       # from your CI secret store
orbital whoami
```

If the platform runs with auth disabled (local development), only
`ORBITAL_URL` is needed (default `http://localhost:8000`).

### Several platforms: profiles

```bash
orbital login --profile staging --url https://orbital.staging.example.com
orbital --profile staging apps list
ORBITAL_PROFILE=staging orbital apps list
```

```toml
# ~/.config/orbital/config.toml
default_profile = "prod"

[profiles.prod]
url = "https://orbital.example.com"
token = "orbpat_..."

[profiles.staging]
url = "https://orbital.staging.example.com"
token = "orbpat_..."
```

### Configuration precedence

Highest first:

| Setting | Flag | Environment variable | Config file key |
|---|---|---|---|
| Control-plane URL | `--url` | `ORBITAL_URL` | `profiles.<p>.url` |
| API token | `--token-stdin` (or `--token`, which is discouraged) | `ORBITAL_TOKEN` | `profiles.<p>.token` |
| Profile | `--profile` | `ORBITAL_PROFILE` | `default_profile` |
| Output format | `-o, --output` | `ORBITAL_OUTPUT` | `profiles.<p>.output` |

## Quick start

```bash
# create a Streamlit app from a repo
orbital apps create my-app \
  --repo https://github.com/streamlit/streamlit-example \
  --branch master --main-file streamlit_app.py --wait

# see it
orbital apps list
orbital status my-app

# push code, then redeploy and block until it is live (or failed)
orbital deploy my-app --wait --follow

# runtime logs
orbital logs my-app -f
```

Anywhere a command takes `APP`, you can pass the app's **slug**
(`my-app`) or its **id**.

## Using the CLI in CI

The typical pipeline step: redeploy on push to `main`, fail the job if
the build or rollout fails, and show the build log in the job output.

### GitHub Actions

```yaml
name: Deploy to Orbital
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - name: Deploy
        env:
          ORBITAL_URL: https://orbital.example.com
          ORBITAL_TOKEN: ${{ secrets.ORBITAL_TOKEN }}
        run: uvx orbital-cli apply -f orbital.toml --wait --follow --timeout 20m
```

A dedicated action wraps the same command:

```yaml
      - uses: gggard/orbital/cli@v0
        with:
          url: https://orbital.example.com
          token: ${{ secrets.ORBITAL_TOKEN }}
          command: apply -f orbital.toml --wait
```

### GitLab CI

```yaml
deploy:
  stage: deploy
  image: ghcr.io/gggard/orbital/cli:0.2.0
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
  script:
    - orbital apply -f orbital.toml --wait --follow
  # ORBITAL_URL and ORBITAL_TOKEN set as masked CI/CD variables
```

### Pushing secrets from CI

Secrets never go in `orbital.toml`. Pipe them from your CI secret store
to `secrets set`. Changing secrets restarts the app without a rebuild.

```bash
printf '%s' "$APP_SECRETS_TOML" | orbital secrets set my-app -f -
```

### CI token hygiene

- Create a **dedicated token** for each pipeline (`orbital tokens create ci-sales --ttl-days 30`)
  so you can revoke one pipeline without affecting others.
- A token has every right its owner has. Create CI tokens from an
  account with the `creator` role that owns only the apps the pipeline
  deploys.
- Don't pass `--token` on the command line, because it shows up in logs
  and process listings. Use `ORBITAL_TOKEN` or `--token-stdin`.

## Using the CLI from an AI agent

The CLI is designed so an agent can drive it without scraping text:

- `-o json` on any command prints the **unchanged API response** (the
  same schema as `/openapi.json`) as a single JSON document on stdout.
- Errors with `-o json` are a single JSON object on stderr:

  ```json
  {"error": {"code": 5, "http_status": 409, "message": "a build is already in progress"}}
  ```

- [Exit codes](#exit-codes) are stable and specific, so "conflict",
  "not found" and "the build failed" can be told apart without reading
  messages.
- The CLI never prompts when stdin is not a terminal, when `CI` is set,
  or with `--no-input`. Commands that would ask for confirmation fail
  with exit code 2 unless `--yes` is given.
- `apply --dry-run -o json` describes what *would* change, so an agent
  can propose a change and get it reviewed before applying it.

Example agent loop:

```bash
export ORBITAL_OUTPUT=json
orbital status my-app | jq -r .state             # -> running
orbital deploy my-app --wait --timeout 10m
case $? in
  0) echo "live" ;;
  8) orbital builds logs my-app --tail 100 ;;    # build/rollout failed: inspect
  5) orbital wait my-app ;;                      # a build was already running
esac
```

## Declarative apps: `orbital.toml`

Commit an `orbital.toml` next to your app's code and run `orbital apply`.
The command creates the app if its slug doesn't exist yet. Otherwise it
updates only the settings that changed, then redeploys.

```toml
slug = "sales-dashboard"
repo_url = "https://github.com/acme/sales-dashboard"
branch = "main"
app_type = "streamlit"          # or "static"

# streamlit only
main_file = "app.py"
python_version = "3.13"

# static only
# build_command = "npm run build"
# output_dir = "dist"

public = false
allowed_groups = ["sales"]
owner_groups = ["sales-admins"]
tags = ["team:sales"]

[hibernate]
enabled = true
after_seconds = 3600

[poll]
enabled = false
# interval_seconds = 300
```

The fields match the API's `AppCreate` body; see
[API.md](API.md#deploying-an-app) for the rules. `slug`, `repo_url` and
`app_type` cannot change after creation. `apply` stops with an error if
they differ from the live app.

```bash
orbital apply -f orbital.toml --dry-run          # show the plan, change nothing
orbital apply -f orbital.toml --wait             # create/update + redeploy, block
orbital apply -f orbital.toml --no-redeploy      # settings only
```

Dry-run output:

```text
app sales-dashboard: update
  public           true -> false
  allowed_groups   [] -> ["sales"]
  then: redeploy (branch main)
```

## Command reference

Global options, accepted by every command:

| Option | Description |
|---|---|
| `--url URL` | Control-plane base URL |
| `--profile NAME` | Config profile to use |
| `--token-stdin` | Read the API token from stdin |
| `-o, --output table\|json\|yaml\|name` | Output format (default `table`) |
| `--no-input` | Never prompt; fail instead |
| `-q, --quiet` | Print only errors (and the requested data) |
| `-v, --verbose` | Log HTTP requests to stderr (tokens redacted) |
| `--no-color` | Disable colour (also honours `NO_COLOR`) |

### Auth

| Command | Description |
|---|---|
| `orbital login [--url URL] [--profile P]` | Validate a token and store it in the config file |
| `orbital logout [--profile P]` | Remove the stored token (does not revoke it) |
| `orbital whoami` | Show the current identity, groups and role |

### Apps

| Command | Description |
|---|---|
| `orbital apps list [--tag T] [--state S]` | List apps you can see |
| `orbital apps get APP` | Show one app (alias: `orbital status APP`) |
| `orbital apps create SLUG --repo URL [options] [--wait]` | Create an app and start its first build |
| `orbital apps update APP [options]` | Change settings. Fields that need a rebuild (branch, main file, ...) trigger one |
| `orbital apps delete APP [--yes] [--wait]` | Delete the app and all its resources |
| `orbital apps open APP` | Open the app's URL in a browser (prints it when non-interactive) |

`create`/`update` options mirror the API fields: `--branch`,
`--type streamlit|static`, `--main-file`, `--python-version`,
`--build-command`, `--output-dir`, `--public/--private`,
`--allowed-group G` (repeatable), `--owner-group G` (repeatable),
`--tag T` (repeatable), `--hibernate/--no-hibernate`,
`--hibernate-after-seconds N`, `--poll/--no-poll`,
`--poll-interval-seconds N`, `--secrets-file FILE` (create only).

### Lifecycle

| Command | Description |
|---|---|
| `orbital deploy APP [--wait] [--follow] [--timeout DUR]` | Rebuild from the branch head and redeploy |
| `orbital reboot APP [--wait]` | Restart without rebuilding (clears `st.cache_*`) |
| `orbital wake APP [--wait]` | Wake a hibernating app |
| `orbital wait APP [--for running\|deleted] [--timeout DUR]` | Block until the app settles into the given state |
| `orbital status APP` | Current state, error, URL, current build |

`--wait` blocks until the operation succeeds (exit 0), fails (exit 8,
with the app's error and the tail of the build log printed to stderr),
or times out (exit 7; the operation keeps running server-side).
`--follow` streams build logs while waiting. The default `--timeout` is
`15m`; durations accept `90s`, `10m`, `1h`.

### Logs and builds

| Command | Description |
|---|---|
| `orbital logs APP [-f] [--tail N]` | Runtime logs (default last 500 lines); `-f` streams |
| `orbital builds list APP` | Build history (id, phase, commit, timestamps) |
| `orbital builds logs APP [BUILD] [-f]` | Build log. Without `BUILD`, the latest build |

### Secrets

| Command | Description |
|---|---|
| `orbital secrets get APP` | Print the app's secrets TOML to stdout (owners/admins) |
| `orbital secrets set APP -f FILE` | Replace the secrets TOML (`-f -` reads stdin). Validated before upload; restarts the app |

### Observability and security

| Command | Description |
|---|---|
| `orbital metrics APP` | Current CPU/memory vs. limits, restart count |
| `orbital analytics APP` | Views and unique viewers |
| `orbital scans list APP` | Vulnerability scan history |
| `orbital scans show APP [SCAN] [--severity S]` | Vulnerabilities in a scan (default: latest) |
| `orbital scans run APP [--wait] [--fail-on critical\|high\|medium\|low]` | Request a scan; `--fail-on` exits 8 if findings at or above that severity exist |

`scans run --wait --fail-on high` works as a security gate in CI.

### Tokens

| Command | Description |
|---|---|
| `orbital tokens list` | Your tokens (never shows secret values) |
| `orbital tokens create NAME [--ttl-days N]` | Create a token and print it **once** |
| `orbital tokens revoke ID [--yes]` | Revoke a token, effective immediately |

### Admin (admin role only)

| Command | Description |
|---|---|
| `orbital admin overview` | Fleet summary |
| `orbital admin activity [--limit N]` | Platform activity feed |
| `orbital admin logs` | Control-plane logs |
| `orbital admin scans` | Latest scan of every app |

### Misc

| Command | Description |
|---|---|
| `orbital version` | CLI version and, if reachable, the platform version |
| `orbital health` | Check `GET /healthz` (exit 0 if healthy) |
| `orbital completion bash\|zsh\|fish` | Print a shell-completion script |

## Output formats

```bash
$ orbital apps list
SLUG             TYPE       STATE      URL                                   UPDATED
my-app           streamlit  running    https://my-app.apps.example.com       2m ago
docs-site        static     sleeping   https://docs-site.apps.example.com    3d ago

$ orbital apps list -o name
my-app
docs-site

$ orbital apps get my-app -o json | jq .state
"running"
```

- `table`: for people. Columns may change between releases; don't parse it.
- `json` / `yaml`: the API response, unchanged. Stable, follows the API schema.
- `name`: one identifier per line, for `xargs`.

Data goes to stdout; progress messages and streamed logs go to stderr.
So `orbital deploy my-app --wait --follow -o json > result.json`
captures only the final app state.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unexpected error (network, server 5xx) |
| 2 | Usage error (bad flags, invalid manifest, missing `--yes`) |
| 3 | Not authenticated / not allowed (401, 403) |
| 4 | Not found (unknown app, build, token) |
| 5 | Conflict (a build is already running, slug taken, wrong state) |
| 6 | Rejected by server validation (422) |
| 7 | `--wait` timed out |
| 8 | The awaited operation failed (build, rollout or scan gate) |

## Limitations

- `deploy` always builds the **head of the tracked branch** when the
  build starts, not a specific commit. If more commits land in between,
  the newer head is deployed.
- `orbital login` takes a pasted token; there is no browser login from
  the CLI.
- Tokens carry all of their owner's rights; there are no per-app or
  read-only scopes yet.
- No `rollback` command yet; the API doesn't expose rollback.
