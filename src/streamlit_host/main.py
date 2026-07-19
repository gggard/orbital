import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .api import apps, auth, authz, wake, webhooks
from .api.wake import hibernation_middleware
from .config import get_settings
from .db import init_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()
    settings = get_settings()
    if settings.reconciler_enabled:
        from .k8s.reconciler import start_reconciler, stop_reconciler

        start_reconciler()
        yield
        stop_reconciler()
    else:
        yield


app = FastAPI(title="streamlit-host", version=__version__, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().session_secret,
    same_site="lax",
    max_age=12 * 3600,
)
# intercepts requests to hosts/paths that resolve to a sleeping app (traffic
# reaching this process for an app host only happens while it's sleeping,
# since the ingress otherwise points straight at the app's own Service)
app.middleware("http")(hibernation_middleware)
app.include_router(apps.router)
app.include_router(auth.router)
app.include_router(authz.router)
app.include_router(wake.router)
app.include_router(webhooks.router)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"apps_domain": settings.apps_domain, "python_versions": sorted(settings.python_versions)},
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": __version__}
