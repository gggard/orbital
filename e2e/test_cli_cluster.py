"""Cluster tier: the CLI against a real Orbital install (control plane,
reconciler, in-cluster BuildKit, ingress), deploying real apps from git.

Skipped unless ORBITAL_E2E_URL is set. CI runs it on minikube via
.github/workflows/e2e.yml; to run it against your own platform see
e2e/README.md.

    ORBITAL_E2E_URL       control-plane URL (required)
    ORBITAL_E2E_TOKEN     API token, if the platform has auth enabled
    ORBITAL_E2E_INGRESS   base URL of the ingress controller (e.g.
                          http://192.168.49.2); requests are sent there with
                          the app's Host header, so no DNS is needed. Default:
                          the app's own URL.
    ORBITAL_E2E_STREAMLIT_REPO / _BRANCH / _MAIN_FILE
    ORBITAL_E2E_STATIC_REPO / _BRANCH / _OUTPUT_DIR
    ORBITAL_E2E_SCANS=1   also run a vulnerability scan (needs trivy in-cluster)
"""

from __future__ import annotations

import os
import time
import uuid
from urllib.parse import urlsplit

import httpx
import pytest
from conftest import Orbital

URL = os.environ.get("ORBITAL_E2E_URL")
pytestmark = pytest.mark.skipif(not URL, reason="ORBITAL_E2E_URL not set (no cluster)")

DEPLOY_TIMEOUT = os.environ.get("ORBITAL_E2E_DEPLOY_TIMEOUT", "20m")
STREAMLIT_REPO = os.environ.get(
    "ORBITAL_E2E_STREAMLIT_REPO", "https://github.com/streamlit/streamlit-example"
)
STREAMLIT_BRANCH = os.environ.get("ORBITAL_E2E_STREAMLIT_BRANCH", "master")
STREAMLIT_MAIN = os.environ.get("ORBITAL_E2E_STREAMLIT_MAIN_FILE", "streamlit_app.py")
# Orbital's own repo doubles as a static site: docs/index.html is the landing page
STATIC_REPO = os.environ.get("ORBITAL_E2E_STATIC_REPO", "https://github.com/gggard/orbital")
STATIC_BRANCH = os.environ.get("ORBITAL_E2E_STATIC_BRANCH", "main")
STATIC_OUTPUT_DIR = os.environ.get("ORBITAL_E2E_STATIC_OUTPUT_DIR", "docs")


@pytest.fixture
def orbital(tmp_path) -> Orbital:
    assert URL
    return Orbital(URL, tmp_path, token=os.environ.get("ORBITAL_E2E_TOKEN"))


@pytest.fixture
def slug(orbital):
    """A unique slug per test, deleted afterwards whatever happened."""
    name = f"e2e-{uuid.uuid4().hex[:8]}"
    yield name
    orbital("apps", "delete", name, "--yes", "--wait", "--timeout", "5m")


def fetch(app_url: str, path: str = "/") -> httpx.Response:
    """GET through the ingress, by Host header when ORBITAL_E2E_INGRESS is set."""
    parts = urlsplit(app_url)
    ingress = os.environ.get("ORBITAL_E2E_INGRESS")
    if ingress:
        return httpx.get(
            f"{ingress.rstrip('/')}{path}",
            headers={"Host": parts.netloc},
            timeout=15,
            follow_redirects=False,
        )
    return httpx.get(f"{app_url.rstrip('/')}{path}", timeout=15, follow_redirects=False)


def eventually(check, timeout: float = 120, interval: float = 3):
    """Ingress/rollout propagation isn't instant even once the app is running."""
    deadline = time.monotonic() + timeout
    last: object = None
    while time.monotonic() < deadline:
        try:
            last = check()
            if last:
                return last
        except httpx.HTTPError as e:
            last = e
        time.sleep(interval)
    pytest.fail(f"condition not met within {timeout}s (last: {last!r})")


def test_platform_reachable(orbital):
    assert orbital("health").code == 0
    version = orbital("version").json
    assert version["platform"], version


def test_streamlit_app_lifecycle(orbital, slug, tmp_path):
    manifest = tmp_path / "orbital.toml"
    manifest.write_text(
        f'slug = "{slug}"\nrepo_url = "{STREAMLIT_REPO}"\nbranch = "{STREAMLIT_BRANCH}"\n'
        f'main_file = "{STREAMLIT_MAIN}"\n[hibernate]\nenabled = false\n'
    )

    # real build in BuildKit + rollout, build log streamed to stderr
    deployed = orbital(
        "apply", "-f", str(manifest), "--wait", "--follow", "--timeout", DEPLOY_TIMEOUT
    )
    assert deployed.code == 0, deployed.stderr[-4000:]
    app = deployed.json
    assert app["state"] == "running"
    assert "--- build " in deployed.stderr  # --follow streamed something

    # served through the ingress
    eventually(lambda: fetch(app["url"], "/_stcore/health").text.strip() == "ok")

    # observability
    assert orbital("builds", "logs", slug).stdout.strip()
    builds = orbital("builds", "list", slug).json
    assert builds[0]["phase"] == "succeeded" and builds[0]["commit_sha"]
    eventually(lambda: orbital("logs", slug, "--tail", "50").stdout.strip(), timeout=60)

    # secrets restart the app without a rebuild
    assert orbital("secrets", "set", slug, "-f", "-", input='E2E = "yes"\n').code == 0
    assert orbital("wait", slug, "--timeout", "5m").code == 0
    assert orbital("builds", "list", slug).json == builds

    # reboot
    rebooted = orbital("reboot", slug, "--wait", "--timeout", "5m")
    assert rebooted.code == 0, rebooted.stderr
    eventually(lambda: fetch(app["url"], "/_stcore/health").text.strip() == "ok")

    # redeploy produces a new build
    again = orbital("deploy", slug, "--wait", "--timeout", DEPLOY_TIMEOUT)
    assert again.code == 0, again.stderr[-4000:]
    assert again.json["current_build_id"] != app["current_build_id"]

    if os.environ.get("ORBITAL_E2E_SCANS") == "1":
        scan = orbital("scans", "run", slug, "--wait", "--timeout", "15m")
        assert scan.code == 0, scan.stderr
        assert scan.json["status"] == "succeeded"

    # delete tears everything down
    gone = orbital("apps", "delete", slug, "--yes", "--wait", "--timeout", "5m")
    assert gone.code == 0, gone.stderr
    eventually(lambda: fetch(app["url"], "/_stcore/health").status_code == 404, timeout=60)


def test_static_site(orbital, slug):
    created = orbital(
        "apps",
        "create",
        slug,
        "--type",
        "static",
        "--repo",
        STATIC_REPO,
        "--branch",
        STATIC_BRANCH,
        "--output-dir",
        STATIC_OUTPUT_DIR,
        "--wait",
        "--timeout",
        DEPLOY_TIMEOUT,
    )
    assert created.code == 0, created.stderr[-4000:]
    url = created.json["url"]
    page = eventually(lambda: (r := fetch(url)).status_code == 200 and r)
    assert "<html" in page.text.lower()


def test_broken_build_fails_with_exit_8(orbital, slug):
    result = orbital(
        "apps",
        "create",
        slug,
        "--repo",
        STREAMLIT_REPO,
        "--branch",
        "e2e-no-such-branch",
        "--wait",
        "--timeout",
        "10m",
    )
    assert result.code == 8, result.stderr[-4000:]
    assert result.error["code"] == 8
