"""Build Job and supporting ConfigMap manifests."""

from ..config import Settings
from ..models import App, Build
from . import scripts

SUPPORT_CONFIGMAP = "orbital-build-support"


def build_support_configmap(settings: Settings) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": SUPPORT_CONFIGMAP,
            "namespace": settings.builds_namespace,
            "labels": {"app.orbital.io/managed-by": "control-plane"},
        },
        "data": {
            "fetch.sh": scripts.FETCH_SH,
            "detect.sh": scripts.DETECT_SH,
            "build.sh": scripts.BUILD_SH,
            "buildkitd.toml": scripts.buildkitd_toml(settings.registry_push_url),
        },
    }


def build_job(app: App, build: Build, settings: Settings) -> dict:
    push_image = settings.app_image(app.id, build.id, pull=False)
    base_image = settings.base_image_for(app.python_version)
    labels = {
        "app.orbital.io/managed-by": "control-plane",
        "app.orbital.io/app-id": app.id,
        "app.orbital.io/build-id": build.id,
    }
    if settings.buildkit_rootless:
        pod_annotations = {
            "container.apparmor.security.beta.kubernetes.io/buildkit": "unconfined"
        }
        buildkit_security = {
            "seccompProfile": {"type": "Unconfined"},
            "runAsUser": 1000,
            "runAsGroup": 1000,
        }
        buildkitd_flags = "--oci-worker-no-process-sandbox"
        config_path = "/home/user/.config/buildkit/buildkitd.toml"
        state_path = "/home/user/.local/share/buildkit"
    else:
        pod_annotations = {}
        buildkit_security = {"privileged": True}
        buildkitd_flags = ""
        config_path = "/etc/buildkit/buildkitd.toml"
        state_path = "/var/lib/buildkit"
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": f"build-{build.id}",
            "namespace": settings.builds_namespace,
            "labels": labels,
        },
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": settings.build_ttl_seconds,
            "activeDeadlineSeconds": settings.build_timeout_seconds,
            "template": {
                "metadata": {
                    "labels": labels,
                    "annotations": pod_annotations,
                },
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "initContainers": [
                        {
                            "name": "fetch",
                            "image": settings.git_image,
                            "command": [
                                "sh",
                                "-c",
                                "sh /scripts/fetch.sh && sh /scripts/detect.sh",
                            ],
                            "env": [
                                {"name": "REPO_URL", "value": app.repo_url},
                                {"name": "BRANCH", "value": app.branch},
                                {"name": "COMMIT_SHA", "value": build.commit_sha or ""},
                                {"name": "MAIN_FILE", "value": app.main_file},
                                {"name": "BASE_IMAGE", "value": base_image},
                                {"name": "SRC_DIR", "value": "/workspace/src"},
                            ],
                            "volumeMounts": [
                                {"name": "workspace", "mountPath": "/workspace"},
                                {"name": "scripts", "mountPath": "/scripts"},
                            ],
                        }
                    ],
                    "containers": [
                        {
                            "name": "buildkit",
                            "image": settings.resolved_buildkit_image(),
                            "command": ["sh", "/scripts/build.sh"],
                            "env": [
                                {"name": "IMAGE", "value": push_image},
                                {"name": "SRC_DIR", "value": "/workspace/src"},
                                {"name": "BUILDKITD_FLAGS", "value": buildkitd_flags},
                            ],
                            "securityContext": buildkit_security,
                            "volumeMounts": [
                                {"name": "workspace", "mountPath": "/workspace"},
                                {"name": "scripts", "mountPath": "/scripts"},
                                {
                                    "name": "scripts",
                                    "mountPath": config_path,
                                    "subPath": "buildkitd.toml",
                                },
                                {"name": "buildkit-state", "mountPath": state_path},
                            ],
                            "resources": {
                                "requests": {"cpu": "500m", "memory": "512Mi"},
                                "limits": {"cpu": "2", "memory": "2Gi"},
                            },
                        }
                    ],
                    "volumes": [
                        {"name": "workspace", "emptyDir": {}},
                        {"name": "scripts", "configMap": {"name": SUPPORT_CONFIGMAP}},
                        {"name": "buildkit-state", "emptyDir": {}},
                    ],
                },
            },
        },
    }
