"""In-memory ring buffer of recent log lines, for the admin log viewer.

Mirrors k8s/metrics.MetricsStore: no persistence, history resets with the
control plane and is bounded. Captures every logger under the root (the
reconciler and the API), not just one subsystem.
"""

import logging
from collections import deque
from threading import Lock

MAX_LINES = 2000


class RingBufferHandler(logging.Handler):
    def __init__(self, maxlen: int = MAX_LINES):
        super().__init__()
        self._lock = Lock()
        self._buf: deque[str] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        line = self.format(record)
        with self._lock:
            self._buf.append(line)

    def tail(self, n: int) -> list[str]:
        with self._lock:
            lines = list(self._buf)
        return lines[-n:] if n < len(lines) else lines


handler = RingBufferHandler()
handler.setFormatter(
    logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
)
