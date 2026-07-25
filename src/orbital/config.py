import logging
from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

# Placeholder only safe when ui_auth_enabled=False (local dev without auth).
# Named so the default and the startup check below can't drift apart.
INSECURE_DEFAULT_SESSION_SECRET = "dev-session-secret-change-me"
MIN_SESSION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Platform configuration. All values overridable via ORBITAL_* env vars."""

    model_config = SettingsConfigDict(env_prefix="ORBITAL_", env_file=".env")

    database_url: str = "sqlite:///./orbital.db"

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

    # Base image for static-site apps, as repo:tag inside the registry.
    static_base_image: str = "static-base:latest"

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
    oidc_client_id: str = "orbital"
    oidc_client_secret: str = ""
    ui_base_url: str = "http://localhost:3000"  # browser-facing console URL
    # Signs the console session cookie (holds the caller's identity/role).
    # The insecure default below is only tolerated when ui_auth_enabled=False;
    # see _validate_session_secret.
    session_secret: str = INSECURE_DEFAULT_SESSION_SECRET
    # Marks the session cookie Secure (browser withholds it over plain HTTP).
    # Secure-by-default; disable only for the plain-HTTP local/minikube dev
    # flow (docs/DEVELOPMENT.md), where the console isn't served over TLS.
    session_cookie_secure: bool = True

    # Encrypts App.secrets_toml at rest (issue #73): 32-byte, base64-encoded
    # Fernet key, sourced from a k8s Secret (see docs/ADMIN.md). No default -
    # the app refuses to start without one (see _validate_secrets_encryption_key).
    secrets_encryption_key: str = ""

    # Personal API tokens (SPEC: "dashboard session or personal API token").
    # No separate default is needed beyond this: a token with no explicit
    # ttl_days gets this value, so it's both the default and the ceiling.
    api_token_max_ttl_days: int = 90

    # Rate limiting (issue #82): in-process, per-key request throttling on
    # unauthenticated hot paths, as a defense-in-depth backstop against
    # resource exhaustion / IdP rate-limit amplification - not an auth
    # control (see orbital.ratelimit for the multi-replica caveat).
    login_rate_limit_per_minute: int = 20  # /api/auth/login + /api/auth/callback, per client IP
    # /webhooks/apps/{app_id}/*, per app_id. Legitimate traffic is one push
    # event at a time (rarely more than a couple in quick succession from a
    # force-push/rebase), so this can stay tight; see docs/ADMIN.md.
    webhook_rate_limit_per_minute: int = 5

    # Build
    # Rootless BuildKit is the default (SPEC §5.2); some environments (nested
    # containers/LXC without user-namespace support) need privileged builds.
    # SECURITY: build Jobs run untrusted, user-supplied repository content
    # (arbitrary Dockerfile.orbital / RUN steps from an app owner's own
    # repo). Setting this False switches the build container's
    # securityContext to privileged=true (see k8s/builder.py), one of the
    # most direct paths to node/host compromise in Kubernetes - see
    # warn_if_privileged_builds() below and docs/ADMIN.md. Only disable
    # where rootless BuildKit is confirmed unsupported.
    buildkit_rootless: bool = True
    buildkit_image: str = ""  # empty -> auto based on buildkit_rootless
    git_image: str = "alpine/git:latest"
    build_ttl_seconds: int = 3600
    build_timeout_seconds: int = 900

    # Vulnerability scanning: periodic Trivy image scans of deployed apps.
    scan_enabled: bool = True
    scans_namespace: str = "streamlit-scans"
    trivy_image: str = "aquasec/trivy:0.56.2"
    # How often a given image gets re-scanned once it has a completed scan.
    scan_interval_seconds: int = 24 * 3600
    scan_timeout_seconds: int = 600
    scan_ttl_seconds: int = 3600
    # How many completed ScanResults to retain per app; older ones (and
    # their vulnerabilities) are pruned during the periodic sweep.
    scan_retention_per_app: int = 10

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
    hibernation_timeout_seconds: int = 12 * 3600  # 12h default idle timeout
    # Platform ceiling: no app (regardless of per-app override) may stay
    # active longer than this while idle, so operators can guarantee
    # resources are eventually reclaimed.
    hibernation_max_timeout_seconds: int = 7 * 24 * 3600  # 7 days
    # the control plane's own in-cluster Service (doubles as the wake proxy
    # and the authz backend); reachable from the ingress controller
    control_plane_service_host: str = "orbital-control-plane.orbital-platform.svc.cluster.local"
    control_plane_service_port: int = 8000

    def resolved_buildkit_image(self) -> str:
        if self.buildkit_image:
            return self.buildkit_image
        return "moby/buildkit:rootless" if self.buildkit_rootless else "moby/buildkit:latest"

    def base_image_for(self, python_version: str) -> str:
        """Base image reference as resolvable from inside the cluster (push URL)."""
        return f"{self.registry_push_url}/{self.python_versions[python_version]}"

    def static_base_image_ref(self) -> str:
        """Static-site base image reference as resolvable from inside the cluster."""
        return f"{self.registry_push_url}/{self.static_base_image}"

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
                "ORBITAL_GIT_POLL_MIN_INTERVAL_SECONDS "
                f"({self.git_poll_min_interval_seconds}) must be <= "
                "ORBITAL_GIT_POLL_DEFAULT_INTERVAL_SECONDS "
                f"({self.git_poll_default_interval_seconds})"
            )
        if self.hibernation_max_timeout_seconds < self.hibernation_timeout_seconds:
            raise ValueError(
                "ORBITAL_HIBERNATION_MAX_TIMEOUT_SECONDS "
                f"({self.hibernation_max_timeout_seconds}) must be >= "
                f"ORBITAL_HIBERNATION_TIMEOUT_SECONDS ({self.hibernation_timeout_seconds})"
            )
        return self

    @model_validator(mode="after")
    def _validate_secrets_encryption_key(self) -> "Settings":
        if not self.secrets_encryption_key:
            raise ValueError(
                "ORBITAL_SECRETS_ENCRYPTION_KEY must be set to a 32-byte, "
                "base64-encoded key (encrypts App.secrets_toml at rest). Generate "
                'one with: python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            )
        try:
            Fernet(self.secrets_encryption_key)
        except Exception as e:
            raise ValueError(
                f"ORBITAL_SECRETS_ENCRYPTION_KEY is not a valid Fernet key: {e}"
            ) from e
        return self

    @model_validator(mode="after")
    def _validate_session_secret(self) -> "Settings":
        if not self.ui_auth_enabled:
            return self
        if self.session_secret == INSECURE_DEFAULT_SESSION_SECRET:
            raise ValueError(
                "ORBITAL_SESSION_SECRET is still the insecure default. Console auth "
                "(ui_auth_enabled=true) trusts this key to sign session cookies "
                "carrying the caller's identity and role - anyone who reads this "
                "repo's source can forge an admin session. Set ORBITAL_SESSION_SECRET "
                f"to a random value (>= {MIN_SESSION_SECRET_LENGTH} chars), e.g.: "
                'python3 -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if len(self.session_secret) < MIN_SESSION_SECRET_LENGTH:
            raise ValueError(
                f"ORBITAL_SESSION_SECRET is too short ({len(self.session_secret)} "
                f"chars; need >= {MIN_SESSION_SECRET_LENGTH}) to safely sign session "
                'cookies. Generate one with: python3 -c "import secrets; '
                'print(secrets.token_urlsafe(48))"'
            )
        return self


def warn_if_privileged_builds(settings: Settings) -> None:
    """Log a loud startup warning when BuildKit runs privileged.

    Not a validator: `buildkit_rootless=False` is a deliberate, supported
    escape hatch for environments without user-namespace support (see the
    field's docstring above), so this never blocks startup - it only makes
    sure an operator flipping it gets an unmissable signal about the blast
    radius they're accepting, since build Jobs execute untrusted,
    user-supplied repository content.
    """
    if settings.buildkit_rootless:
        return
    log.warning(
        "SECURITY: ORBITAL_BUILDKIT_ROOTLESS=false - build Jobs run "
        "PRIVILEGED containers (securityContext.privileged=true) instead of "
        "rootless, capability-restricted BuildKit. Build Jobs execute "
        "untrusted, user-supplied repository content (arbitrary "
        "Dockerfile.orbital / RUN steps from an app owner's own repo); a "
        "privileged container is one of the most direct paths to node/host "
        "compromise in Kubernetes. Only run this way where rootless "
        "BuildKit is confirmed unsupported - see docs/ADMIN.md."
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
