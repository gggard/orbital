# Orbital — Administrator Manual

Audience: platform operators (members of `auth.console.adminGroups`).

## 1. Architecture at a glance

```
console (Next.js) ──proxy──> control plane (FastAPI + reconciler) ──> Kubernetes
                                     │                                  ├── streamlit-apps:   per app Deployment/Service/Ingress/Secret
                                     └── registry (app images)          └── streamlit-builds: BuildKit build Jobs
```

- The **reconciler** inside the control plane is the only component that
  writes to Kubernetes. It drives each app through
  `created → building → deploying → running` (§6 of [SPEC.md](../SPEC.md)).
- Each deploy builds an **immutable image** per app from a shared base image;
  app pods are hardened (non-root, read-only rootfs, no service-account
  token, dropped capabilities).

## 2. Roles and access control

RBAC is group-based, resolved from the OIDC `groups` claim at login:

| Role | Granted by | Rights |
|---|---|---|
| **admin** | `auth.console.adminGroups` | sees and manages every app; may set any `owner_groups` |
| **creator** | `auth.console.creatorGroups` | creates apps; manages apps whose `owner_groups` intersect their groups |
| **viewer** | `auth.console.viewerGroups` | read-only (overview, logs, builds) on apps shared with their groups |

Users in none of these groups cannot use the console at all. Changes to a
user's groups take effect at their next login.

