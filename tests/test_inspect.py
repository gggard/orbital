"""Pod log helpers: the exact read_namespaced_pod_log calls and raw-response handling."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from orbital.config import Settings
from orbital.k8s.inspect import app_log_stream, build_log_tail, scan_log


@pytest.fixture
def core(monkeypatch):
    from orbital.k8s import client as k8s_client

    core = MagicMock()
    core.list_namespaced_pod.return_value = SimpleNamespace(
        items=[SimpleNamespace(metadata=SimpleNamespace(name="pod-1"))]
    )
    resp = MagicMock()
    resp.data = b"hello"
    resp.stream.return_value = iter([b"a", b"b"])
    core.read_namespaced_pod_log.return_value = resp
    monkeypatch.setattr(k8s_client, "core", lambda: core)
    return core


def test_build_log_tail_reads_each_container_with_tail(core):
    settings = Settings()
    out = build_log_tail("bld1", settings, tail=50)

    assert out == "--- fetch ---\nhello\n--- buildkit ---\nhello"
    core.read_namespaced_pod_log.assert_any_call(
        "pod-1",
        settings.builds_namespace,
        container="fetch",
        tail_lines=50,
        _preload_content=False,
    )
    assert core.read_namespaced_pod_log.return_value.release_conn.call_count == 2


def test_scan_log_reads_untruncated_log_of_default_container(core):
    settings = Settings()
    assert scan_log("scn1", settings) == "hello"
    core.read_namespaced_pod_log.assert_called_once_with(
        "pod-1",
        settings.scans_namespace,
        container=None,
        tail_lines=None,
        _preload_content=False,
    )


def test_app_log_stream_yields_chunks_and_releases_connection(core):
    settings = Settings()
    assert list(app_log_stream("app1", settings, tail=10)) == [b"a", b"b"]
    core.read_namespaced_pod_log.assert_called_once_with(
        "pod-1",
        settings.apps_namespace,
        tail_lines=10,
        follow=True,
        _preload_content=False,
    )
    core.read_namespaced_pod_log.return_value.release_conn.assert_called_once()


def test_app_log_stream_without_pods(core):
    core.list_namespaced_pod.return_value = SimpleNamespace(items=[])
    assert list(app_log_stream("app1", Settings())) == [b"[no running pods]\n"]
    core.read_namespaced_pod_log.assert_not_called()
