"""Vulnerability-scan Job manifest, mirroring builder.py's build_job()."""

import json
import logging

from ..config import Settings
from ..models import App, ScanResult, Severity, Vulnerability

log = logging.getLogger(__name__)

# Mount path inside the scan Job's own dedicated emptyDir volume, not the
# host's /tmp - isolated per-pod, so the shared-directory risk S5443 warns
# about doesn't apply here.
_TRIVY_CACHE_DIR = "/tmp/trivy-cache"  # NOSONAR


def scan_job(app: App, scan: ScanResult, settings: Settings) -> dict:
    # scan.image mirrors app.current_image (pull form: localhost:5000/...,
    # only resolvable by the kubelet) so the "same image already scanned"
    # comparison in reconciler._maybe_scan stays valid across restarts. The
    # scan Job is just another in-cluster pod though - like builder.build_job,
    # it needs the push-form reference (in-cluster registry DNS) to actually
    # pull the image itself.
    push_image = settings.app_image(app.id, scan.build_id, pull=False)
    labels = {
        "app.orbital.io/managed-by": "control-plane",
        "app.orbital.io/app-id": app.id,
        "app.orbital.io/scan-id": scan.id,
    }
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": f"scan-{scan.id}",
            "namespace": settings.scans_namespace,
            "labels": labels,
        },
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": settings.scan_ttl_seconds,
            "activeDeadlineSeconds": settings.scan_timeout_seconds,
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 1000,
                        "runAsGroup": 1000,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [
                        {
                            "name": "trivy",
                            "image": settings.trivy_image,
                            "command": [
                                "trivy",
                                "image",
                                "--insecure",
                                "--quiet",
                                "--cache-dir",
                                _TRIVY_CACHE_DIR,
                                "--format",
                                "json",
                                "--scanners",
                                "vuln",
                                push_image,
                            ],
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "volumeMounts": [
                                {"name": "cache", "mountPath": _TRIVY_CACHE_DIR},
                            ],
                            "resources": {
                                "requests": {"cpu": "250m", "memory": "512Mi"},
                                "limits": {"cpu": "2", "memory": "2Gi"},
                            },
                        }
                    ],
                    "volumes": [{"name": "cache", "emptyDir": {}}],
                },
            },
        },
    }


def parse_report(raw: str) -> tuple[dict[Severity, int], list[Vulnerability]]:
    """Parse a `trivy image --format json` report into Vulnerability rows
    and per-severity counts. Malformed/empty input yields an all-zero
    result rather than raising - the caller still needs to mark the scan
    finished even when Trivy produced no parseable output (e.g. a killed
    pod whose log the reconciler picked up mid-write).
    """
    counts: dict[Severity, int] = {severity: 0 for severity in Severity}
    vulnerabilities: list[Vulnerability] = []
    try:
        report = json.loads(raw) if raw else {}
    except ValueError:
        log.warning("could not parse trivy report as JSON (%d bytes)", len(raw))
        return counts, vulnerabilities

    for result in report.get("Results") or []:
        target = result.get("Target")
        for finding in result.get("Vulnerabilities") or []:
            try:
                severity = Severity((finding.get("Severity") or "").lower())
            except ValueError:
                severity = Severity.unknown
            counts[severity] += 1
            vulnerabilities.append(
                Vulnerability(
                    vuln_id=finding.get("VulnerabilityID", ""),
                    pkg_name=finding.get("PkgName", ""),
                    installed_version=finding.get("InstalledVersion", ""),
                    fixed_version=finding.get("FixedVersion"),
                    severity=severity,
                    title=finding.get("Title"),
                    target=target,
                )
            )
    return counts, vulnerabilities
