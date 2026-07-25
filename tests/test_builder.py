"""build_job() manifest generation for both app types."""

from orbital.config import Settings
from orbital.k8s import scripts
from orbital.k8s.builder import REGISTRY_CA_CERT_PATH, build_job, build_support_configmap
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
        e["name"]: e["value"] for e in job["spec"]["template"]["spec"]["initContainers"][0]["env"]
    }
    assert init_env["BASE_IMAGE"] == f"{settings.registry_push_url}/streamlit-base:py3.12"
    assert init_env["APP_TYPE"] == "streamlit"
    assert init_env["MAIN_FILE"] == "app.py"


def test_build_job_static_uses_static_base_image_and_skips_python_version():
    settings = Settings()
    job = build_job(_app(AppType.static), _build(), settings)

    init_env = {
        e["name"]: e["value"] for e in job["spec"]["template"]["spec"]["initContainers"][0]["env"]
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


def _buildkit_container(job: dict) -> dict:
    return job["spec"]["template"]["spec"]["containers"][0]


def _buildkit_env(job: dict) -> dict:
    return {e["name"]: e.get("value") for e in _buildkit_container(job)["env"]}


# --- scripts.buildkitd_toml() -----------------------------------------------


def test_buildkitd_toml_plaintext_by_default():
    assert scripts.buildkitd_toml("registry.local:80") == (
        '[registry."registry.local:80"]\n  http = true\n'
    )


def test_buildkitd_toml_tls_emits_ca_cert_form():
    assert scripts.buildkitd_toml("registry.local:443", ca_cert_path="/etc/certs/ca.crt") == (
        '[registry."registry.local:443"]\n  ca=["/etc/certs/ca.crt"]\n'
    )


# --- build_support_configmap() ----------------------------------------------


def test_build_support_configmap_default_matches_pre_tls_behavior():
    settings = Settings()
    cm = build_support_configmap(settings)

    assert cm["data"]["buildkitd.toml"] == scripts.buildkitd_toml(settings.registry_push_url)
    assert "registry-ca.crt" not in cm["data"]


def test_build_support_configmap_tls_enabled_includes_ca_cert():
    ca_pem = "-----BEGIN CERTIFICATE-----\n..."
    settings = Settings(registry_tls_enabled=True, registry_ca_cert=ca_pem)
    cm = build_support_configmap(settings)

    assert cm["data"]["registry-ca.crt"] == settings.registry_ca_cert
    assert f'ca=["{REGISTRY_CA_CERT_PATH}"]' in cm["data"]["buildkitd.toml"]
    assert "http = true" not in cm["data"]["buildkitd.toml"]


def test_build_support_configmap_tls_enabled_without_ca_cert_omits_key():
    # registry_tls_enabled without a cert yet provisioned: buildkitd.toml
    # still points at the fixed CA path (misconfiguration surfaces as a
    # build failure rather than silently falling back to plaintext), but
    # there's no PEM to write into the ConfigMap.
    settings = Settings(registry_tls_enabled=True, registry_ca_cert="")
    cm = build_support_configmap(settings)

    assert "registry-ca.crt" not in cm["data"]
    assert f'ca=["{REGISTRY_CA_CERT_PATH}"]' in cm["data"]["buildkitd.toml"]


# --- build_job() registry TLS wiring ----------------------------------------


def test_build_job_registry_tls_disabled_matches_byte_for_byte_prior_behavior():
    settings = Settings()
    job = build_job(_app(), _build(), settings)

    env = _buildkit_env(job)
    assert env["REGISTRY_INSECURE"] == "true"
    mounts = _buildkit_container(job)["volumeMounts"]
    assert mounts == [
        {"name": "workspace", "mountPath": "/workspace"},
        {"name": "scripts", "mountPath": "/scripts"},
        {
            "name": "scripts",
            "mountPath": "/home/user/.config/buildkit/buildkitd.toml",
            "subPath": "buildkitd.toml",
        },
        {"name": "buildkit-state", "mountPath": "/home/user/.local/share/buildkit"},
    ]
    assert not any(m.get("subPath") == "registry-ca.crt" for m in mounts)


def test_build_job_registry_tls_enabled_sets_insecure_false_and_mounts_ca():
    settings = Settings(registry_tls_enabled=True, registry_ca_cert="fake-pem")
    job = build_job(_app(), _build(), settings)

    env = _buildkit_env(job)
    assert env["REGISTRY_INSECURE"] == "false"

    mounts = _buildkit_container(job)["volumeMounts"]
    ca_mounts = [m for m in mounts if m.get("subPath") == "registry-ca.crt"]
    assert len(ca_mounts) == 1
    assert ca_mounts[0]["name"] == "scripts"
    assert ca_mounts[0]["mountPath"] == REGISTRY_CA_CERT_PATH
