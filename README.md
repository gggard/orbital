<img src="ui/src/app/icon.svg" width="72" align="right" alt="streamlit-host logo">

# streamlit-host

Self-hosted Streamlit hosting platform on Kubernetes, inspired by Streamlit
Community Cloud. See [SPEC.md](SPEC.md) for the full specification.

**Deploying on a real cluster?** The platform ships as a Helm chart —
see [docs/INSTALL.md](docs/INSTALL.md) (installation),
[docs/ADMIN.md](docs/ADMIN.md) (operations) and
[docs/USER.md](docs/USER.md) (end-user manual). The rest of this README
covers local development on minikube.

**Current milestone**: core deploy pipeline — create an app from a git URL via
API/dashboard, in-cluster BuildKit image build (Python packages only, no apt
packages), deploy behind ingress at `<slug>.<apps-domain>`, logs, redeploy
webhook, secrets, reboot, delete. Not yet implemented: OIDC auth, hibernation,
analytics (see SPEC §4.6–4.8).

## Local development (minikube)

```bash
make install          # python venv + dependencies
make setup-minikube   # minikube profile 'streamlit-host' + registry + ingress + base image; writes .env
make run              # control plane + dashboard on http://localhost:8000
```

Then start the management console (Next.js + MUI, see
[docs/UI-SPEC.md](docs/UI-SPEC.md)):

```bash
make ui-install
make ui        # console on http://localhost:3000 (make ui-dev for hot reload)
```

Open http://localhost:3000 and deploy an app, e.g.
repo `https://github.com/streamlit/streamlit-example`, branch `master`,
main file `streamlit_app.py`. (A minimal fallback dashboard also exists at
http://localhost:8000.) Node.js ≥ 20 is required for the console; on this dev
host it is installed at `~/.local/node/bin`.

Over VS Code Remote-SSH, forward port **3000** as well — the console proxies
all API calls to the control plane, so no extra configuration is needed.

### Working over VS Code Remote-SSH

App URLs are host-routed through the minikube ingress, which is only reachable
on the remote host. To browse apps from your local machine:

1. In `.env` set the domain to loopback nip.io and pick a tunnel port, then
   restart the control plane (running apps' ingresses converge automatically):

   ```
   SH_APPS_DOMAIN=127.0.0.1.nip.io
   SH_APPS_URL_PORT=8090
   ```

2. On the remote, expose the ingress controller on localhost:

   ```bash
   kubectl --context streamlit-host -n ingress-nginx \
     port-forward svc/ingress-nginx-controller 8090:80
   ```

3. In VS Code's **Ports** panel, forward `8000` (dashboard) and `8090`
   (apps) — keep the local port numbers identical.

Now `http://localhost:8000` opens the dashboard and every app link
(`http://<slug>.127.0.0.1.nip.io:8090`) resolves to your machine's loopback,
goes through the VS Code tunnel, and is routed by hostname on the ingress —
websockets included.

## Authentication (public vs. private apps)

Apps are **public** (anyone with the URL) or **private** — restricted to OIDC
groups. Deploy the demo auth stack (Keycloak + oauth2-proxy) with:

```bash
bash deploy/auth/setup-auth.sh   # then restart the control plane
```

Demo users: `alice/alice123` (group `data-team`), `bob/bob123` (group
`viewers`). Keycloak admin console: `http://keycloak.<domain>:<port>`
(admin/admin).

Make an app private via the dashboard (Private checkbox + groups field) or:

```bash
curl -X PATCH localhost:8000/api/v1/apps/<id> -H 'Content-Type: application/json' \
  -d '{"public": false, "allowed_groups": ["data-team"]}'
```

Access-control changes apply live (no rebuild): the reconciler swaps the
ingress auth annotations. Flow: nginx `auth_request` → control-plane
`/authz/{app_id}` → session check against oauth2-proxy `/oauth2/auth` → group
intersection with `allowed_groups` (empty list = any signed-in user).
Unauthenticated users are redirected to Keycloak; authenticated users outside
the allowed groups get 403.

## Console RBAC (group-based)

The management console itself is behind OIDC login. Roles come from group
claims via `.env` mappings — users in none of the mapped groups cannot sign in:

| Setting | Role | Rights |
|---|---|---|
| `SH_ADMIN_GROUPS` | admin | sees and manages every app |
| `SH_CREATOR_GROUPS` | creator | creates apps; manages apps whose `owner_groups` intersect their groups |
| `SH_VIEWER_GROUPS` | viewer | read-only (overview/logs/builds) on apps whose `owner_groups` intersect their groups |

Every app has `owner_groups` (defaults to its creator's groups): only members
of those groups — plus admins — can see the app at all (others get 404).
Secrets are readable only by managers. Demo users: `carol/carol123` (admin),
`alice/alice123` (creator via data-team), `bob/bob123` (viewer).

**Changing ownership** (console: app → Sharing → Ownership, or
`PATCH /api/v1/apps/<id> {"owner_groups": [...]}`):

- **Admins** can set any owner groups (including none = admins-only).
- **Members of the current owner groups** (creator role) can add or remove
  co-owner groups, but must keep at least one of their *own* groups — no
  accidental self-lockout; transferring an app entirely to another team is an
  admin action.
- Empty owner groups are rejected for non-admins (422).

Apps created before RBAC was enabled have empty `owner_groups` and are visible
to admins only — an admin can share them via the same Ownership panel.

## How it works

- **Control plane** (FastAPI, `src/streamlit_host/`): REST API + dashboard,
  SQLite/PostgreSQL app registry, and a reconciler thread — the only component
  that talks to Kubernetes.
- **Builds**: a Kubernetes Job per build (`k8s/builder.py`) clones the repo
  (alpine/git init container), detects the dependency file in
  Community-Cloud order (`uv.lock` → `requirements.txt` → `pyproject.toml`,
  `packages.txt` rejected with a warning), generates a Dockerfile on a shared
  base image, and builds/pushes with rootless BuildKit to the in-cluster
  registry (minikube `registry` addon: push via cluster DNS, nodes pull via
  `localhost:5000`).
- **Runtime**: per app one Deployment (hardened: non-root, read-only rootfs,
  no SA token) + Service + Ingress (`<slug>.<minikube-ip>.nip.io` locally).
- **Secrets**: TOML via API, mounted as `/app/.streamlit/secrets.toml`;
  updates restart the app without rebuilding.

## API

OpenAPI docs at `/docs`. Highlights:

```
POST   /api/v1/apps                     {slug, repo_url, branch, main_file, ...}
GET    /api/v1/apps
POST   /api/v1/apps/{id}/deploy         trigger rebuild+redeploy
POST   /api/v1/apps/{id}/reboot
GET    /api/v1/apps/{id}/logs?follow=true
GET    /api/v1/apps/{id}/builds/{bid}/logs
PUT    /api/v1/apps/{id}/secrets        {"secrets_toml": "..."}
POST   /webhooks/apps/{id}/{token}      git push webhook (generic)
```
