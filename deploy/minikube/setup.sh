#!/usr/bin/env bash
# One-time local-dev setup: minikube profile + registry + ingress + base image.
# Writes platform env vars to .env in the repo root.
set -euo pipefail
cd "$(dirname "$0")/../.."

PROFILE="${PROFILE:-streamlit-host}"
PYVER="${PYVER:-3.12}"

if ! minikube -p "$PROFILE" status >/dev/null 2>&1; then
  # KubeletInUserNamespace is required on hosts with restricted cgroups
  # (rootless / LXC environments); harmless elsewhere.
  minikube start -p "$PROFILE" --cpus=4 --memory=6g \
    --extra-config=kubelet.feature-gates=KubeletInUserNamespace=true
fi
minikube -p "$PROFILE" addons enable registry
minikube -p "$PROFILE" addons enable ingress

echo ">> building base image (python $PYVER)"
LOCAL_TAG="localhost:45000/streamlit-base:py${PYVER}"
docker build -t "$LOCAL_TAG" --build-arg "PYTHON_VERSION=${PYVER}" deploy/base-image

echo ">> pushing base image into the cluster registry"
kubectl --context "$PROFILE" -n kube-system port-forward svc/registry 45000:80 >/dev/null 2>&1 &
PF_PID=$!
trap 'kill $PF_PID 2>/dev/null || true' EXIT
for i in $(seq 1 20); do curl -sf http://localhost:45000/v2/ >/dev/null && break; sleep 0.5; done
docker push "$LOCAL_TAG"

IP="$(minikube -p "$PROFILE" ip)"
cat > .env <<EOF
SH_KUBE_CONTEXT=${PROFILE}
SH_APPS_DOMAIN=${IP}.nip.io
# Privileged builds: rootless BuildKit needs user namespaces, often unavailable
# in nested/LXC dev hosts. Remove this line on a normal cluster.
SH_BUILDKIT_ROOTLESS=false
EOF
echo ">> wrote .env:"
cat .env
echo ">> done. Start the control plane with: make run"
