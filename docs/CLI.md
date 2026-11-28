# Orbital — Command-Line Interface

!!! info "New in the next Orbital release"
    The CLI ships with the next release (PyPI package, container image
    and GitHub Action). Until then, install it from a checkout of this
    repository: `uv tool install ./cli` or `pipx install ./cli`. The
    design is in [proposals/CLI-PLAN.md](proposals/CLI-PLAN.md).

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
  ghcr.io/gggard/orbital/cli:<version> orbital apps list
```

The package is `orbital-cli`; the command it installs is `orbital`.
The image has no entrypoint, so CI systems can run shell scripts in it.
Use a CLI version that matches your platform version. `orbital version`
prints both.

## Authenticate

The CLI authenticates with a **personal API token**. Create one in the
console under **My tokens**, or see [API.md](API.md#authentication).

**Interactive use.** Store the token in your config file:

```bash
orbital login --url https://orbital.example.com
# API token (orbpat_...): ********
# Logged in as alice@example.com (creator) on https://orbital.example.com

orbital whoami
```

`login` checks the token against the platform before saving it. To
script it, pipe the token instead of typing it:
`printf '%s' "$TOKEN" | orbital login --url https://orbital.example.com --token-stdin`.

The token is saved in `~/.config/orbital/config.toml` (mode `0600`;
`$XDG_CONFIG_HOME` is honoured, and `ORBITAL_CONFIG` overrides the path).
The CLI warns if the file is readable by other users.
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

A dedicated action wraps the same command. It installs the CLI version
that matches the action's ref, so no PyPI access is needed:

```yaml
      - uses: gggard/orbital/cli@v1.2.3   # pin to your platform's release
        id: orbital
        with:
          url: https://orbital.example.com
          token: ${{ secrets.ORBITAL_TOKEN }}
          command: apply -f orbital.toml --wait --follow
      - run: echo "Live at ${{ fromJSON(steps.orbital.outputs.result).url }}"
```

Inputs: `command` (required; the arguments after `orbital`), `url`
(required), `token`, and `output` (default `json`). Output: `result`,
the command's stdout.

### GitLab CI

```yaml
deploy:
  stage: deploy
  image: ghcr.io/gggard/orbital/cli:1.2.3   # pin to your platform's release
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

- Output is JSON whenever stdout isn't a terminal (or with `-o json`):
  the **unchanged API response** (the same schema as `/openapi.json`)
  as a single JSON document on stdout.
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
| `--token-stdin` | Read the API token from stdin (not combinable with `-f -`) |
| `--token TOKEN` | API token. Discouraged: it shows up in shell history and process listings |
| `-o, --output table\|json\|name` | Output format (default: `table` on a terminal, `json` otherwise) |
| `--no-input` | Never prompt; fail instead |
| `-q, --quiet` | Print only errors (and the requested data) |
| `-v, --verbose` | Log HTTP requests to stderr (tokens redacted) |
| `--version` | Print the CLI version and exit |

### Auth

| Command | Description |
|---|---|
| `orbital login [--token-stdin]` | Validate a token and store it in the config file (use the global `--url`/`--profile` to choose where) |
| `orbital logout` | Remove the stored token (does not revoke it) |
| `orbital whoami` | Show the current identity, groups and role |

### Apps

| Command | Description |
|---|---|
| `orbital apps list [--tag T] [--state S]` | List apps you can see |
| `orbital apps get APP` | Show one app (alias: `orbital status APP`) |
| `orbital apps create SLUG --repo URL [options] [--wait] [--follow]` | Create an app and start its first build |
| `orbital apps update APP [options] [--wait] [--follow]` | Change settings. Fields that need a rebuild (branch, main file, Python version, build command, output dir) trigger one, and `--wait` waits for it |
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
| `orbital builds logs APP [BUILD] [-f]` | Build log. Without `BUILD`, the latest build. `-f` keeps printing until the build ends (exit 8 if it fails) |

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
| `orbital scans run APP [--wait] [--fail-on critical\|high\|medium\|low]` | Request a scan; `--fail-on` implies `--wait` and exits 8 if findings at or above that severity exist |

`scans run --fail-on high` works as a security gate in CI.

### Tokens

| Command | Description |
|---|---|
| `orbital tokens list` | Your tokens (never shows secret values) |
| `orbital tokens create NAME [--ttl-days N]` | Create a token and print it **once**. In table mode only the secret goes to stdout, so `T=$(orbital -o table tokens create ci)` works |
| `orbital tokens revoke ID [--yes]` | Revoke a token, effective immediately |

### Admin (admin role only)

| Command | Description |
|---|---|
| `orbital admin overview` | Fleet summary |
| `orbital admin activity [--limit N]` | Platform activity feed |
| `orbital admin logs [--tail N]` | Control-plane logs |
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
- `json`: the API response, unchanged. Stable, follows the API schema.
- `name`: one identifier per line, for `xargs`.

When you don't pick a format (with `-o`, `ORBITAL_OUTPUT`, or the
profile's `output` key), the CLI prints `table` on a terminal and `json`
when stdout is piped or redirected. In CI and from agents you get JSON
without asking. Pass `-o table` to force the table.

Commands that return text rather than objects (`logs`, `builds logs`,
`secrets get`, `admin logs`) print it raw in every format.

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
- `--follow` polls the build log every few seconds (the API can't
  stream build logs yet), so lines arrive in small batches.
- `APP` is resolved by listing the apps you can see, which costs one
  extra request per command.
