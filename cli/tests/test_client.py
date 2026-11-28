import httpx
import pytest

from orbital_cli import __version__
from orbital_cli import client as client_mod
from orbital_cli.client import Client
from orbital_cli.errors import CliError, ExitCode


def test_sends_token_and_user_agent(api):
    api.on("GET", "/api/v1/apps", [])
    Client("http://x", "orbpat_secret").get("/apps")
    req = api.requests[0]
    assert req.headers["Authorization"] == "Bearer orbpat_secret"
    assert req.headers["User-Agent"] == f"orbital-cli/{__version__}"


def test_no_auth_header_without_token(api):
    api.on("GET", "/healthz", {"status": "ok"})
    Client("http://x", None).get("/healthz")
    assert "Authorization" not in api.requests[0].headers
    assert api.requests[0].url.path == "/healthz"  # not prefixed with /api/v1


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, ExitCode.VALIDATION),
        (401, ExitCode.AUTH),
        (403, ExitCode.AUTH),
        (404, ExitCode.NOT_FOUND),
        (409, ExitCode.CONFLICT),
        (422, ExitCode.VALIDATION),
        (500, ExitCode.ERROR),
        (502, ExitCode.ERROR),
    ],
)
def test_status_to_exit_code(api, status, code):
    api.on("GET", "/api/v1/apps", (status, {"detail": "nope"}))
    with pytest.raises(CliError) as e:
        Client("http://x", None).get("/apps")
    assert e.value.code == code
    assert e.value.http_status == status
    assert "nope" in e.value.message


def test_validation_detail_is_flattened(api):
    detail = [{"loc": ["body", "slug"], "msg": "bad slug"}, {"loc": ["body"], "msg": "other"}]
    api.on("POST", "/api/v1/apps", (422, {"detail": detail}))
    with pytest.raises(CliError) as e:
        Client("http://x", None).post("/apps", json={})
    assert e.value.message == "slug: bad slug; other"


def test_non_json_error_body(api):
    api.on("GET", "/api/v1/apps", (502, "Bad Gateway from proxy"))
    with pytest.raises(CliError) as e:
        Client("http://x", None).get("/apps")
    assert e.value.message == "Bad Gateway from proxy"


def test_401_hints_at_login(api):
    api.on("GET", "/api/v1/me", (401, {"detail": "invalid token"}))
    with pytest.raises(CliError) as e:
        Client("http://x", "bad").get("/me")
    assert "orbital login" in e.value.message


def test_network_errors(monkeypatch):
    def factory(**kw):
        def boom(request):
            raise httpx.ConnectError("refused")

        return httpx.Client(transport=httpx.MockTransport(boom), base_url=kw["base_url"])

    monkeypatch.setattr(client_mod, "http_factory", factory)
    with pytest.raises(CliError) as e:
        Client("http://x", None).get("/apps")
    assert e.value.code == ExitCode.ERROR
    assert "cannot reach http://x" in e.value.message


def test_verbose_logs_requests_without_token(api, capsys):
    api.on("GET", "/api/v1/apps", [])
    Client("http://x", "orbpat_secret", verbose=True).get("/apps")
    err = capsys.readouterr().err
    assert "GET http://x/api/v1/apps -> 200" in err
    assert "orbpat_secret" not in err


def test_stream_text(api):
    api.on("GET", "/api/v1/apps/a/logs", "line1\nline2\n")
    chunks = list(Client("http://x", None).stream_text("/apps/a/logs", follow="true"))
    assert "".join(chunks) == "line1\nline2\n"
    assert api.requests[0].url.params["follow"] == "true"


def test_stream_text_error(api):
    api.on("GET", "/api/v1/apps/a/logs", (404, {"detail": "app not found"}))
    with pytest.raises(CliError) as e:
        list(Client("http://x", None).stream_text("/apps/a/logs"))
    assert e.value.code == ExitCode.NOT_FOUND
