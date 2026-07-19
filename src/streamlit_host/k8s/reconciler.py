"""Control loop driving apps from desired state (DB) to actual state (cluster).

The reconciler is the only component that writes to Kubernetes (SPEC §5.1).
"""

import logging
import threading
import time
from datetime import UTC, datetime

from kubernetes.client import ApiException
from sqlalchemy import select

from ..config import get_settings
from ..db import session_scope
from ..gitutil import GitError, resolve_branch_head
from ..models import App, AppState, Build, BuildPhase, PendingAction
from . import builder, client, metrics, resources
from .inspect import build_log_tail

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _not_found_ok(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ApiException as e:
        if e.status != 404:
            raise
        return None


def _apply(create_fn, replace_fn, name: str, namespace: str, body: dict):
    try:
        create_fn(namespace, body)
    except ApiException as e:
        if e.status != 409:
            raise
        replace_fn(name, namespace, body)


class Reconciler:
    def __init__(self):
        self.settings = get_settings()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_sample = 0.0

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        self.ensure_setup()
        self._thread = threading.Thread(target=self._run, daemon=True, name="reconciler")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _run(self):
        log.info("reconciler started (interval=%ss)", self.settings.reconcile_interval)
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("reconcile tick failed")
            self._stop.wait(self.settings.reconcile_interval)

    def ensure_setup(self):
        client.ensure_namespace(self.settings.apps_namespace)
        client.ensure_namespace(self.settings.builds_namespace)
        cm = builder.build_support_configmap(self.settings)
        _apply(
            client.core().create_namespaced_config_map,
            client.core().replace_namespaced_config_map,
            cm["metadata"]["name"],
            self.settings.builds_namespace,
            cm,
        )

    # -- reconcile ---------------------------------------------------------

    def tick(self):
        with session_scope() as session:
            apps = session.scalars(select(App)).all()
            for app in apps:
                try:
                    self.step(session, app)
                except Exception:
                    log.exception("reconcile failed for app %s (%s)", app.slug, app.id)
            self._sample_metrics(apps)

    def _sample_metrics(self, apps: list[App]):
        now = time.time()
        if now - self._last_sample < metrics.SAMPLE_INTERVAL:
            return
        self._last_sample = now
        for app in apps:
            if app.state != AppState.running:
                continue
            try:
                sample = metrics.fetch_app_usage(app.id, self.settings)
            except Exception:
                log.exception("metrics sampling failed for app %s", app.slug)
                continue
            if sample is not None:
                metrics.store.add(app.id, sample)

    def step(self, session, app: App):
        if app.pending_action == PendingAction.delete:
            self._delete_app(session, app)
            return

        if app.pending_action == PendingAction.deploy and app.state != AppState.building:
            self._start_build(session, app)
            return

        if app.state == AppState.building:
            self._check_build(session, app)
            return

        if app.state == AppState.deploying:
            self._check_rollout(app)

        if app.state == AppState.running:
            self._ensure_ingress(app)
            self._ensure_base_path(app)

        if app.state in (AppState.running, AppState.deploying, AppState.deploy_failed):
            if app.pending_action == PendingAction.reboot:
                app.pending_action = PendingAction.none
                self._restart(app)
                app.state = AppState.deploying
            elif app.secrets_dirty and app.current_image:
                # re-apply the whole deployment: the secret volume mount may not
                # exist yet if the app was first deployed without secrets
                self._deploy(app)
                app.secrets_dirty = False
                app.state = AppState.deploying

    # -- build -------------------------------------------------------------

    def _start_build(self, session, app: App):
        try:
            sha = resolve_branch_head(app.repo_url, app.branch)
        except GitError as e:
            app.state = AppState.build_failed
            app.pending_action = PendingAction.none
            app.error = str(e)
            log.warning("commit resolution failed for %s: %s", app.slug, e)
            return

        build = Build(app_id=app.id, commit_sha=sha, phase=BuildPhase.running)
        session.add(build)
        session.flush()
        build.image = self.settings.app_image(app.id, build.id, pull=True)

        job = builder.build_job(app, build, self.settings)
        client.batch().create_namespaced_job(self.settings.builds_namespace, job)

        app.state = AppState.building
        app.pending_action = PendingAction.none
        app.current_build_id = build.id
        app.error = None
        log.info("build %s started for app %s at %s", build.id, app.slug, sha[:10])

    def _check_build(self, session, app: App):
        build = session.get(Build, app.current_build_id)
        if build is None:
            app.state = AppState.build_failed
            app.error = "build record missing"
            return

        job = _not_found_ok(
            client.batch().read_namespaced_job,
            f"build-{build.id}",
            self.settings.builds_namespace,
        )
        if job is None:
            self._fail_build(build, app, "build job not found (expired or deleted)")
            return

        for cond in (job.status.conditions or []):
            if cond.type == "Complete" and cond.status == "True":
                build.phase = BuildPhase.succeeded
                build.finished_at = datetime.now(UTC)
                app.current_image = build.image
                app.error = None
                log.info("build %s succeeded; deploying %s", build.id, app.slug)
                self._deploy(app)
                app.state = AppState.deploying
                return
            if cond.type == "Failed" and cond.status == "True":
                tail = build_log_tail(build.id, self.settings)
                self._fail_build(build, app, cond.message or "build failed", tail)
                return

    def _fail_build(self, build: Build, app: App, message: str, log_tail: str = ""):
        build.phase = BuildPhase.failed
        build.finished_at = datetime.now(UTC)
        build.error = f"{message}\n{log_tail}".strip()
        app.state = AppState.build_failed
        app.error = message
        log.warning("build %s failed for %s: %s", build.id, app.slug, message)

    # -- deploy ------------------------------------------------------------

    def _deploy(self, app: App):
        s = self.settings
        if app.secrets_toml:
            sec = resources.secret(app, s)
            _apply(
                client.core().create_namespaced_secret,
                client.core().replace_namespaced_secret,
                sec["metadata"]["name"], s.apps_namespace, sec,
            )
        dep = resources.deployment(app, app.current_image, s, _now_iso())
        _apply(
            client.apps_v1().create_namespaced_deployment,
            client.apps_v1().replace_namespaced_deployment,
            dep["metadata"]["name"], s.apps_namespace, dep,
        )
        svc = resources.service(app, s)
        try:
            client.core().create_namespaced_service(s.apps_namespace, svc)
        except ApiException as e:
            if e.status != 409:
                raise  # Service replace requires resourceVersion; existing one is fine
        ing = resources.ingress(app, s)
        _apply(
            client.networking().create_namespaced_ingress,
            client.networking().replace_namespaced_ingress,
            ing["metadata"]["name"], s.apps_namespace, ing,
        )

    def _ensure_ingress(self, app: App):
        """Converge ingress host and auth annotations (domain or public/private changes)."""
        desired = resources.ingress(app, self.settings)
        current = _not_found_ok(
            client.networking().read_namespaced_ingress,
            resources.name_for(app),
            self.settings.apps_namespace,
        )
        desired_rule = desired["spec"]["rules"][0]
        desired_host = desired_rule["host"]
        desired_path = desired_rule["http"]["paths"][0]["path"]
        desired_auth = desired["metadata"]["annotations"].get(
            "nginx.ingress.kubernetes.io/auth-url"
        )
        current_auth = (
            (current.metadata.annotations or {}).get("nginx.ingress.kubernetes.io/auth-url")
            if current
            else None
        )
        if (
            current is None
            or current.spec.rules[0].host != desired_host
            or current.spec.rules[0].http.paths[0].path != desired_path
            or current_auth != desired_auth
        ):
            log.info(
                "updating ingress for %s (host=%s path=%s auth=%s)",
                app.slug, desired_host, desired_path, bool(desired_auth),
            )
            _apply(
                client.networking().create_namespaced_ingress,
                client.networking().replace_namespaced_ingress,
                desired["metadata"]["name"],
                self.settings.apps_namespace,
                desired,
            )

    def _ensure_base_path(self, app: App):
        """Converge the pod's Streamlit baseUrlPath when routing_mode changes."""
        dep = _not_found_ok(
            client.apps_v1().read_namespaced_deployment,
            resources.name_for(app),
            self.settings.apps_namespace,
        )
        if dep is None or not app.current_image:
            return
        env = dep.spec.template.spec.containers[0].env or []
        current = next(
            (e.value for e in env if e.name == "STREAMLIT_SERVER_BASE_URL_PATH"), ""
        )
        desired = self.settings.base_url_path(app.slug)
        if current != desired:
            log.info(
                "routing mode change: redeploying %s (baseUrlPath %r -> %r)",
                app.slug, current, desired,
            )
            self._deploy(app)
            app.state = AppState.deploying

    def _restart(self, app: App):
        patch = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {"app.streamlit-host.io/restarted-at": _now_iso()}
                    }
                }
            }
        }
        _not_found_ok(
            client.apps_v1().patch_namespaced_deployment,
            resources.name_for(app),
            self.settings.apps_namespace,
            patch,
        )

    def _check_rollout(self, app: App):
        dep = _not_found_ok(
            client.apps_v1().read_namespaced_deployment,
            resources.name_for(app),
            self.settings.apps_namespace,
        )
        if dep is None:
            return
        if (dep.status.ready_replicas or 0) >= 1 and (
            dep.status.updated_replicas or 0
        ) >= 1:
            app.state = AppState.running
            app.error = None
            return
        # surface crash loops / pull errors instead of waiting forever
        pods = client.core().list_namespaced_pod(
            self.settings.apps_namespace,
            label_selector=f"app.streamlit-host.io/app-id={app.id}",
        )
        for pod in pods.items:
            for cs in pod.status.container_statuses or []:
                waiting = cs.state.waiting
                if waiting and waiting.reason in ("CrashLoopBackOff", "ErrImagePull", "ImagePullBackOff"):
                    app.state = AppState.deploy_failed
                    app.error = f"{waiting.reason}: {waiting.message or ''}".strip()
                    return

    # -- delete ------------------------------------------------------------

    def _delete_app(self, session, app: App):
        s = self.settings
        name = resources.name_for(app)
        _not_found_ok(client.networking().delete_namespaced_ingress, name, s.apps_namespace)
        _not_found_ok(client.apps_v1().delete_namespaced_deployment, name, s.apps_namespace)
        _not_found_ok(client.core().delete_namespaced_service, name, s.apps_namespace)
        _not_found_ok(
            client.core().delete_namespaced_secret, resources.secret_name(app), s.apps_namespace
        )
        jobs = client.batch().list_namespaced_job(
            s.builds_namespace,
            label_selector=f"app.streamlit-host.io/app-id={app.id}",
        )
        for job in jobs.items:
            _not_found_ok(
                client.batch().delete_namespaced_job,
                job.metadata.name,
                s.builds_namespace,
                propagation_policy="Background",
            )
        metrics.store.drop(app.id)
        log.info("deleted app %s (%s)", app.slug, app.id)
        session.delete(app)


_reconciler: Reconciler | None = None


def start_reconciler() -> Reconciler:
    global _reconciler
    if _reconciler is None:
        _reconciler = Reconciler()
        _reconciler.start()
    return _reconciler


def stop_reconciler():
    global _reconciler
    if _reconciler is not None:
        _reconciler.stop()
        _reconciler = None
