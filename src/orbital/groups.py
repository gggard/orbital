"""Known-groups directory backing the console's group pickers.

Merged from three sources, deduplicated and sorted:

- the role configuration (admin/creator/viewer/public-sharing groups),
- the static ``ORBITAL_KNOWN_GROUPS`` list,
- optionally the Keycloak realm's groups (``ORBITAL_GROUPS_FROM_KEYCLOAK``),
  fetched from the admin REST API with the OIDC client's service account
  (requires the ``query-groups`` + ``view-users`` roles from the realm's
  ``realm-management`` client).

The Keycloak lookup is cached briefly and fails soft: on any error the
directory simply falls back to the configured lists.
"""

import logging
import threading
import time

import httpx

from .config import Settings

log = logging.getLogger(__name__)

_CACHE_TTL = 60.0
_cache_lock = threading.Lock()
_cache: tuple[float, list[str]] | None = None


def _flatten(groups: list[dict]) -> list[str]:
    """Group names from a Keycloak group tree (subgroups included)."""
    names: list[str] = []
    for g in groups:
        if isinstance(g.get("name"), str):
            names.append(g["name"])
        names.extend(_flatten(g.get("subGroups") or []))
    return names


def _fetch_keycloak_groups(settings: Settings) -> list[str]:
    issuer = settings.oidc_issuer_url.rstrip("/")
    server, sep, realm = issuer.rpartition("/realms/")
    if not sep:
        raise ValueError(f"issuer URL {issuer!r} has no /realms/<realm> part")
    token_resp = httpx.post(
        f"{issuer}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
        },
        timeout=10,
    )
    token_resp.raise_for_status()
    groups_resp = httpx.get(
        f"{server}/admin/realms/{realm}/groups",
        params={"briefRepresentation": "true", "max": 1000},
        headers={"Authorization": f"Bearer {token_resp.json()['access_token']}"},
        timeout=10,
    )
    groups_resp.raise_for_status()
    return _flatten(groups_resp.json())


def _keycloak_groups_cached(settings: Settings) -> list[str]:
    global _cache
    with _cache_lock:
        if _cache is not None and time.time() - _cache[0] < _CACHE_TTL:
            return _cache[1]
    try:
        names = _fetch_keycloak_groups(settings)
    except (httpx.HTTPError, ValueError, KeyError) as e:
        log.warning("keycloak group lookup failed (using configured lists only): %s", e)
        names = []
    with _cache_lock:
        _cache = (time.time(), names)
    return names


def clear_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def known_groups(settings: Settings) -> list[str]:
    names = {
        *settings.known_groups,
        *settings.admin_groups,
        *settings.creator_groups,
        *settings.viewer_groups,
        *settings.public_sharing_groups,
    }
    if settings.groups_from_keycloak:
        names |= set(_keycloak_groups_cached(settings))
    return sorted(names)