**Ownership.** Every app has `owner_groups` (default: creator's groups).
Non-owners don't see the app (API returns 404). Owners can add/remove
co-owner groups but must keep one of their own; **full transfers and
admin-only apps are admin actions** (console: app → Sharing → Ownership).

**App viewer access** is separate from console access: public apps are open
to the internet; private apps require OIDC login through oauth2-proxy and a
match against the app's `allowed_groups`.

**Group directory (picker suggestions).** The group pickers in the console
(viewer access, ownership, new-app dialog) suggest a directory of known
groups. It always contains the role-config groups above; extend it with:

- `auth.console.knownGroups` (`ORBITAL_KNOWN_GROUPS`) — a static list, works with
  any IdP;
- `auth.console.groupsFromKeycloak` (`ORBITAL_GROUPS_FROM_KEYCLOAK`) — list the
  Keycloak realm's groups live (cached 60 s, subgroups flattened). The OIDC
  client must have **service accounts enabled** and its service account
  granted the `query-groups` and `view-users` roles of the realm's
  `realm-management` client. If the lookup fails, the console silently falls
  back to the configured lists. The demo realm in `deploy/auth/` ships with
  this pre-configured.

The directory is advisory: pickers still accept free-typed group names, and
authorization always evaluates the OIDC `groups` claim at request time.

**Restricting public sharing.** By default anyone who can manage an app may
make it public. Set `auth.console.publicSharingGroups`
(`ORBITAL_PUBLIC_SHARING_GROUPS`) to limit that right to specific groups — other
users can then only deploy private apps (the console greys out the Public
switch; the API rejects the transition with 403). Admins are always allowed.
Already-public apps stay public until someone flips them; the policy gates
the private→public transition.

## 3. Routine operations

### Monitoring apps

- Console home shows every app (admins see all) with live states, owner
  groups and CPU/memory (cards and table both), and lets you filter by
  name, state or owner — built for fleets in the hundreds, not just a
  handful of apps. Failure states carry the error message; the Builds tab
  has per-build logs. The card/table view toggle in the header switches to
  a table (slug, state, owner groups, CPU, memory, last updated); for
  admins this is fleet-wide (every app, backed by `GET /api/v1/admin/overview`)
  and adds a stat row above the filters — app/running counts and total
  CPU/memory consumption (latest **metrics-server** samples, same source as
  the per-app Metrics tab; a plain sum, not measured against a platform
  total — apps have per-app limits, not a shared pool). Other roles see the
  same cards/table scoped to their own apps, with CPU/memory blank (no bulk
  metrics endpoint outside the admin role).
- The **Metrics** tab on each app charts CPU and memory usage against the
  platform limits (sampled from **metrics-server** every 15 s, last ~30 min
  kept in memory — history resets when the control plane restarts). If the
  cluster has no metrics-server, the tab reports "no metrics" and everything
  else works normally.
- Admins also get an **Admin** page (the shield icon in the top bar,
  `/admin` in the console): a live tail of the control plane's in-memory log
  buffer (reconciler + API), for a namespace-level view without shelling
  into the cluster. Same in-memory/per-replica caveat as the Metrics tab and
  the fleet overview: history resets on restart, and with
  `controlPlane.replicas > 1` (only possible with `database.url` set) each
  replica only reflects what it has seen itself.
- Cluster level:
  ```bash
  kubectl -n streamlit-apps get deploy,pods       # runtime health
  kubectl -n streamlit-builds get jobs,pods        # builds in flight
  kubectl -n orbital-platform logs deploy/orbital-control-plane
  ```

### Python versions & base images

Supported versions come from `baseImages.pythonVersions`. To add one:

1. Add it to the list and `helm upgrade` — the post-install job builds and
   pushes `streamlit-base:py<version>`.
2. The base image pins the platform's default Streamlit version; apps can
   override Streamlit in their own requirements.

To refresh base images (e.g. for security updates), just `helm upgrade` —
the build job re-runs. Apps pick the new base at their next rebuild
(push or **Redeploy**).

Static-site apps (`app_type=static`) share a single base image
(`baseImages.staticTag`, default `static-base:latest`) — nginx, non-root,
built from `deploy/base-image/static/`. It's controlled by
`baseImages.buildStatic` (default `true`) and rebuilt the same way as the
Python base images. Its bundled `nginx.conf` listens on `ORBITAL_APP_PORT`
(default `8501`) — if you change that setting, rebuild the static base image
to match, or static apps will fail their readiness probe.

### Routing modes

Apps are routed by **subdomain** (`<slug>.<apps-domain>`, needs wildcard DNS)
or by **path** (`<apps-domain>/app/<slug>`, one host — for environments
without wildcard DNS). Set `apps.routing` (`ORBITAL_ROUTING_MODE`) and optionally
`apps.pathPrefix`. Switching modes is safe on a live platform: the reconciler
migrates every running app's ingress and redeploys it with the matching
Streamlit `baseUrlPath` (a brief rolling restart per app). Bookmarked URLs
from the old mode stop working — announce the change to users.

Static apps have no equivalent of Streamlit's `baseUrlPath` env var, so path
mode is best-effort for them: plain multi-page HTML works, but a built SPA
bundle with absolute root-relative asset paths may break under a `/prefix`
unless the build itself was configured for it. Prefer subdomain routing for
static apps where possible.

### Hibernation

Apps idle past a timeout (default **12h**, matching Streamlit Community
Cloud) are scaled to zero replicas — state `Sleeping`. Any request to a
sleeping app's URL shows an auto-refreshing "waking up" page while the
control plane scales it back to one replica and repoints its ingress; no
extra authentication is required beyond the app's normal sharing mode.

- Platform default: `hibernation.enabled` / `hibernation.timeoutHours`
  (`ORBITAL_HIBERNATION_ENABLED` / `ORBITAL_HIBERNATION_TIMEOUT_SECONDS`).
- Platform maximum: `hibernation.maxTimeoutHours`
  (`ORBITAL_HIBERNATION_MAX_TIMEOUT_SECONDS`), default **7 days**. Caps how high
  an app's timeout can go, whether raised per-app or via the platform
  default — apps are guaranteed to eventually be reclaimed. Must be `>=`
  the default timeout (checked at startup).
- Per app: developers can raise/lower the timeout — up to the platform
  maximum — or disable hibernation entirely from the app's Settings tab.
- Mechanism: activity is recorded via the same nginx `auth_request` hook
  already used for private-app authorization, generalized to a non-blocking
  beacon for public apps — no ingress-log pipeline required. While sleeping,
  the app's Ingress is repointed at the control plane (via the in-namespace
  `sh-wake-proxy` `ExternalName` Service) which doubles as the wake proxy.
  Requires `hibernation.enabled` and a control plane Service reachable from
  the ingress controller (`ORBITAL_CONTROL_PLANE_SERVICE_HOST/PORT`, set
  automatically by the chart).

