"""End-to-end fixtures.

Local tier (always runs): the installed `orbital` executable, driven as a
subprocess exactly like a CI job would, against a real control plane
(uvicorn, real HTTP, SQLite). Kubernetes is replaced by `SimulatedReconciler`,
which moves apps through the same state machine as the real reconciler
(SPEC §6) by writing to the control plane's database.

Cluster tier (`test_cli_cluster.py`): only runs when ORBITAL_E2E_URL points
at a real platform (see e2e/README.md and .github/workflows/e2e.yml).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent


def orbital_executable() -> str:
    exe = shutil.which("orbital", path=str(Path(sys.executable).parent)) or shutil.which("orbital")
    if exe is None:
        pytest.exit("the `orbital` CLI is not installed: run `make cli-install`", returncode=2)
    return exe


@dataclass
class Result:
    code: int
    stdout: str
    stderr: str

    @property
    def json(self):
        return json.loads(self.stdout)

    @property
    def error(self) -> dict:
        """The JSON error object the CLI prints last on stderr."""
        return json.loads(self.stderr.strip().splitlines()[-1])["error"]


class Orbital:
    """Runs the real CLI binary with an isolated config and environment."""

    def __init__(self, url: str, home: Path, token: str | None = None):
        self.exe = orbital_executable()
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home),
            "ORBITAL_URL": url,
            "ORBITAL_CONFIG": str(home / "orbital.toml"),
            "CI": "true",  # like a CI runner: never prompt
        }
        if token:
            self.env["ORBITAL_TOKEN"] = token

    def __call__(self, *args: str, input: str | None = None, timeout: float = 900) -> Result:
        proc = subprocess.run(
            [self.exe, *args],
            input=input,
            capture_output=True,
            text=True,
            env=self.env,
            timeout=timeout,
        )
        return Result(proc.returncode, proc.stdout, proc.stderr)


# -- local tier ----------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SimulatedReconciler(threading.Thread):
    """Stands in for orbital.k8s.reconciler (which needs a cluster), writing
    the same state transitions to the database:

    pending deploy -> building (new Build row) -> deploying -> running,
    or build_failed when the branch is named "broken"; pending reboot ->
    deploying -> running; wake request on a sleeping app -> deploying ->
    running; pending delete -> row removed. Apps whose slug starts with
    "frozen" are never touched (to exercise --wait timeouts).
    """

    def __init__(self, db_url: str, tick: float = 0.3):
        super().__init__(daemon=True)
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(db_url, connect_args={"timeout": 30})
        self.Session = sessionmaker(engine)
        self.tick = tick
        self.stopped = threading.Event()
        self.errors: list[BaseException] = []

    def run(self) -> None:
        while not self.stopped.wait(self.tick):
            try:
                self.step()
            except Exception as e:  # surfaced by the fixture teardown
                self.errors.append(e)

    def step(self) -> None:
        from datetime import UTC, datetime

        from sqlalchemy import select

        from orbital.models import App, AppState, Build, BuildPhase, PendingAction

        with self.Session.begin() as session:
            for app in session.scalars(select(App)).all():
                if app.slug.startswith("frozen"):
                    continue
                if app.pending_action == PendingAction.delete:
                    session.delete(app)
                elif app.pending_action == PendingAction.deploy and app.state != AppState.building:
                    build = Build(app_id=app.id, commit_sha="0" * 40, phase=BuildPhase.running)
                    session.add(build)
                    session.flush()
                    app.current_build_id = build.id
                    app.state, app.pending_action, app.error = (
                        AppState.building,
                        PendingAction.none,
                        None,
                    )
                elif app.state == AppState.building:
                    build = session.get(Build, app.current_build_id)
                    build.finished_at = datetime.now(UTC)
                    if app.branch == "broken":
                        build.phase, build.error = (
                            BuildPhase.failed,
                            "simulated: pip install failed",
                        )
                        app.state, app.error = (
                            AppState.build_failed,
                            "build failed: pip install failed",
                        )
                    else:
                        build.phase = BuildPhase.succeeded
                        app.current_image = f"registry.local/app-{app.id}:{build.id}"
                        app.state = AppState.deploying
                elif app.state == AppState.deploying:
                    app.state = AppState.running
                elif app.pending_action == PendingAction.reboot:
                    app.state, app.pending_action = AppState.deploying, PendingAction.none
                elif app.state == AppState.sleeping and app.wake_requested_at is not None:
                    app.state, app.wake_requested_at = AppState.deploying, None


@dataclass
class LocalPlatform:
    url: str
    db_url: str
    reconciler: SimulatedReconciler

    def set_state(self, slug: str, state: str) -> None:
        """Force a state, as the real reconciler would on cluster events."""
        from sqlalchemy import select

        from orbital.models import App, AppState, PendingAction

        with self.reconciler.Session.begin() as session:
            app = session.scalars(select(App).where(App.slug == slug)).one()
            app.state = AppState(state)
            app.pending_action = PendingAction.none


@pytest.fixture
def local_platform(tmp_path):
    pytest.importorskip("orbital.k8s", reason="control plane not installed (make cli-install)")
    from cryptography.fernet import Fernet

    db_url = f"sqlite:///{tmp_path}/e2e.db"
    port = _free_port()
    env = {
        **os.environ,
        "ORBITAL_DATABASE_URL": db_url,
        "ORBITAL_RECONCILER_ENABLED": "false",  # replaced by SimulatedReconciler
        "ORBITAL_UI_AUTH_ENABLED": "false",
        "ORBITAL_SECRETS_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    }
    log = (tmp_path / "control-plane.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "orbital.main:app", "--port", str(port)],
        env=env,
        cwd=tmp_path,  # keep the repo's .env out of it
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{url}/healthz", timeout=1).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if proc.poll() is not None:
                pytest.fail(
                    f"control plane exited:\n{(tmp_path / 'control-plane.log').read_text()}"
                )
            time.sleep(0.1)
        else:
            pytest.fail("control plane did not become healthy")
        reconciler = SimulatedReconciler(db_url)
        reconciler.start()
        yield LocalPlatform(url, db_url, reconciler)
        reconciler.stopped.set()
        reconciler.join(5)
        assert not reconciler.errors, reconciler.errors
    finally:
        proc.terminate()
        proc.wait(10)
        log.close()


@pytest.fixture
def orbital(local_platform, tmp_path) -> Orbital:
    home = tmp_path / "home"
    home.mkdir()
    return Orbital(local_platform.url, home)
