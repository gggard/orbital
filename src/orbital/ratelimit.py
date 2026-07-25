"""In-process, per-key request rate limiting (issue #82 hardening).

Several endpoints are unauthenticated by design (OIDC login/callback, the
per-app git-push webhook) and call out synchronously to an external service
(the IdP's token endpoint, oauth2-proxy). Token/state entropy already makes
brute force impractical, so this isn't an auth control - it's a lightweight
backstop against a request flood exhausting control-plane capacity or
tripping the IdP's own rate limits and locking out legitimate users.

Sliding-window counter, in-process only (a `dict[key, deque[timestamp]]`):
no Redis, no cross-process coordination. That has one consequence worth
being explicit about: with `controlPlane.replicas > 1` (only possible with a
shared Postgres `database.url`, see deploy/chart/orbital/templates/
control-plane.yaml), each replica enforces its own independent counter, so
the *effective* limit scales with replica count (e.g. 20/min/IP configured
against 3 replicas behaves like ~60/min/IP in the worst case where requests
happen to spread evenly). That's an accepted, documented limitation for a
defense-in-depth backstop (see docs/ADMIN.md) - not a reason to add a
shared-store dependency for this.
"""

import logging
import threading
import time
from collections import deque
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from .config import Settings, get_settings

log = logging.getLogger(__name__)

# Hard cap on distinct keys tracked at once (client IPs / app IDs), so a
# flood of requests using many distinct keys can't grow this store without
# bound. Evicted opportunistically when the cap is hit (see _evict_stale).
MAX_TRACKED_KEYS = 10_000


class RateLimiter:
    """Sliding-window request counter: at most `limit` hits per `window_seconds`, per key."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: float) -> bool:
        """Record a hit for `key` and report whether it's still within `limit`.

        Thread-safe: FastAPI runs sync path/dependency functions in a
        threadpool, so concurrent callers sharing a key are expected.
        """
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= MAX_TRACKED_KEYS:
                    self._evict_stale(cutoff)
                hits = deque()
                self._hits[key] = hits
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        """Clear all tracked state (used by tests to avoid cross-test interference)."""
        with self._lock:
            self._hits.clear()

    def _evict_stale(self, cutoff: float) -> None:
        """Drop keys idle since before `cutoff`. Called with `_lock` already held."""
        stale = [k for k, hits in self._hits.items() if not hits or hits[-1] < cutoff]
        for k in stale:
            del self._hits[k]
        if len(self._hits) >= MAX_TRACKED_KEYS:
            # Still at capacity (all tracked keys are recently active): drop
            # the oldest-inserted entries rather than grow unbounded. Slightly
            # unfair to whichever keys get evicted, but keeps memory bounded
            # under a sustained flood of distinct keys, which is the failure
            # mode this cap exists to prevent.
            overflow = len(self._hits) - MAX_TRACKED_KEYS + 1
            for k in list(self._hits.keys())[:overflow]:
                del self._hits[k]


WINDOW_SECONDS = 60.0

# Module-level singletons: one shared counter per limited surface, wired
# into routes as FastAPI dependencies below. Tests reset these between test
# functions (see tests/conftest.py) since they'd otherwise persist state for
# the lifetime of the process (here: the whole pytest session, as `app` is
# only imported/constructed once).
login_limiter = RateLimiter()
webhook_limiter = RateLimiter()


def _reject(scope: str, key: str, limit: int) -> None:
    log.warning(
        "rate limit exceeded for %s (key=%r, limit=%d/%ds)", scope, key, limit, int(WINDOW_SECONDS)
    )
    raise HTTPException(
        status_code=429,
        detail="rate limit exceeded, please retry later",
        headers={"Retry-After": str(int(WINDOW_SECONDS))},
    )


def rate_limit_login(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Per-client-IP limiter for `/api/auth/login` and `/api/auth/callback`.

    Keyed on the direct TCP peer (`request.client.host`), not
    `X-Forwarded-For`. `orbital.analytics.client_key` does trust XFF, but
    only as a best-effort dedup key for view analytics, where a spoofed
    value merely skews a count. A rate *limit* is a security control an
    attacker is actively trying to defeat: trusting a self-reported header
    here would let a caller paint requests under an arbitrary key (e.g.
    someone else's IP, or a rotating fake one to dodge the limit entirely),
    so this deliberately uses the raw peer instead.

    Caveat: the console sits behind an ingress/load balancer, so in
    production this is the ingress hop's address, not the browser's real
    IP - every browser client is bucketed together at ingress granularity
    rather than limited individually. That's an accepted tradeoff rather
    than a gap: it still caps total login/callback volume the control plane
    will absorb, which is the resource-exhaustion concern this exists for;
    per-real-client-IP limiting, if wanted, belongs at the ingress
    controller (which already terminates the real client connection).
    """
    key = request.client.host if request.client else "unknown"
    if not login_limiter.check(key, settings.login_rate_limit_per_minute, WINDOW_SECONDS):
        _reject("login", key, settings.login_rate_limit_per_minute)


def rate_limit_webhook(
    app_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Per-`app_id` limiter for the git-push webhook.

    Keyed by `app_id` rather than by IP: legitimate senders (GitHub/GitLab/
    Gitea) call from shared, documented IP ranges, so an IP-keyed limit
    would either be too loose (many apps' webhook traffic sharing one
    bucket) or collateral-damage every other app hosted behind the same
    provider once one app's webhook gets hammered.
    """
    if not webhook_limiter.check(app_id, settings.webhook_rate_limit_per_minute, WINDOW_SECONDS):
        _reject("webhook", app_id, settings.webhook_rate_limit_per_minute)