### Git-poll auto-update

Push webhooks (Settings → *Deploy webhook*) are the primary way apps redeploy
on new commits. For git hosts that can't reach this cluster to deliver a
webhook, developers can opt an app into polling instead: the reconciler
periodically runs `git ls-remote` on the tracked branch and redeploys if the
head has moved since the last deployed build.

- Platform default interval: `gitPoll.defaultIntervalMinutes`
  (`ORBITAL_GIT_POLL_DEFAULT_INTERVAL_SECONDS`), default 10 minutes.
- Platform minimum: `gitPoll.minIntervalMinutes`
  (`ORBITAL_GIT_POLL_MIN_INTERVAL_SECONDS`), default **1 minute**. Floors how low
  an app's interval can go, whether lowered per-app or via the platform
  default — keeps `git ls-remote` traffic against developers' git hosts
  bounded. Must be `<=` the default interval (checked at startup).
- Per app: developers enable polling and may override the interval — down to
  the platform minimum — from the app's Settings tab (*Poll for updates*);
  disabled by default.
- Failures (host unreachable, bad credentials, renamed branch) are logged and
  retried at the next interval — same as a webhook delivery that never
  arrives needs a fresh push.

### Resource tiers

Per-app requests/limits are platform-wide (`apps.resources.*`). Raising them
requires a `helm upgrade`; running apps apply the new limits at their next
deploy/reboot.

#### Namespace quotas and limit ranges

App creation is available to any `creator`-role user with no per-user or
per-group cap on how many apps they own. To stop a single tenant (or a
compromised account) from creating enough apps to exhaust the whole
cluster's CPU/memory - a noisy-neighbor denial of service against every
other tenant - the chart also installs a `ResourceQuota` in each of
`apps-namespace` and `builds-namespace` bounding the *total* pod count and
aggregate CPU/memory requests/limits across all apps (or build Jobs) in that
namespace:

- `apps.resourceQuota.*` (default: 50 pods, 20/50 cores requested/limited,
  40Gi/100Gi memory requested/limited) - sized to roughly 50-100x a single
  app's default per-pod request/limit (`apps.resources.*`), so a handful of
  legitimate apps never comes close to it; it only kicks in as a backstop.
- `builds.resourceQuota.*` (default: 30 pods, 10/40 cores requested/limited,
  20Gi/40Gi memory requested/limited) - sized for roughly 20 concurrent
  per-app build Jobs at their hardcoded per-job limits (2 CPU / 2Gi memory
  each, set in `builder.py`), plus headroom for the one-off base-image build
  Jobs (`builds.resources.*`).

Each namespace also gets a `LimitRange` whose `default`/`defaultRequest`
exactly match `apps.resources.*` / `builds.resources.*`. Every pod the
control plane creates already sets explicit requests/limits (which always
take precedence over a `LimitRange` default), so this is a pure
belt-and-suspenders fallback - it should never actually be exercised in
practice, but keeps any future pod that omits resources from being
unbounded.

Both are enabled by default (`apps.resourceQuota.enabled` /
`builds.resourceQuota.enabled`) and sized generously enough not to interfere
with normal use, including the minikube quick-start
(`deploy/chart/orbital/examples/minikube-values.yaml`). For a larger
deployment, raise the `requestsCpu`/`requestsMemory`/`limitsCpu`/
`limitsMemory`/`pods` fields via `helm upgrade`; there's no need to disable
the quota entirely unless you're intentionally relying on some other
enforcement mechanism.

This is a coarse, cluster-wide backstop, not a fair-share mechanism between
tenants - a per-owner-group cap on app count (enforced in `api/apps.py`'s
`create_app`) would be a more targeted follow-up but is out of scope here.

### Registry hygiene

Every build pushes an image tagged `apps/<app-id>:<build-id>`. The platform
does not garbage-collect the registry in v1 — configure your registry's own
retention (or run its GC) periodically. Deleting an app removes its
Kubernetes resources; images remain in the registry until GC.

### Privileged builds

