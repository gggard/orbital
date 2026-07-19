import logging

from kubernetes import client, config

from ..config import get_settings

log = logging.getLogger(__name__)

_api_client: client.ApiClient | None = None


def api() -> client.ApiClient:
    global _api_client
    if _api_client is None:
        settings = get_settings()
        try:
            config.load_incluster_config()
            log.info("using in-cluster kube config")
        except config.ConfigException:
            config.load_kube_config(context=settings.kube_context)
            log.info("using kubeconfig (context=%s)", settings.kube_context or "current")
        _api_client = client.ApiClient()
    return _api_client


def core() -> client.CoreV1Api:
    return client.CoreV1Api(api())


def apps_v1() -> client.AppsV1Api:
    return client.AppsV1Api(api())


def batch() -> client.BatchV1Api:
    return client.BatchV1Api(api())


def networking() -> client.NetworkingV1Api:
    return client.NetworkingV1Api(api())


def ensure_namespace(name: str) -> None:
    try:
        core().create_namespace({"metadata": {"name": name}})
        log.info("created namespace %s", name)
    except client.ApiException as e:
        if e.status == 403:
            # namespace-scoped deployments (e.g. Helm-managed) pre-create
            # namespaces and don't grant cluster-wide namespace creation
            log.info("no permission to create namespace %s; assuming it exists", name)
        elif e.status != 409:
            raise
