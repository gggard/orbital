# streamlit-host — Installation Guide

streamlit-host is a self-hosted platform for deploying Streamlit apps from git
repositories onto a Kubernetes cluster ([SPEC.md](../SPEC.md)). This guide
covers a production-style installation with the Helm chart in
[deploy/chart/streamlit-host](../deploy/chart/streamlit-host). For a local
development setup on minikube, see the [README](../README.md) instead.

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Kubernetes ≥ 1.27 | any distribution (EKS/GKE/AKS/k3s/minikube/…) |
| Ingress controller | NGINX Ingress recommended; must support websockets |
| DNS | subdomain routing: wildcard `*.<apps-domain>` → ingress; **path routing** (`apps.routing=path`): a single apps host suffices | 
| Container registry | reachable by build pods (push) and by cluster nodes (pull) |
| OIDC identity provider | Keycloak, Entra ID, Okta, Dex… — required for console RBAC and private apps |
| Helm ≥ 3.12, Docker | on the machine performing the install |
| (optional) TLS | cert-manager with a wildcard certificate for the apps domain |
| (optional) metrics-server | powers the console's per-app CPU/memory Metrics tab (minikube: `addons enable metrics-server`) — without it the tab shows "no metrics" |

**Registry note.** The platform builds one container image per app. Configure:

- `registry.pushUrl` — endpoint build pods push to (in-cluster DNS is fine).
- `registry.pullPrefix` — the image prefix nodes use to pull.

These may differ (e.g. minikube's registry addon: push to
`registry.kube-system.svc.cluster.local:80`, pull via `localhost:5000`). For a
cloud registry both are usually the same host. The chart can also deploy a
**dev-only** in-cluster registry (`registry.internal.enabled=true`).

**Rootless builds.** By default builds run rootless BuildKit. Clusters
without user-namespace support (some LXC/nested environments) need
`builds.rootless=false` (privileged build pods).

## 2. Build and push the platform images

```bash
make images IMAGE_PREFIX=registry.example.com/streamlit-host TAG=0.1.0
make push-images IMAGE_PREFIX=registry.example.com/streamlit-host TAG=0.1.0
```

This produces `control-plane` (FastAPI + reconciler) and `console`
(Next.js UI) images.

## 3. Configure values

Create `my-values.yaml`:

```yaml
image:
  controlPlane:
    repository: registry.example.com/streamlit-host/control-plane
    tag: 0.1.0
  console:
    repository: registry.example.com/streamlit-host/console
    tag: 0.1.0

apps:
  domain: apps.example.com          # *.apps.example.com -> ingress
ingress:
  className: nginx
  consoleHost: streamlit.example.com
  tls:
    enabled: true
    secretName: streamlit-tls
console:
  url: https://streamlit.example.com

registry:
  pushUrl: registry.example.com
  pullPrefix: registry.example.com

database:
  url: postgresql+psycopg://streamlit:***@db.example.com/streamlit  # empty = SQLite PVC

auth:
  console:
    enabled: true
    issuerUrl: https://idp.example.com/realms/main
    clientId: streamlit-host
    clientSecret: "***"
    adminGroups: ["platform-admins"]
    creatorGroups: ["developers"]
    viewerGroups: ["everyone"]
  viewer:                            # private-app viewer auth (oauth2-proxy)
    enabled: true
    oauth2ProxyAuthUrl: http://oauth2-proxy.auth.svc/oauth2/auth
```

### OIDC client requirements

Register a confidential client at your IdP with:

- Redirect URIs: `https://<consoleHost>/api/auth/callback` (console login) and
  your oauth2-proxy callback if you use private apps.
- Post-logout redirect URI: `https://<consoleHost>/` (RP-initiated logout).
- A **groups claim** in the ID token (e.g. Keycloak "Group Membership" mapper,
  claim name `groups`, full path off). RBAC is entirely group-based.
- (optional, Keycloak) to let the console's group pickers list the realm's
  groups (`auth.console.groupsFromKeycloak=true`): enable **service accounts**
  on the client and grant its service account the `query-groups` and
  `view-users` roles of the realm's `realm-management` client. Otherwise
  provide suggestions statically via `auth.console.knownGroups`.

### Private apps (viewer auth)

Deploy [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/) against
the same IdP with `--set-xauthrequest` and a cookie domain covering
`.<apps-domain>`, then set `auth.viewer.*`.
[deploy/auth/auth-stack.yaml.tmpl](../deploy/auth/auth-stack.yaml.tmpl) is a
working demo (Keycloak + oauth2-proxy) to copy from.

## 4. Install

```bash
helm install streamlit-host deploy/chart/streamlit-host \
  -n streamlit-platform --create-namespace \
  -f my-values.yaml
```

The chart creates the `streamlit-apps` and `streamlit-builds` namespaces,
RBAC (the control plane can only touch those two namespaces), the control
plane + console Deployments and the console ingress. A post-install job
builds the app **base images** (one per entry in `baseImages.pythonVersions`)
with BuildKit and pushes them to your registry.

Verify:

```bash
kubectl -n streamlit-platform get pods       # control-plane + console Running
kubectl -n streamlit-builds get jobs          # base image job(s) Complete
```

Open `https://<consoleHost>`, sign in, and deploy a first app
(see [USER.md](USER.md)).

## 5. Upgrades

```bash
helm upgrade streamlit-host deploy/chart/streamlit-host -n streamlit-platform -f my-values.yaml
```

- **Always bump the image tag** when releasing new platform images: with
  `pullPolicy: IfNotPresent` (the default), re-pushing the same tag will NOT
  be picked up by nodes that already cached it.
- Base-image jobs re-run on every upgrade (`baseImages.build=true`); running
  apps keep their current images until their next rebuild.
- With SQLite (default), the control plane is single-replica and upgrades
  cause a short API outage; running apps are unaffected. Use PostgreSQL for
  zero-downtime control-plane restarts.

## 6. Values reference (excerpt)

| Value | Default | Purpose |
|---|---|---|
| `apps.routing` | `subdomain` | `subdomain` (`<slug>.<domain>`, wildcard DNS) or `path` (`<domain>/app/<slug>`, single host — for environments where wildcard DNS is unavailable) |
| `apps.pathPrefix` | `/app` | URL prefix in path mode |
| `apps.domain` | `apps.example.com` | apps domain (wildcard in subdomain mode; single host in path mode) |
| `apps.urlPort` | `80` | port in generated app URLs (tunnel setups) |
| `apps.resources.*` | 250m/1 CPU, 512Mi/2Gi | per-app requests/limits |
| `builds.rootless` | `true` | rootless vs privileged BuildKit |
| `registry.pushUrl` / `pullPrefix` | minikube addon | app image registry |
| `registry.internal.enabled` | `false` | dev-only in-cluster registry |
| `baseImages.pythonVersions` | `["3.12"]` | supported Python versions |
| `database.url` | `""` (SQLite PVC) | PostgreSQL URL for production |
| `auth.console.*` | disabled | console OIDC login + group RBAC |
| `auth.viewer.*` | disabled | private-app viewer auth |
| `controlPlane.reconcileInterval` | `3` | reconcile loop period (s) |

## 7. Uninstall

```bash
helm uninstall streamlit-host -n streamlit-platform
kubectl delete ns streamlit-apps streamlit-builds   # removes all hosted apps!
```
