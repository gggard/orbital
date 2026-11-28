"""Shared fixtures: an isolated config/env, a CLI runner, a scriptable fake
API (httpx.MockTransport) and a fake clock for --wait loops."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from orbital_cli import client as client_mod
from orbital_cli import wait as wait_mod
from orbital_cli.main import app as cli_app

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """No real config file, no inherited ORBITAL_*/CI variables."""
    for var in (
        "ORBITAL_URL",
        "ORBITAL_TOKEN",
        "ORBITAL_PROFILE",
        "ORBITAL_OUTPUT",
        "CI",
        "XDG_CONFIG_HOME",
        "NO_COLOR",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = tmp_path / "config" / "orbital" / "config.toml"
    monkeypatch.setenv("ORBITAL_CONFIG", str(cfg))
    return cfg


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    """--wait loops run instantly: sleeping advances a fake monotonic clock."""
    now = [0.0]
    monkeypatch.setattr(wait_mod, "monotonic", lambda: now[0])
    monkeypatch.setattr(wait_mod, "sleep", lambda s: now.__setitem__(0, now[0] + s))
    return now


class FakeApi:
    """Routes (method, path) to queued responses; the last one repeats."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], deque[Any]] = defaultdict(deque)
        self.requests: list[httpx.Request] = []

    def on(self, method: str, path: str, *responses: Any) -> FakeApi:
        """Each response is a JSON-able body, (status, body), a str (text
        body) or a callable(request) -> httpx.Response."""
        self.routes[(method, path)].extend(responses)
        return self

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        queue = self.routes.get(key)
        if not queue:
            return httpx.Response(404, json={"detail": f"no fake route for {key}"})
        item = queue.popleft() if len(queue) > 1 else queue[0]
        if callable(item):
            return item(request)
        status, body = item if isinstance(item, tuple) else (200, item)
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    def calls(self, method: str, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method and r.url.path == path]

    def body(self, method: str, path: str, index: int = -1) -> Any:
        return json.loads(self.calls(method, path)[index].content)


@pytest.fixture
def api(monkeypatch) -> FakeApi:
    fake = FakeApi()

    def factory(*, base_url: str, headers: dict[str, str], timeout: float) -> httpx.Client:
        return httpx.Client(
            base_url=base_url, headers=headers, transport=httpx.MockTransport(fake.handle)
        )

    monkeypatch.setattr(client_mod, "http_factory", factory)
    return fake


class Runner:
    def __init__(self) -> None:
        self.runner = CliRunner()

    def __call__(self, *args: str, input: str | None = None, env: dict | None = None):
        return self.runner.invoke(cli_app, list(args), input=input, env=env)


@pytest.fixture
def cli() -> Runner:
    return Runner()


def make_app(**overrides: Any) -> dict:
    app = {
        "id": "a1b2c3d4e5f6",
        "slug": "demo",
        "repo_url": "https://github.com/x/y",
        "branch": "main",
        "app_type": "streamlit",
        "main_file": "streamlit_app.py",
        "python_version": None,
        "build_command": None,
        "output_dir": ".",
        "public": True,
        "allowed_groups": [],
        "owner_groups": ["devs"],
        "tags": [],
        "state": "running",
        "pending_action": "none",
        "error": None,
        "current_build_id": "build000001",
        "latest_scan": None,
        "url": "https://demo.apps.example.com",
        "webhook_path": "/webhooks/apps/a1b2c3d4e5f6/tok",
        "hibernate_enabled": True,
        "hibernate_after_seconds": None,
        "poll_enabled": False,
        "poll_interval_seconds": None,
        "last_polled_at": None,
        "last_active_at": "2026-11-28T10:00:00Z",
        "created_at": "2026-11-28T10:00:00Z",
        "updated_at": "2026-11-28T10:00:00Z",
    }
    app.update(overrides)
    return app
