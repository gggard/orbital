from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform configuration. All values overridable via SH_* env vars."""

    model_config = SettingsConfigDict(env_prefix="SH_", env_file=".env")

    database_url: str = "sqlite:///./streamlit_host.db"

    # Kubernetes
    kube_context: str | None = None  # None -> default context / in-cluster
    apps_namespace: str = "streamlit-apps"
    builds_namespace: str = "streamlit-builds"

    # Registry: builds push to push_url (in-cluster DNS), nodes pull via pull_prefix.
    # Defaults match the minikube "registry" addon.
    registry_push_url: str = "registry.kube-system.svc.cluster.local:80"
    registry_pull_prefix: str = "localhost:5000"

    # Base images per supported Python version, as repo:tag inside the registry.
    python_versions: dict[str, str] = {"3.12": "streamlit-base:py3.12"}
    default_python_version: str = "3.12"

    # Routing
    # "subdomain": apps at <slug>.<apps_domain> (needs wildcard DNS)
    # "path":      apps at <apps_domain><apps_path_prefix>/<slug> (single host)
    routing_mode: str = "subdomain"
    apps_domain: str = "apps.local"
    apps_path_prefix: str = "/app"  # only used in path mode
    apps_url_port: int = 80  # port shown in app URLs (e.g. a forwarded tunnel port)
    ingress_class: str = "nginx"

    # Auth (SPEC §4.6/§5.5): oauth2-proxy + OIDC IdP fronting private apps.
    auth_enabled: bool = False
    # /oauth2/auth endpoint of oauth2-proxy, reachable from the control plane
    oauth2_proxy_auth_url: str = ""
    # base URL of this control plane, reachable from the ingress controller
    authz_base_url: str = ""

    # Management RBAC (group-based). Roles resolved from OIDC group claims:
    # admin > creator > viewer; users in none of these groups cannot log in.
    ui_auth_enabled: bool = False
    admin_groups: list[str] = ["admins"]
    creator_groups: list[str] = []
    viewer_groups: list[str] = []
    # Restrict who may make apps PUBLIC (anyone-with-the-URL). Empty = any
    # user who can manage the app; non-empty = only members of these groups
    # (admins always may).
    public_sharing_groups: list[str] = []
    # Group directory offered by the console's group pickers (viewer access,
    # ownership). Always includes the role-config groups above; extend with a
    # static list and/or a live lookup of the Keycloak realm's groups (admin
    # REST API via the OIDC client's service account — see docs/ADMIN.md).
    known_groups: list[str] = []
    groups_from_keycloak: bool = False
    oidc_issuer_url: str = ""  # e.g. http://keycloak.<domain>:<port>/realms/streamlit
    oidc_client_id: str = "streamlit-host"
    oidc_client_secret: str = ""
    ui_base_url: str = "http://localhost:3000"  # browser-facing console URL
    session_secret: str = "dev-session-secret-change-me"

    # Build
    # Rootless BuildKit is the default (SPEC §5.2); some environments (nested
    # containers/LXC without user-namespace support) need privileged builds.
    buildkit_rootless: bool = True
    buildkit_image: str = ""  # empty -> auto based on buildkit_rootless
    git_image: str = "alpine/git:latest"
    build_ttl_seconds: int = 3600
    build_timeout_seconds: int = 900

    # App runtime defaults
    app_cpu_request: str = "250m"
    app_cpu_limit: str = "1"
    app_mem_request: str = "512Mi"
    app_mem_limit: str = "2Gi"
    app_port: int = 8501

    # Reconciler
    reconciler_enabled: bool = True
    reconcile_interval: float = 3.0

    # Git polling fallback (SPEC §4.2/FR-2.2): per-app opt-in, for git hosts
    # that can't deliver a push webhook into the cluster. Per-app override
    # lives on App.poll_interval_seconds.
    git_poll_default_interval_seconds: int = 600  # 10 min
    # Platform floor: no app (regardless of per-app override) may poll more
    # often than this, to keep git ls-remote traffic against developers' git
    # hosts bounded.
    git_poll_min_interval_seconds: int = 60  # 1 min

    # Hibernation (SPEC §4.8/§5.6): platform default idle timeout before an
    # app is scaled to zero; per-app override lives on App.hibernate_after_seconds.
    hibernation_enabled: bool = True
    hibernation_timeout_seconds: int = 12 * 3600  # SCC: 12h
    # Platform ceiling: no app (regardless of per-app override) may stay
    # active longer than this while idle, so operators can guarantee
    # resources are eventually reclaimed.
    hibernation_max_timeout_seconds: int = 7 * 24 * 3600  # 7 days
    # the control plane's own in-cluster Service (doubles as the wake proxy
    # and the authz backend); reachable from the ingress controller
    control_plane_service_host: str = (
        "streamlit-host-control-plane.streamlit-platform.svc.cluster.local"
    )
    control_plane_service_port: int = 8000

    def resolved_buildkit_image(self) -> str:
        if self.buildkit_image:
            return self.buildkit_image
        return "moby/buildkit:rootless" if self.buildkit_rootless else "moby/buildkit:latest"

    def base_image_for(self, python_version: str) -> str:
        """Base image reference as resolvable from inside the cluster (push URL)."""
        return f"{self.registry_push_url}/{self.python_versions[python_version]}"

    def app_image(self, app_id: str, build_id: str, *, pull: bool) -> str:
        prefix = self.registry_pull_prefix if pull else self.registry_push_url
        return f"{prefix}/apps/{app_id}:{build_id}"

    def url_port_suffix(self) -> str:
        return "" if self.apps_url_port == 80 else f":{self.apps_url_port}"

    def base_url_path(self, slug: str) -> str:
        """Streamlit server.baseUrlPath for an app ("" in subdomain mode)."""
        if self.routing_mode != "path":
            return ""
        return f"{self.apps_path_prefix.rstrip('/')}/{slug}"

    def app_url(self, slug: str) -> str:
        port = self.url_port_suffix()
        if self.routing_mode == "path":
            return f"http://{self.apps_domain}{port}{self.base_url_path(slug)}/"
        return f"http://{slug}.{self.apps_domain}{port}"

    def auth_signin_url(self) -> str:
        """Browser-facing oauth2-proxy sign-in URL (auth.<apps_domain>)."""
        return f"http://auth.{self.apps_domain}{self.url_port_suffix()}/oauth2/start"

    def internal_base_url(self) -> str:
        """Control plane URL as reachable from the ingress controller."""
        return f"http://{self.control_plane_service_host}:{self.control_plane_service_port}"

    @model_validator(mode="after")
    def _validate_poll_and_hibernation_bounds(self) -> "Settings":
        if self.git_poll_min_interval_seconds > self.git_poll_default_interval_seconds:
            raise ValueError(
                "SH_GIT_POLL_MIN_INTERVAL_SECONDS "
                f"({self.git_poll_min_interval_seconds}) must be <= "
                f"SH_GIT_POLL_DEFAULT_INTERVAL_SECONDS ({self.git_poll_default_interval_seconds})"
            )
        if self.hibernation_max_timeout_seconds < self.hibernation_timeout_seconds:
            raise ValueError(
                "SH_HIBERNATION_MAX_TIMEOUT_SECONDS "
                f"({self.hibernation_max_timeout_seconds}) must be >= "
                f"SH_HIBERNATION_TIMEOUT_SECONDS ({self.hibernation_timeout_seconds})"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
