"""Per-app runtime manifests: Deployment, Service, Ingress, Secret (SPEC §5.3)."""

from ..config import Settings
from ..models import App, AppState, AppType

MANAGED_BY = {"app.orbital.io/managed-by": "control-plane"}
APP_ID_LABEL = "app.orbital.io/app-id"

# Mount path inside the app's own dedicated emptyDir volume (readOnlyRootFilesystem
# needs a writable /tmp), not the host's - isolated per-pod, so the shared-directory
# risk S5443 warns about doesn't apply here.
_APP_TMP_DIR = "/tmp"  # NOSONAR

# in-namespace ExternalName Service that lets the apps-namespace Ingress
# objects reach the control plane (a different namespace) as the wake proxy
# and activity-beacon backend (SPEC §5.6).
WAKE_SERVICE_NAME = "sh-wake-proxy"


def app_labels(app: App) -> dict:
    return {**MANAGED_BY, APP_ID_LABEL: app.id}


def name_for(app: App) -> str:
    return f"app-{app.id}"


def secret_name(app: App) -> str:
    return f"app-{app.id}-secrets"


def secret(app: App, settings: Settings) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": secret_name(app),
            "namespace": settings.apps_namespace,
            "labels": app_labels(app),
        },
        "stringData": {"secrets.toml": app.secrets_toml or ""},
    }


def deployment(app: App, image: str, settings: Settings, restarted_at: str) -> dict:
    base_path = settings.base_url_path(app.slug)
    env = [{"name": "HOME", "value": "/home/appuser"}]
    if app.app_type == AppType.streamlit:
        health_path = f"{base_path}/_stcore/health"
        if base_path:
            # path routing: Streamlit serves under the prefix (env var, no rebuild;
            # CLI flags in the image CMD don't set baseUrlPath so env wins)
            env.append({"name": "STREAMLIT_SERVER_BASE_URL_PATH", "value": base_path})
    else:
        # static apps have no generic base-path mechanism (best-effort under
        # path routing - see docs/ADMIN.md); nginx just serves at "/"
        health_path = f"{base_path}/" if base_path else "/"
    volume_mounts = [
        {"name": "tmp", "mountPath": _APP_TMP_DIR},
        {"name": "home", "mountPath": "/home/appuser"},
    ]
    volumes = [
        {"name": "tmp", "emptyDir": {"sizeLimit": "1Gi"}},
        {"name": "home", "emptyDir": {"sizeLimit": "1Gi"}},
    ]
    if app.app_type == AppType.streamlit and app.secrets_toml:
        volume_mounts.append(
            {
                "name": "secrets",
                "mountPath": "/app/.streamlit/secrets.toml",
                "subPath": "secrets.toml",
                "readOnly": True,
            }
        )
        volumes.append({"name": "secrets", "secret": {"secretName": secret_name(app)}})

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name_for(app),
            "namespace": settings.apps_namespace,
            "labels": app_labels(app),
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {APP_ID_LABEL: app.id}},
            "strategy": {"type": "RollingUpdate"},
            "template": {
                "metadata": {
                    "labels": app_labels(app),
                    "annotations": {"app.orbital.io/restarted-at": restarted_at},
                },
                "spec": {
                    "automountServiceAccountToken": False,
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 1000,
                        "runAsGroup": 1000,
                        "fsGroup": 1000,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [
                        {
                            "name": "app",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "ports": [{"containerPort": settings.app_port}],
                            "env": env,
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "readinessProbe": {
                                "httpGet": {
                                    "path": health_path,
                                    "port": settings.app_port,
                                },
                                "initialDelaySeconds": 3,
                                "periodSeconds": 5,
                            },
                            "livenessProbe": {
                                "httpGet": {
                                    "path": health_path,
                                    "port": settings.app_port,
                                },
                                "initialDelaySeconds": 20,
                                "periodSeconds": 15,
                            },
                            "resources": {
                                "requests": {
                                    "cpu": settings.app_cpu_request,
                                    "memory": settings.app_mem_request,
                                },
                                "limits": {
                                    "cpu": settings.app_cpu_limit,
                                    "memory": settings.app_mem_limit,
                                },
                            },
                            "volumeMounts": volume_mounts,
                        }
                    ],
                    "volumes": volumes,
                },
            },
        },
    }


