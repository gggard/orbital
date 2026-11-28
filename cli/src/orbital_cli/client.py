"""Thin HTTP client over the control-plane REST API.

Every non-2xx response becomes a CliError carrying the exit code that
matches its status (see errors.py), with the server's `detail` message.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from . import __version__
from .errors import CliError, ExitCode, code_for_status

API_PREFIX = "/api/v1"
DEFAULT_TIMEOUT = 30.0

HttpFactory = Callable[..., httpx.Client]


def default_http_factory(*, base_url: str, headers: dict[str, str], timeout: float) -> httpx.Client:
    return httpx.Client(base_url=base_url, headers=headers, timeout=timeout)


# Swapped out by tests to point the CLI at an in-process control plane.
http_factory: HttpFactory = default_http_factory


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    detail = body.get("detail", body) if isinstance(body, dict) else body
    if isinstance(detail, list):  # FastAPI/pydantic validation errors
        parts = []
        for err in detail:
            if isinstance(err, dict):
                loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
                parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
            else:
                parts.append(str(err))
        return "; ".join(parts)
    return str(detail)


class Client:
    def __init__(self, base_url: str, token: str | None, *, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.verbose = verbose
        headers = {"User-Agent": f"orbital-cli/{__version__}", "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = http_factory(base_url=self.base_url, headers=headers, timeout=DEFAULT_TIMEOUT)

    def close(self) -> None:
        self._http.close()

    # -- core ----------------------------------------------------------------

    def _url(self, path: str) -> str:
        return path if path.startswith(("/healthz", "/api/")) else API_PREFIX + path

    def _log(self, method: str, url: str, status: int | None = None) -> None:
        if self.verbose:
            suffix = f" -> {status}" if status is not None else ""
            # the Authorization header is never printed
            print(f"> {method} {self.base_url}{url}{suffix}", file=sys.stderr)

    def _check(self, response: httpx.Response) -> httpx.Response:
        if response.is_success:
            return response
        status = response.status_code
        message = _detail(response)
        if status == 401:
            message = f"not authenticated ({message}); set ORBITAL_TOKEN or run `orbital login`"
        elif status == 403:
            message = f"permission denied: {message}"
        raise CliError(message, code_for_status(status), http_status=status)

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        url = self._url(path)
        kwargs: dict[str, Any] = {"json": json, "params": params}
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            response = self._http.request(method, url, **kwargs)
        except httpx.TimeoutException as e:
            raise CliError(f"request to {self.base_url} timed out: {e}", ExitCode.ERROR) from e
        except httpx.TransportError as e:
            raise CliError(f"cannot reach {self.base_url}: {e}", ExitCode.ERROR) from e
        self._log(method, url, response.status_code)
        return self._check(response)

    def get(self, path: str, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        return self.request("GET", path, params=clean or None).json()

    def get_text(self, path: str, **params: Any) -> str:
        clean = {k: v for k, v in params.items() if v is not None}
        return self.request("GET", path, params=clean or None).text

    def post(self, path: str, json: Any = None) -> Any:
        return self.request("POST", path, json=json).json()

    def patch(self, path: str, json: Any) -> Any:
        return self.request("PATCH", path, json=json).json()

    def put(self, path: str, json: Any) -> Any:
        return self.request("PUT", path, json=json).json()

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path).json()

    def stream_text(self, path: str, **params: Any) -> Iterator[str]:
        """Yield decoded text chunks of a streaming (chunked) response."""
        url = self._url(path)
        clean = {k: v for k, v in params.items() if v is not None}
        try:
            with self._http.stream("GET", url, params=clean, timeout=None) as response:
                self._log("GET", url, response.status_code)
                if not response.is_success:
                    response.read()
                    self._check(response)
                yield from response.iter_text()
        except httpx.TransportError as e:
            raise CliError(f"connection to {self.base_url} lost: {e}", ExitCode.ERROR) from e
