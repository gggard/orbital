#!/usr/bin/env bash
# One-time local-dev setup: minikube profile + registry + ingress + base image.
# Writes platform env vars to .env in the repo root.
set -euo pipefail
cd "$(dirname "$0")/../.."

PROFILE="${PROFILE:-orbital}"
PYVER="${PYVER:-3.12}"

if ! minikube -p "$PROFILE" status >/dev/null 2>&1; then
  # Nested Docker (LXC/rootless hosts) often has a lower open-files ceiling
  # than minikube's inner dockerd default (1048576). Exceeding it makes every
  # container fail with "error setting rlimit type 7: operation not
  # permitted" - including kube-apiserver/scheduler/controller-manager, which
  # then crash-loop and minikube start fails after a few retries. Clamp the
  # inner daemon's default ulimit to whatever this host actually allows.
  NOFILE_LIMIT=$(ulimit -Hn)
  DOCKER_OPT=()
  if [ "$NOFILE_LIMIT" != "unlimited" ] && [ "$NOFILE_LIMIT" -lt 1048576 ]; then
    DOCKER_OPT=(--docker-opt="default-ulimit=nofile=${NOFILE_LIMIT}:${NOFILE_LIMIT}")
  fi
  # KubeletInUserNamespace is required on hosts with restricted cgroups
  # (rootless / LXC environments); harmless elsewhere.
  minikube start -p "$PROFILE" --cpus=4 --memory=6g \
    --extra-config=kubelet.feature-gates=KubeletInUserNamespace=true \
    "${DOCKER_OPT[@]}"
fi
minikube -p "$PROFILE" addons enable registry
minikube -p "$PROFILE" addons enable ingress
# per-app CPU/memory monitoring in the console
minikube -p "$PROFILE" addons enable metrics-server

echo ">> building base images (python $PYVER, static)"
LOCAL_TAG="localhost:45000/streamlit-base:py${PYVER}"
docker build -t "$LOCAL_TAG" --build-arg "PYTHON_VERSION=${PYVER}" deploy/base-image
STATIC_LOCAL_TAG="localhost:45000/static-base:latest"
docker build -t "$STATIC_LOCAL_TAG" deploy/base-image/static

echo ">> pushing base images into the cluster registry"
kubectl --context "$PROFILE" -n kube-system port-forward svc/registry 45000:80 >/dev/null 2>&1 &
PF_PID=$!
trap 'kill $PF_PID 2>/dev/null || true' EXIT
for i in $(seq 1 20); do curl -sf http://localhost:45000/v2/ >/dev/null && break; sleep 0.5; done
docker push "$LOCAL_TAG"
docker push "$STATIC_LOCAL_TAG"

IP="$(minikube -p "$PROFILE" ip)"
GATEWAY_IP="$(echo "$IP" | sed 's/\.[0-9]*$/.1/')"
cat > .env <<EOF
ORBITAL_KUBE_CONTEXT=${PROFILE}
ORBITAL_APPS_DOMAIN=${IP}.nip.io
# Privileged builds: rootless BuildKit needs user namespaces, often unavailable
# in nested/LXC dev hosts. Remove this line on a normal cluster.
ORBITAL_BUILDKIT_ROOTLESS=false
# The control plane runs on the host in local dev (make run), not in-cluster,
# so the ingress's activity/wake auth-request (normally aimed at the
# in-cluster orbital-control-plane Service) can't resolve by DNS. Point it at
# the host via the minikube docker-bridge gateway instead - without this,
# every deployed app 500s when viewed through its ingress URL, hibernated or
# not. Same technique deploy/auth/setup-auth.sh uses for the OIDC callback.
ORBITAL_CONTROL_PLANE_SERVICE_HOST=${GATEWAY_IP}
EOF
echo ">> wrote .env:"
cat .env
echo ">> done. Start the control plane with: make run"
