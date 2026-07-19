"""Read-only helpers: pod logs for apps and builds."""

import logging
from collections.abc import Iterator

from kubernetes.client import ApiException

from ..config import Settings
from . import client

log = logging.getLogger(__name__)


def _pods_for(namespace: str, selector: str):
    return client.core().list_namespaced_pod(namespace, label_selector=selector).items


def _read_log(pod: str, namespace: str, tail: int, container: str | None = None) -> str:
    # _preload_content=False + decode: the client otherwise returns a bytes repr
    resp = client.core().read_namespaced_pod_log(
        pod,
        namespace,
        tail_lines=tail,
        _preload_content=False,
        **({"container": container} if container else {}),
    )
    try:
        return resp.data.decode(errors="replace")
    finally:
        resp.release_conn()


def app_log_tail(app_id: str, settings: Settings, tail: int = 500) -> str:
    chunks = []
    for pod in _pods_for(settings.apps_namespace, f"app.streamlit-host.io/app-id={app_id}"):
        try:
            chunks.append(_read_log(pod.metadata.name, settings.apps_namespace, tail))
        except ApiException as e:
            chunks.append(f"[no logs from {pod.metadata.name}: {e.reason}]")
    return "\n".join(chunks)


def app_log_stream(app_id: str, settings: Settings, tail: int = 100) -> Iterator[bytes]:
    pods = _pods_for(settings.apps_namespace, f"app.streamlit-host.io/app-id={app_id}")
    if not pods:
        yield b"[no running pods]\n"
        return
    resp = client.core().read_namespaced_pod_log(
        pods[0].metadata.name,
        settings.apps_namespace,
        tail_lines=tail,
        follow=True,
        _preload_content=False,
    )
    try:
        yield from resp.stream()
    finally:
        resp.release_conn()


def build_log_tail(build_id: str, settings: Settings, tail: int = 200) -> str:
    """Concatenated logs of the fetch (clone+detect) and buildkit containers."""
    chunks = []
    for pod in _pods_for(
        settings.builds_namespace, f"app.streamlit-host.io/build-id={build_id}"
    ):
        for container in ("fetch", "buildkit"):
            try:
                text = _read_log(
                    pod.metadata.name, settings.builds_namespace, tail, container
                )
                chunks.append(f"--- {container} ---\n{text}")
            except ApiException as e:
                chunks.append(f"--- {container} --- [unavailable: {e.reason}]")
    return "\n".join(chunks)
