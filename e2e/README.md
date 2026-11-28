# End-to-end tests

Two tiers. Both drive the **installed `orbital` executable as a subprocess**,
the way a CI job or an agent does: real argument parsing, environment
variables, config file, stdout/stderr split and exit codes.

| Tier | File | Platform | Runs |
|---|---|---|---|
| Local | `test_cli_local.py` | A real control plane (uvicorn, SQLite, real HTTP). Kubernetes is replaced by a simulated reconciler that writes the same state transitions to the database (`conftest.py`) | Every PR (`test-cli` job in `ci.yml`), ~35 s |
| Cluster | `test_cli_cluster.py` | A real Orbital install: reconciler, in-cluster BuildKit builds from GitHub, ingress | `e2e.yml`: pushes to `main`, nightly, on demand, and PRs labelled `e2e`. ~20–30 min |

## Local tier

```bash
make cli-install
make e2e-local
```

What it covers: a CI pipeline from the first `apply --wait` to `delete --wait`
(re-apply redeploys, settings patch, secrets from stdin, reboot), a failing
build exiting 8, a `--wait` timeout exiting 7, a deploy conflict exiting 5
followed by `wait`, waking a hibernating app, and the agent conventions
(JSON errors, `--yes` in CI, validation exit codes, global options after
the subcommand, `login`).

The simulated reconciler fails builds of the branch named `broken`, and
ignores apps whose slug starts with `frozen` (for timeout and conflict
scenarios).

## Cluster tier

CI installs the chart on minikube with `e2e/minikube-values.yaml` (see
`.github/workflows/e2e.yml`). To run the suite against any platform you can
reach:

```bash
export ORBITAL_E2E_URL=https://orbital.example.com   # control plane
export ORBITAL_E2E_TOKEN=orbpat_...                  # if auth is enabled
# optional: reach apps through the ingress by Host header (no DNS needed)
export ORBITAL_E2E_INGRESS=http://192.168.49.2
make e2e-cluster
```

It deploys a public Streamlit example and Orbital's own `docs/` as a static
site, under unique `e2e-<random>` slugs that are deleted afterwards. The
repositories, branches, timeouts and an optional vulnerability scan are
configurable: see the docstring of `test_cli_cluster.py`. On minikube, the
first build of each Python version also waits for the chart's base-image
jobs.