Build Jobs execute untrusted, user-supplied repository content (arbitrary
`Dockerfile.orbital` / `RUN` steps generated from an app owner's own repo).
`builds.rootless` (`ORBITAL_BUILDKIT_ROOTLESS`) defaults to `true`, which
runs BuildKit rootless with a capability-restricted `securityContext`.
Setting it to `false` switches the build container to
`securityContext.privileged: true` instead — one of the most direct paths to
node/host compromise in Kubernetes, since a build that escapes the
container lands directly on the node. Only set it `false` where rootless
BuildKit is confirmed unsupported (e.g. nested containers/LXC without
user-namespace support — see the Troubleshooting table below). The control
plane logs a `WARNING` at startup whenever it resolves to `false`, so this
can't silently pass unnoticed.

### Database

- Default: SQLite on a PVC — fine for small teams, single replica.
- Production: set `database.url` to PostgreSQL. Migration: the schema is
  created automatically at startup; copy rows with any SQLite→Postgres tool.
- Schema changes to existing tables (e.g. new columns added by a platform
  upgrade) are also applied automatically at startup — the control plane
  checks the live schema against the current model and backfills anything
  missing before serving traffic. There's no separate migration step to run.
- Back up either the PVC or the Postgres database; it holds app definitions,
  build history, webhook tokens, and app secrets (encrypted, see below).

### Secrets encryption

Every app's `secrets.toml` (`App.secrets_toml`) is encrypted at rest with a
platform-wide symmetric key before it's written to the database, and only
decrypted at the two points that need plaintext: the owner-facing
`GET /api/v1/apps/{id}/secrets` response, and the Kubernetes `Secret` the
control plane builds for the running app.

- **Provisioning**: set `secrets.encryptionKey` (a 32-byte, base64-encoded
  key) or `secrets.existingSecret` (name of a pre-existing Secret with an
  `encryption-key` key) in the Helm values. Generate a key with:
  ```
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
  The control plane refuses to start if `ORBITAL_SECRETS_ENCRYPTION_KEY` is
  missing or malformed - unlike `auth.console.sessionSecret`, the chart
  never auto-generates this key, since a value that changed across a `helm
  upgrade` would make every already-encrypted `secrets_toml` row
  permanently undecryptable.
- **Rotation**: there's no live re-encryption in v1 - rotating the key does
  not re-encrypt existing rows. After rotating, re-enter each app's secrets
  once via `PUT /api/v1/apps/{id}/secrets` (or the console) using the new
  key; until then, apps whose secrets predate the rotation will fail to
  redeploy (decryption error surfaces in the reconciler logs).
- **Upgrading from a version before this feature**: any `secrets_toml` rows
  written before the key existed are plaintext and will fail to decrypt.
  Set the key, then re-enter secrets for each affected app the same way.

## 4. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| App stuck `building` | `kubectl -n streamlit-builds logs job/build-<id>` (containers `fetch`, `buildkit`); commonest causes: bad main-file path, unresolvable dependencies, registry unreachable |
| `build_failed`: "not supported" | repo uses `Pipfile`/conda only, or `packages.txt` expectations — Python deps only (see [USER.md](USER.md)) |
| Rootless build fails with `newuidmap` errors | cluster lacks user-namespace support → `builds.rootless=false` |
| `deploy_failed`: ImagePullBackOff | nodes can't resolve `registry.pullPrefix` — verify a node can pull the app image manually |
| `deploy_failed`: CrashLoopBackOff | app crashes at start — Logs tab shows stderr; often a missing secret or bad entrypoint |
| App killed / restarts (OOM) | raise `apps.resources.memLimit` or fix the app's memory use |
| Console login loop / state mismatch | `console.url` must exactly match the browser-facing URL; check IdP redirect URIs |
| 403 after login | user's groups map to no role, or the groups claim is missing from the ID token (check the IdP's group mapper) |
| Webhook doesn't trigger | webhook URL must be reachable from the git host; check per-app rate limit (5/min, `ORBITAL_WEBHOOK_RATE_LIMIT_PER_MINUTE`) |
| Login intermittently fails with 429 | per-IP login rate limit (20/min, `ORBITAL_LOGIN_RATE_LIMIT_PER_MINUTE`) tripped — expected under a flood, but if it fires for normal traffic check whether many real users share one IP (corporate NAT/VPN egress) and raise the limit |

## 5. Security notes

- App code is untrusted: pods run as non-root with read-only rootfs, no SA
  token, dropped capabilities, and (recommended) rootless builds — see
  [Privileged builds](#privileged-builds) for the risk of disabling the
  latter. Consider adding NetworkPolicies denying app-pod egress to
  cluster-internal CIDRs
  and cloud metadata endpoints (SPEC §8) — not yet templated in the chart.
- Never expose the control plane without `auth.console.enabled=true`; an
  unauthenticated control plane treats every caller as admin.
- `ORBITAL_SESSION_SECRET` signs the console session cookie (identity +
  role); the control plane refuses to start with `ui_auth_enabled=true` if
  it's left at the insecure built-in default or is under 32 characters. The
  Helm chart auto-generates a strong value when `auth.console.sessionSecret`
  is left unset (recommended) and fails the render if you set it explicitly
  to something too short.
- The console session cookie is `Secure` by default
  (`auth.console.sessionCookieSecure` / `ORBITAL_SESSION_COOKIE_SECURE`),
  which requires the console to be served over TLS — see
  [INSTALL.md](INSTALL.md) prerequisites. Only set it to `false` for a
  plain-HTTP dev/demo console (e.g.
  [examples/minikube-values.yaml](../deploy/chart/orbital/examples/minikube-values.yaml)),
  never in production.
- App secrets live in the platform database (encrypted at rest, see
  [Secrets encryption](#secrets-encryption)) **and** as plaintext Kubernetes
  Secrets in `streamlit-apps` (required so app pods can read them) —
  restrict access to both.
- The demo Keycloak in `deploy/auth/` runs in dev mode with fixed passwords:
  demos only, never production.
- **Rate limiting** (issue #82): `/api/auth/login` and `/api/auth/callback`
  (per client IP, default 20/min, `ORBITAL_LOGIN_RATE_LIMIT_PER_MINUTE`) and
  the per-app git-push webhook (per `app_id`, default 5/min,
  `ORBITAL_WEBHOOK_RATE_LIMIT_PER_MINUTE`) are throttled in-process, returning
  `429` with `Retry-After` once tripped. This is defense-in-depth, not an
  auth control — token/state entropy already makes brute force impractical
  on these routes — the goal is to stop a request flood from exhausting
  control-plane capacity or tripping the IdP's own rate limits (both
  `callback()` and `authz()` call out synchronously to an external service).
  Two things to know before relying on it:
  - **Single process, in-memory counters.** There's no shared store (no
    Redis) across replicas. `controlPlane.replicas > 1` is only reachable
    when `database.url` (Postgres) is set — see
    `deploy/chart/orbital/templates/control-plane.yaml` — and in that mode
    each replica enforces its own independent counter, so the *effective*
    limit scales roughly with replica count (e.g. 3 replicas behind a
    load balancer that spreads requests evenly behave closer to 3x the
    configured per-key limit). Accepted as a documented limitation for a
    backstop control, not a blocker.
  - **`/authz/{app_id}` is deliberately NOT limited in-app.** It's on the hot
    path for every request to every private app (the ingress `auth_request`
    target), so per-request limiter overhead there is the wrong tradeoff,
    and the SPEC's own hardening guidance allows scoping it out explicitly.
    If you want protection against a flood of `/authz` calls, configure your
    ingress controller's own rate limiting instead — e.g. nginx-ingress's
    `nginx.ingress.kubernetes.io/limit-rps` (or `limit-rpm`/`limit-burst-multiplier`)
    annotation on the app Ingress. This is intentionally the primary
    mitigation layer for that endpoint, not a fallback.

## 6. Demo identity stack

For evaluation without a corporate IdP:

```bash
bash deploy/auth/setup-auth.sh    # Keycloak (dev mode) + oauth2-proxy
```

Demo users: `carol/carol123` (admins), `alice/alice123` (data-team),
`bob/bob123` (viewers). Keycloak admin console: `keycloak.<apps-domain>`
(admin/admin).
