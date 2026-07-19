# streamlit-host — Administrator Manual

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

- `auth.console.knownGroups` (`SH_KNOWN_GROUPS`) — a static list, works with
  any IdP;
- `auth.console.groupsFromKeycloak` (`SH_GROUPS_FROM_KEYCLOAK`) — list the
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
(`SH_PUBLIC_SHARING_GROUPS`) to limit that right to specific groups — other
users can then only deploy private apps (the console greys out the Public
switch; the API rejects the transition with 403). Admins are always allowed.
Already-public apps stay public until someone flips them; the policy gates
the private→public transition.

## 3. Routine operations

### Monitoring apps

- Console home shows every app (admins see all) with live states. Failure
  states carry the error message; the Builds tab has per-build logs.
- The **Metrics** tab on each app charts CPU and memory usage against the
  platform limits (sampled from **metrics-server** every 15 s, last ~30 min
  kept in memory — history resets when the control plane restarts). If the
  cluster has no metrics-server, the tab reports "no metrics" and everything
  else works normally.
- Cluster level:
  ```bash
  kubectl -n streamlit-apps get deploy,pods       # runtime health
  kubectl -n streamlit-builds get jobs,pods        # builds in flight
  kubectl -n streamlit-platform logs deploy/streamlit-host-control-plane
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

### Routing modes

Apps are routed by **subdomain** (`<slug>.<apps-domain>`, needs wildcard DNS)
or by **path** (`<apps-domain>/app/<slug>`, one host — for environments
without wildcard DNS). Set `apps.routing` (`SH_ROUTING_MODE`) and optionally
`apps.pathPrefix`. Switching modes is safe on a live platform: the reconciler
migrates every running app's ingress and redeploys it with the matching
Streamlit `baseUrlPath` (a brief rolling restart per app). Bookmarked URLs
from the old mode stop working — announce the change to users.

### Hibernation

Apps idle past a timeout (default **12h**, matching Streamlit Community
Cloud) are scaled to zero replicas — state `Sleeping`. Any request to a
sleeping app's URL shows an auto-refreshing "waking up" page while the
control plane scales it back to one replica and repoints its ingress; no
extra authentication is required beyond the app's normal sharing mode.

- Platform default: `hibernation.enabled` / `hibernation.timeoutHours`
  (`SH_HIBERNATION_ENABLED` / `SH_HIBERNATION_TIMEOUT_SECONDS`).
- Per app: developers can raise/lower the timeout or disable hibernation
  entirely from the app's Settings tab.
- Mechanism: activity is recorded via the same nginx `auth_request` hook
  already used for private-app authorization, generalized to a non-blocking
  beacon for public apps — no ingress-log pipeline required. While sleeping,
  the app's Ingress is repointed at the control plane (via the in-namespace
  `sh-wake-proxy` `ExternalName` Service) which doubles as the wake proxy.
  Requires `hibernation.enabled` and a control plane Service reachable from
  the ingress controller (`SH_CONTROL_PLANE_SERVICE_HOST/PORT`, set
  automatically by the chart).

### Git-poll auto-update

Push webhooks (Settings → *Deploy webhook*) are the primary way apps redeploy
on new commits. For git hosts that can't reach this cluster to deliver a
webhook, developers can opt an app into polling instead: the reconciler
periodically runs `git ls-remote` on the tracked branch and redeploys if the
head has moved since the last deployed build.

- Platform default interval: `gitPoll.defaultIntervalMinutes`
  (`SH_GIT_POLL_DEFAULT_INTERVAL_SECONDS`), default 10 minutes.
- Per app: developers enable polling and may override the interval from the
  app's Settings tab (*Poll for updates*); disabled by default.
- Failures (host unreachable, bad credentials, renamed branch) are logged and
  retried at the next interval — same as a webhook delivery that never
  arrives needs a fresh push.

### Resource tiers

Per-app requests/limits are platform-wide (`apps.resources.*`). Raising them
requires a `helm upgrade`; running apps apply the new limits at their next
deploy/reboot.

### Registry hygiene

Every build pushes an image tagged `apps/<app-id>:<build-id>`. The platform
does not garbage-collect the registry in v1 — configure your registry's own
retention (or run its GC) periodically. Deleting an app removes its
Kubernetes resources; images remain in the registry until GC.

### Database

- Default: SQLite on a PVC — fine for small teams, single replica.
- Production: set `database.url` to PostgreSQL. Migration: the schema is
  created automatically at startup; copy rows with any SQLite→Postgres tool.
- Back up either the PVC or the Postgres database; it holds app definitions,
  build history, webhook tokens, and app secrets.

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
| Webhook doesn't trigger | webhook URL must be reachable from the git host; check per-app rate limit (5/min) |

## 5. Security notes

- App code is untrusted: pods run as non-root with read-only rootfs, no SA
  token, dropped capabilities, and (recommended) rootless builds. Consider
  adding NetworkPolicies denying app-pod egress to cluster-internal CIDRs
  and cloud metadata endpoints (SPEC §8) — not yet templated in the chart.
- Never expose the control plane without `auth.console.enabled=true`; an
  unauthenticated control plane treats every caller as admin.
- App secrets live in the platform database **and** as Kubernetes Secrets in
  `streamlit-apps` — restrict access to both.
- The demo Keycloak in `deploy/auth/` runs in dev mode with fixed passwords:
  demos only, never production.

## 6. Demo identity stack

For evaluation without a corporate IdP:

```bash
bash deploy/auth/setup-auth.sh    # Keycloak (dev mode) + oauth2-proxy
```

Demo users: `carol/carol123` (admins), `alice/alice123` (data-team),
`bob/bob123` (viewers). Keycloak admin console: `keycloak.<apps-domain>`
(admin/admin).
