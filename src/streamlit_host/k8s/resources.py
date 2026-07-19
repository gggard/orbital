"""Per-app runtime manifests: Deployment, Service, Ingress, Secret (SPEC §5.3)."""

from ..config import Settings
from ..models import App

MANAGED_BY = {"app.streamlit-host.io/managed-by": "control-plane"}


def app_labels(app: App) -> dict:
    return {**MANAGED_BY, "app.streamlit-host.io/app-id": app.id}


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
    health_path = f"{base_path}/_stcore/health"
    env = [{"name": "HOME", "value": "/home/appuser"}]
    if base_path:
        # path routing: Streamlit serves under the prefix (env var, no rebuild;
        # CLI flags in the image CMD don't set baseUrlPath so env wins)
        env.append({"name": "STREAMLIT_SERVER_BASE_URL_PATH", "value": base_path})
    volume_mounts = [
        {"name": "tmp", "mountPath": "/tmp"},
        {"name": "home", "mountPath": "/home/appuser"},
    ]
    volumes = [
        {"name": "tmp", "emptyDir": {"sizeLimit": "1Gi"}},
        {"name": "home", "emptyDir": {"sizeLimit": "1Gi"}},
    ]
    if app.secrets_toml:
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
            "selector": {"matchLabels": {"app.streamlit-host.io/app-id": app.id}},
            "strategy": {"type": "RollingUpdate"},
            "template": {
                "metadata": {
                    "labels": app_labels(app),
                    "annotations": {"app.streamlit-host.io/restarted-at": restarted_at},
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
            "selector": {"app.streamlit-host.io/app-id": app.id},
            "ports": [{"port": 80, "targetPort": settings.app_port}],
        },
    }


def ingress(app: App, settings: Settings) -> dict:
    if settings.routing_mode == "path":
        host = settings.apps_domain
        path = settings.base_url_path(app.slug)
    else:
        host = f"{app.slug}.{settings.apps_domain}"
        path = "/"
    annotations = {
        # Streamlit needs long-lived websockets
        "nginx.ingress.kubernetes.io/proxy-read-timeout": "3600",
        "nginx.ingress.kubernetes.io/proxy-send-timeout": "3600",
        "nginx.ingress.kubernetes.io/proxy-body-size": "200m",
    }
    if not app.public and settings.auth_enabled:
        # nginx auth_request -> control plane authz (session + group check),
        # 401 -> redirect the browser to oauth2-proxy sign-in (SPEC §5.5)
        port = settings.url_port_suffix()
        annotations["nginx.ingress.kubernetes.io/auth-url"] = (
            f"{settings.authz_base_url}/authz/{app.id}"
        )
        annotations["nginx.ingress.kubernetes.io/auth-signin"] = (
            f"{settings.auth_signin_url()}?rd=http://$host{port}$escaped_request_uri"
        )
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
                                        "name": name_for(app),
                                        "port": {"number": 80},
                                    }
                                },
                            }
                        ]
                    },
                }
            ],
        },
    }
