# Orbital — REST API Guide

Audience: developers who want to deploy and monitor apps programmatically
instead of (or alongside) the console. For the console-based flow see
[USER.md](USER.md); for local development see [DEVELOPMENT.md](DEVELOPMENT.md).

All endpoints are served by the control plane (default `http://localhost:8000`
in local dev; your platform's control-plane host in production) under
`/api/v1`. The full OpenAPI schema and an interactive explorer are always
available at `/docs`.

## Authentication

If your platform runs with auth disabled (`ORBITAL_UI_AUTH_ENABLED=false`,
the default for local dev — see [DEVELOPMENT.md](DEVELOPMENT.md)), every
request is treated as an admin with no credentials required. This is what
the examples below assume.

If your platform has auth enabled, the console itself uses a server-signed
session cookie (OIDC login via `GET /api/auth/login`), but scripts and
automation should use a **personal API token** instead:

1. Sign in to the console and open **My tokens** (account menu, top right),
   or call the endpoint directly once you have a session:

   ```bash
   curl -sX POST localhost:8000/api/v1/me/tokens \
     -H 'Content-Type: application/json' \
     -H 'Cookie: session=<your browser session cookie>' \
     -d '{"name": "ci", "ttl_days": 30}'
   ```

   The response's `token` field (`orbpat_...`) is shown **once** — copy it
   immediately, it can't be retrieved again. `ttl_days` is optional and
   defaults to (and is capped at) the platform's configured maximum
   (`ORBITAL_API_TOKEN_MAX_TTL_DAYS`, 90 days by default); requesting more
   is rejected with `422`.
2. Use it on every subsequent request as a bearer token — no session/cookie
   needed:

   ```bash
   curl -H "Authorization: Bearer $ORBITAL_TOKEN" localhost:8000/api/v1/apps
   ```

A token carries a snapshot of the groups you were in when you created it,
so its **role** (viewer/creator/admin) always reflects the platform's
*current* group→role mapping — but if you're later added to or removed from
an actual OIDC group, that only takes effect on your next token (or your
next browser sign-in). List (`GET /api/v1/me/tokens`) and revoke
(`DELETE /api/v1/me/tokens/{id}`) your own tokens from the console's **My
tokens** page or the API directly; revocation is immediate.

## Deploying an app

Create an app by pointing at a git repository. This schedules a build; the
app moves through `building → deploying → running` (poll `GET /apps/{id}` or
tail logs to watch it, see [Monitoring](#monitoring-an-app) below).

**Request body** (`AppCreate`): `slug` (DNS-safe, e.g. `my-app`), `repo_url`,
`branch` (default `main`), `main_file` (default `streamlit_app.py`),
`python_version`, `public` (default `true`), `allowed_groups`,
`secrets_toml`, `hibernate_enabled`, `hibernate_after_seconds`.

### Shell

```bash
BASE=http://localhost:8000/api/v1

curl -sX POST "$BASE/apps" \
  -H 'Content-Type: application/json' \
  -d '{
        "slug": "my-app",
        "repo_url": "https://github.com/streamlit/streamlit-example",
        "branch": "master",
        "main_file": "streamlit_app.py"
      }'
```

### Python

```python
import requests

BASE = "http://localhost:8000/api/v1"

resp = requests.post(
    f"{BASE}/apps",
    json={
        "slug": "my-app",
        "repo_url": "https://github.com/streamlit/streamlit-example",
        "branch": "master",
        "main_file": "streamlit_app.py",
    },
)
resp.raise_for_status()
app = resp.json()
print(app["id"], app["state"], app["url"])
```

### JavaScript

```js
const BASE = "http://localhost:8000/api/v1";

const resp = await fetch(`${BASE}/apps`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    slug: "my-app",
    repo_url: "https://github.com/streamlit/streamlit-example",
    branch: "master",
    main_file: "streamlit_app.py",
  }),
});
if (!resp.ok) throw new Error(`create failed: ${resp.status}`);
const app = await resp.json();
console.log(app.id, app.state, app.url);
```

### Redeploying, rebooting, waking

- `POST /apps/{id}/deploy` — rebuild and redeploy from the tracked branch's
  current head (same as the console's **Redeploy** button). 409 if a build is
  already in progress.
- `POST /apps/{id}/reboot` — restart the running container without rebuilding
  (clears memory/`st.cache_*`). 409 unless the app is `running` or
  `deploy_failed`.
- `POST /apps/{id}/wake` — wake a hibernating app. 409 unless the app is
  `sleeping`.

```bash
curl -sX POST "$BASE/apps/$APP_ID/deploy"
curl -sX POST "$BASE/apps/$APP_ID/reboot"
curl -sX POST "$BASE/apps/$APP_ID/wake"
```

```python
requests.post(f"{BASE}/apps/{app_id}/deploy").raise_for_status()
```

```js
await fetch(`${BASE}/apps/${appId}/deploy`, { method: "POST" });
```

Automatic redeploy-on-push is available too: each app has a
`webhook_path` (returned in `AppOut`); point your git host's push webhook at
`POST /webhooks/apps/{app_id}/{token}` and pushes to the tracked branch
redeploy without any polling.

## Monitoring an app

### Status and build history

```bash
curl -s "$BASE/apps/$APP_ID" | jq '.state, .error, .current_build_id'
curl -s "$BASE/apps/$APP_ID/builds" | jq '.[] | {id, phase, commit_sha}'
curl -s "$BASE/apps/$APP_ID/builds/$BUILD_ID/logs"
```

```python
app = requests.get(f"{BASE}/apps/{app_id}").json()
print(app["state"], app["error"])

builds = requests.get(f"{BASE}/apps/{app_id}/builds").json()
build_log = requests.get(
    f"{BASE}/apps/{app_id}/builds/{builds[0]['id']}/logs"
).text
```

```js
const app = await (await fetch(`${BASE}/apps/${appId}`)).json();
console.log(app.state, app.error);

const builds = await (await fetch(`${BASE}/apps/${appId}/builds`)).json();
```

### Runtime logs

`GET /apps/{id}/logs?tail=500` returns the last `tail` lines as plain text.
Add `follow=true` to stream new lines as they arrive (chunked response, like
`kubectl logs -f`).

```bash
curl -s "$BASE/apps/$APP_ID/logs?tail=200"
curl -sN "$BASE/apps/$APP_ID/logs?follow=true"   # -N: don't buffer, stream
```

```python
logs = requests.get(f"{BASE}/apps/{app_id}/logs", params={"tail": 200}).text

with requests.get(
    f"{BASE}/apps/{app_id}/logs", params={"follow": "true"}, stream=True
) as r:
    for line in r.iter_lines():
        if line:
            print(line.decode())
```

```js
const logs = await (
  await fetch(`${BASE}/apps/${appId}/logs?tail=200`)
).text();

// Streaming with follow=true:
const res = await fetch(`${BASE}/apps/${appId}/logs?follow=true`);
const reader = res.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  process.stdout.write(decoder.decode(value));
}
```

### Metrics and analytics

`GET /apps/{id}/metrics` returns CPU/memory samples (`current` value plus a
`series`) against the app's resource `limits`; `available: false` means the
cluster has no metrics-server data yet. `GET /apps/{id}/analytics` returns
view counts and unique-viewer trends.

```bash
curl -s "$BASE/apps/$APP_ID/metrics" | jq '.current, .limits'
curl -s "$BASE/apps/$APP_ID/analytics" | jq '.total_views, .unique_viewers_7d'
```

```python
metrics = requests.get(f"{BASE}/apps/{app_id}/metrics").json()
if metrics["available"]:
    print(metrics["current"], "/", metrics["limits"])

analytics = requests.get(f"{BASE}/apps/{app_id}/analytics").json()
print(analytics["total_views"], analytics["unique_viewers_7d"])
```

```js
const metrics = await (
  await fetch(`${BASE}/apps/${appId}/metrics`)
).json();
if (metrics.available) console.log(metrics.current, metrics.limits);
```

### Health check

`GET /healthz` (no auth, no `/api/v1` prefix) reports control-plane liveness
— useful for external uptime monitors:

```bash
curl -s http://localhost:8000/healthz
```

## Deleting an app

```bash
curl -sX DELETE "$BASE/apps/$APP_ID"
```

Returns `202 {"status": "deleting"}`; the reconciler tears down the
Deployment/Service/Ingress asynchronously.

## Reference

See `/docs` (Swagger UI) or `/openapi.json` on your control plane for the
complete, always-current schema, including admin-only endpoints
(`/api/v1/admin/overview`, `/api/v1/admin/logs`) and settings updates
(`PATCH /apps/{id}`, `PUT /apps/{id}/secrets`).
