"""build_job() manifest generation for both app types."""

from orbital.config import Settings
from orbital.k8s.builder import build_job
from orbital.models import App, AppType, Build


def _app(app_type=AppType.streamlit, **overrides) -> App:
    defaults = {
        "id": "abc123def456",
        "slug": "demo",
        "repo_url": "https://github.com/x/y",
        "branch": "main",
        "app_type": app_type,
        "owner_groups": [],
        "allowed_groups": [],
    }
    if app_type == AppType.streamlit:
        defaults["main_file"] = "app.py"
        defaults["python_version"] = "3.12"
    else:
        defaults["build_command"] = "npm run build"
        defaults["output_dir"] = "dist"
    defaults.update(overrides)
    return App(**defaults)


def _build() -> Build:
    return Build(id="bld000000001", app_id="abc123def456", commit_sha="aaa111")


def test_build_job_streamlit_uses_python_version_base_image():
    settings = Settings()
    job = build_job(_app(), _build(), settings)

    assert job["kind"] == "Job"
    assert job["metadata"]["name"] == "build-bld000000001"
    assert job["metadata"]["namespace"] == settings.builds_namespace

    init_env = {
        e["name"]: e["value"]
        for e in job["spec"]["template"]["spec"]["initContainers"][0]["env"]
    }
    assert init_env["BASE_IMAGE"] == f"{settings.registry_push_url}/streamlit-base:py3.12"
    assert init_env["APP_TYPE"] == "streamlit"
    assert init_env["MAIN_FILE"] == "app.py"


def test_build_job_static_uses_static_base_image_and_skips_python_version():
    settings = Settings()
    job = build_job(_app(AppType.static), _build(), settings)

    init_env = {
        e["name"]: e["value"]
        for e in job["spec"]["template"]["spec"]["initContainers"][0]["env"]
    }
    assert init_env["BASE_IMAGE"] == f"{settings.registry_push_url}/{settings.static_base_image}"
    assert init_env["APP_TYPE"] == "static"
    assert init_env["BUILD_COMMAND"] == "npm run build"
    assert init_env["OUTPUT_DIR"] == "dist"


def test_build_job_buildkit_rootless_vs_privileged():
    rootless = build_job(_app(), _build(), Settings(buildkit_rootless=True))
    privileged = build_job(_app(), _build(), Settings(buildkit_rootless=False))

    rootless_ctx = rootless["spec"]["template"]["spec"]["containers"][0]["securityContext"]
    privileged_ctx = privileged["spec"]["template"]["spec"]["containers"][0]["securityContext"]
    assert rootless_ctx == {
        "seccompProfile": {"type": "Unconfined"},
        "runAsUser": 1000,
        "runAsGroup": 1000,
    }
    assert privileged_ctx == {"privileged": True}
