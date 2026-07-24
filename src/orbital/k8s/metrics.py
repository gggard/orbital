"""Per-app CPU/memory metrics from the Kubernetes metrics-server (SPEC FR-5.6).

The reconciler samples pod metrics for running apps into an in-memory ring
buffer; the API serves the buffered series. No persistence: history resets
with the control plane and is bounded per app.
"""

import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from kubernetes import client as k8s_client
from kubernetes.client import ApiException

from ..config import Settings
from . import client

log = logging.getLogger(__name__)

# ring buffer: ~30 min of history at one sample every 15 s
SAMPLE_INTERVAL = 15.0
MAX_SAMPLES = 120

_SUFFIXES = {
    "n": 1e-9, "u": 1e-6, "m": 1e-3,
    "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "P": 1e15, "E": 1e18,
    "Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40, "Pi": 2**50, "Ei": 2**60,
}
_QUANTITY_RE = re.compile(r"^(-?[0-9.]+)([a-zA-Z]*)$")


def parse_quantity(q: str | int | float) -> float:
    """Parse a Kubernetes resource quantity ("250m", "12345678n", "2Gi") to a float.

    CPU quantities come out in cores, memory quantities in bytes.
    """
    if isinstance(q, (int, float)):
        return float(q)
    m = _QUANTITY_RE.match(q.strip())
    if not m:
        raise ValueError(f"invalid quantity {q!r}")
    value, suffix = m.groups()
    if suffix and suffix not in _SUFFIXES:
        raise ValueError(f"invalid quantity suffix {suffix!r} in {q!r}")
    return float(value) * (_SUFFIXES[suffix] if suffix else 1.0)


@dataclass(frozen=True)
class Sample:
    ts: float  # unix seconds
    cpu: float  # cores
    mem: float  # bytes


def fetch_app_usage(app_id: str, settings: Settings) -> Sample | None:
    """Current CPU/memory of an app, summed over its pods and containers.

    Returns None when metrics are unavailable (metrics-server missing or not
    ready, or no pods reporting yet).
    """
    api = k8s_client.CustomObjectsApi(client.api())
    try:
        result = api.list_namespaced_custom_object(
            "metrics.k8s.io", "v1beta1", settings.apps_namespace, "pods",
            label_selector=f"app.orbital.io/app-id={app_id}",
        )
    except ApiException as e:
        # 404/503: metrics.k8s.io not served (metrics-server absent/unready)
        log.debug("pod metrics unavailable for %s: %s", app_id, e.status)
        return None
    items = result.get("items", [])
    if not items:
        return None
    cpu = mem = 0.0
    for pod in items:
        for c in pod.get("containers", []):
            usage = c.get("usage", {})
            cpu += parse_quantity(usage.get("cpu", "0"))
            mem += parse_quantity(usage.get("memory", "0"))
    return Sample(ts=time.time(), cpu=cpu, mem=mem)


class MetricsStore:
    """Thread-safe per-app ring buffer of usage samples."""

    def __init__(self, maxlen: int = MAX_SAMPLES):
        self._maxlen = maxlen
        self._lock = threading.Lock()
        self._series: dict[str, deque[Sample]] = {}

    def add(self, app_id: str, sample: Sample) -> None:
        with self._lock:
            self._series.setdefault(app_id, deque(maxlen=self._maxlen)).append(sample)

    def series(self, app_id: str) -> list[Sample]:
        with self._lock:
            return list(self._series.get(app_id, ()))

    def latest(self, app_id: str) -> Sample | None:
        with self._lock:
            series = self._series.get(app_id)
            return series[-1] if series else None

    def drop(self, app_id: str) -> None:
        with self._lock:
            self._series.pop(app_id, None)


store = MetricsStore()


@dataclass(frozen=True)
class RestartInfo:
    count: int  # total container restarts across the app's pods
    last_reason: str | None  # e.g. "Error", "OOMKilled" (from the container's last termination)
    last_at: datetime | None  # when that last termination happened; None if never restarted


def fetch_pod_restarts(app_id: str, settings: Settings) -> RestartInfo | None:
    """Restart count, date and reason across an app's pods (SPEC FR-5.6 companion stat).

    Sourced from the Core API (pod status), not the metrics-server, so it's
    available even in clusters where metrics-server isn't installed. Returns
    None when the app has no pods yet.
    """
    pods = client.core().list_namespaced_pod(
        settings.apps_namespace,
        label_selector=f"app.orbital.io/app-id={app_id}",
    ).items
    if not pods:
        return None
    count = 0
    last_reason: str | None = None
    last_at: datetime | None = None
    for pod in pods:
        for cs in pod.status.container_statuses or []:
            count += cs.restart_count
            terminated = cs.last_state.terminated if cs.last_state else None
            if terminated and terminated.finished_at:
                if last_at is None or terminated.finished_at > last_at:
                    last_at = terminated.finished_at
                    last_reason = terminated.reason
    return RestartInfo(count=count, last_reason=last_reason, last_at=last_at)


class RestartCounts:
    """Thread-safe latest known restart info per app (a point-in-time fact,
    not a series - no ring buffer needed)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._info: dict[str, RestartInfo] = {}

    def set(self, app_id: str, info: RestartInfo) -> None:
        with self._lock:
            self._info[app_id] = info

    def get(self, app_id: str) -> RestartInfo | None:
        with self._lock:
            return self._info.get(app_id)

    def drop(self, app_id: str) -> None:
        with self._lock:
            self._info.pop(app_id, None)


restart_counts = RestartCounts()
