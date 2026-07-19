<img src="ui/src/app/icon.svg" width="72" align="right" alt="streamlit-host logo">

# streamlit-host

Self-hosted platform for deploying, running, and managing [Streamlit](https://streamlit.io)
apps on Kubernetes — a self-hosted alternative to
[Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud).
Point it at a git repository and the app is live on its own subdomain minutes
later, with secrets management, logs, automatic redeploys on push, and
hibernation of idle apps.

## Capabilities

- **Deploy from git** — give a repo URL, branch and main file; the platform
  clones, resolves dependencies (`uv.lock` / `requirements.txt` /
  `pyproject.toml`), builds an immutable container image, and deploys it
  behind `https://<slug>.<apps-domain>`. Build/deploy status and logs stream
  live to the dashboard.
- **Automatic redeploys** — a per-app webhook (GitHub, GitLab, Gitea, or
  generic) triggers a rebuild on push; unchanged dependencies reuse the
  cached layer for fast rebuilds.
- **Secrets management** — TOML secrets edited in the dashboard, mounted at
  `.streamlit/secrets.toml` so `st.secrets` works exactly as it does locally
  or on Community Cloud. Updates restart the app without a rebuild.
- **Sharing & access control** — apps are public or private. Private apps sit
  behind OIDC login (any provider with a groups claim) with per-app viewer
  allowlists; the console itself has group-based admin/creator/viewer roles
  and per-app ownership.
- **App management** — live log streaming, reboot (clears cached state
  without rebuilding), rollback to a previous build, per-app CPU/memory
  indicators, and delete.
- **Hibernation** — idle apps scale to zero and wake automatically on the
  next request, like Community Cloud's 12-hour sleep.
- **Analytics** — per-app view counts and unique-viewer trends for owners and
  admins.
- **Safe multi-tenancy** — every app is an isolated, hardened Deployment
  (non-root, read-only rootfs, no service-account token); builds run in a
  separate namespace via rootless BuildKit.

See [SPEC.md](SPEC.md) for the full functional specification and architecture.

## Documentation

| Guide | Audience |
|---|---|
| [docs/INSTALL.md](docs/INSTALL.md) | Install the Helm chart on a real cluster |
| [docs/ADMIN.md](docs/ADMIN.md) | Operate the platform (roles, RBAC, upgrades) |
| [docs/USER.md](docs/USER.md) | Deploy and manage your own apps |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Contribute to streamlit-host (local dev on minikube) |
| [SPEC.md](SPEC.md) | Full specification |

## Status

**Current milestone**: core deploy pipeline — create an app from a git URL via
API/dashboard, in-cluster BuildKit image build (Python packages only, no apt
packages), deploy behind ingress, logs, redeploy webhook, secrets, reboot,
delete. Not yet implemented: OIDC auth, hibernation, analytics (see
SPEC §4.6–4.8).
