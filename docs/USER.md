# streamlit-host — User Manual

Audience: developers deploying Streamlit apps (creator role) and app viewers.
If something in the console is missing for you (no "New app" button, no
Settings tab), your role doesn't include it — see your platform admin.

## 1. Deploying an app

1. Open the console and sign in with your organization account.
2. Click **New app** and fill in:
   - **Slug** — becomes your URL: `<slug>.<apps-domain>` (or
     `<apps-domain>/app/<slug>` on platforms configured for path routing).
     Lowercase letters, digits, dashes.
   - **Git repository URL** — any reachable git host (public repos in v1).
   - **Branch** (default `main`) and **main file** (default
     `streamlit_app.py`), the path of the Streamlit script relative to the
     repository root.
   - **Python version**.
   - **Public / Private** and, for private apps, the viewer groups.
   - Optional **secrets** (TOML).
3. Click **Deploy**. You land on the app page; the state chip walks through
   *queued → building → deploying → running*. The Builds tab streams the
   build log. First builds typically take 1–3 minutes.

### Dependencies

The platform installs your Python dependencies from **exactly one** file,
searched first next to your main file, then in the repository root:

| Priority | File | Handling |
|---|---|---|
| 1 | `uv.lock` (+ `pyproject.toml`) | exact locked versions (recommended) |
| 2 | `requirements.txt` | pip-style, installed with uv |
| 3 | `pyproject.toml` | dependencies resolved then installed |

Notes:

- Pin your versions (`streamlit==1.x`, `pandas>2` …) to avoid surprise
  upgrades on rebuilds.
- **Linux (apt) packages are not supported.** A `packages.txt` file is
  ignored with a warning; if your dependency needs a system library that is
  not in the base image, ask your admin.
- `Pipfile` and conda `environment.yml` are not supported.
- Streamlit itself is preinstalled; add it to your requirements only to pin
  a specific version.

### App runtime facts

- Your working directory is the repository root; use relative paths for data
  files.
- The filesystem is read-only except `/tmp` and `$HOME`; anything written is
  lost on restart.
- Default resources per app: ~1 CPU / 2 GiB memory (platform-configurable).
  The app is restarted if it exceeds its memory limit.
- Your repo's `.streamlit/config.toml` (repo root) is honored — except a few
  locked options (error details hidden from viewers, XSRF protection on).

## 2. Updating your app

- **On push**: in Settings → *Deploy webhook*, copy the webhook URL into your
  git host (GitHub/GitLab/Gitea → Webhooks, trigger on push). Every push to
  the tracked branch redeploys automatically.
- **Manually**: the **Redeploy** button rebuilds from the branch head.
- **Reboot** restarts the app without rebuilding (clears memory and
  `st.cache_*`).
- Changing branch / main file / Python version in **Settings** triggers a
  rebuild.

## 3. Secrets

The **Secrets** tab holds TOML that your app reads via `st.secrets` —
identical to local development with `.streamlit/secrets.toml`:

```toml
api_key = "sk-..."

[db]
host = "db.internal"
password = "..."
```

Saving restarts the app (no rebuild). Never commit secrets to your repo; a
committed `secrets.toml` is shadowed and a warning is logged.

## 4. Sharing your app

**Sharing** tab, *Viewer access*:

- **Public** — anyone with the URL can use the app. (On some platforms this
  is restricted to specific groups; the switch is greyed out if you are not
  allowed to publish publicly.)
- **Private** — viewers must sign in through the organization's identity
  provider; access is limited to the OIDC groups you list (empty list = any
  signed-in user). Changes apply live.

Private-app viewers hitting the URL are redirected to the login page; users
outside the allowed groups get a 403.

## 5. Ownership (who can manage the app)

*Sharing → Ownership* lists the **owner groups**: members of these groups see
the app in the console (and manage it, if they have the creator role).
You can add or remove co-owner groups, but must keep at least one group you
belong to — transferring an app entirely to another team is done by an admin.

## 6. Observing your app

- **Logs** tab: live runtime logs (Follow toggle, download).
- **Builds** tab: build history; click a row for that build's log.
- **Metrics** tab: CPU and memory over the last ~30 minutes, with the current
  value and its share of the app's limit. Memory climbing toward 100% means
  the app risks an out-of-memory restart — cache less or ask your admin for a
  higher tier. (Requires the cluster's metrics-server; if it's absent the tab
  says so.)
- **Overview**: current state, commit, build times, ownership, visibility.

## 7. Hibernation

Apps with no traffic for 12 hours (platform default) scale to zero and show
as **Sleeping**. The next visit to the app's URL wakes it automatically — the
visitor sees a "waking up" page for a few seconds while it starts back up,
then lands on the app. No sign-in beyond what the app normally requires.

In Settings you can raise or lower your app's timeout, or turn hibernation
off entirely if it needs to stay warm (e.g. it's polled by another system).
A sleeping app can also be woken from the console with the **Wake now**
button on the app page.

## 8. Limits & good practices

- One dependency file; Python packages only.
- Ephemeral storage only — persist data in external services (S3, DBs, …).
- Webhook redeploys are rate-limited (bursts are coalesced).
- Keep memory below the app limit; cache with `st.cache_data` judiciously.
- The app must listen as a standard Streamlit script — no custom servers,
  ports, or Procfiles; the platform runs `streamlit run <main file>`.