def service(app: App, settings: Settings) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": name_for(app),
            "namespace": settings.apps_namespace,
            "labels": app_labels(app),
        },
        "spec": {
            "selector": {APP_ID_LABEL: app.id},
            "ports": [{"port": 80, "targetPort": settings.app_port}],
        },
    }


def wake_service(settings: Settings) -> dict:
    """ExternalName Service in the apps namespace pointing at the control plane."""
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": WAKE_SERVICE_NAME,
            "namespace": settings.apps_namespace,
            "labels": MANAGED_BY,
        },
        "spec": {
            "type": "ExternalName",
            "externalName": settings.control_plane_service_host,
            "ports": [
                {
                    "port": settings.control_plane_service_port,
                    "targetPort": settings.control_plane_service_port,
                }
            ],
        },
    }


def _hibernation_active(app: App, settings: Settings) -> bool:
    return bool(
        settings.hibernation_enabled
        and settings.control_plane_service_host
        and app.hibernate_enabled
    )


def ingress(app: App, settings: Settings) -> dict:
    if settings.routing_mode == "path":
        host = settings.apps_domain
        path = settings.base_url_path(app.slug)
    else:
        host = f"{app.slug}.{settings.apps_domain}"
        path = "/"
    annotations = {"nginx.ingress.kubernetes.io/proxy-body-size": "200m"}
    if app.app_type == AppType.streamlit:
        # Streamlit needs long-lived websockets; static apps get ingress
        # defaults, which is more correct (no reason to hang for an hour).
        annotations["nginx.ingress.kubernetes.io/proxy-read-timeout"] = "3600"
        annotations["nginx.ingress.kubernetes.io/proxy-send-timeout"] = "3600"
    if not app.public and settings.auth_enabled:
        # nginx auth_request -> control plane authz (session + group check),
        # 401 -> redirect the browser to oauth2-proxy sign-in (SPEC §5.5).
        # This request also records activity (SPEC §4.8).
        port = settings.url_port_suffix()
        base = settings.authz_base_url or settings.internal_base_url()
        annotations["nginx.ingress.kubernetes.io/auth-url"] = f"{base}/authz/{app.id}"
        annotations["nginx.ingress.kubernetes.io/auth-signin"] = (
            f"{settings.auth_signin_url()}?rd=http://$host{port}$escaped_request_uri"
        )
    elif app.public and _hibernation_active(app, settings) and app.state != AppState.sleeping:
        # public apps have no auth_request in front of them; attach a
        # non-blocking beacon (always 200) purely to record activity so the
        # reconciler knows the app is still being used (SPEC §4.8/§5.6).
        # Same base-URL override as the private-app authz annotation above -
        # both are auth_request subrequests from the ingress controller, so
        # they need the same "reachable from inside the cluster" address.
        base = settings.authz_base_url or settings.internal_base_url()
        annotations["nginx.ingress.kubernetes.io/auth-url"] = f"{base}/activity/{app.id}"

    if app.state == AppState.sleeping and _hibernation_active(app, settings):
        # scaled to zero: route to the control plane, which serves the
        # waking-up interstitial and requests a wake-up (SPEC §5.6)
        backend_name = WAKE_SERVICE_NAME
        backend_port = settings.control_plane_service_port
    else:
        backend_name = name_for(app)
        backend_port = 80

    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "name": name_for(app),
            "namespace": settings.apps_namespace,
            "labels": app_labels(app),
            "annotations": annotations,
        },
        "spec": {
            "ingressClassName": settings.ingress_class,
            "rules": [
                {
                    "host": host,
                    "http": {
                        "paths": [
                            {
                                "path": path,
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": backend_name,
                                        "port": {"number": backend_port},
                                    }
                                },
                            }
                        ]
                    },
                }
            ],
        },
    }
