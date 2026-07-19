#!/usr/bin/env bash
# Deploys the demo auth stack (Keycloak + oauth2-proxy) and appends the
# auth settings to .env. Reads ORBITAL_APPS_DOMAIN / ORBITAL_APPS_URL_PORT from .env.
set -euo pipefail
cd "$(dirname "$0")/../.."

PROFILE="${PROFILE:-orbital}"
DOMAIN=$(grep '^ORBITAL_APPS_DOMAIN=' .env | cut -d= -f2)
PORT=$(grep '^ORBITAL_APPS_URL_PORT=' .env | cut -d= -f2 || true)
PORT_SUFFIX=""
[ -n "$PORT" ] && [ "$PORT" != "80" ] && PORT_SUFFIX=":$PORT"

CLIENT_SECRET="${CLIENT_SECRET:-orbital-dev-secret}"
COOKIE_SECRET=$(python3 -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")

echo ">> deploying Keycloak + oauth2-proxy (domain=$DOMAIN, port suffix=$PORT_SUFFIX)"
sed -e "s/@DOMAIN@/$DOMAIN/g" \
    -e "s/@PORT_SUFFIX@/$PORT_SUFFIX/g" \
    -e "s/@CLIENT_SECRET@/$CLIENT_SECRET/g" \
    -e "s|@COOKIE_SECRET@|$COOKIE_SECRET|g" \
    -e "s/@INGRESS_CLASS@/nginx/g" \
    deploy/auth/auth-stack.yaml.tmpl | kubectl --context "$PROFILE" apply -f -

echo ">> waiting for rollouts (keycloak first start takes ~1 min)"
kubectl --context "$PROFILE" -n orbital-platform rollout status deploy/oauth2-proxy --timeout=300s
kubectl --context "$PROFILE" -n orbital-platform rollout status deploy/keycloak --timeout=600s

MINIKUBE_IP=$(minikube -p "$PROFILE" ip)
GATEWAY_IP=$(echo "$MINIKUBE_IP" | sed 's/\.[0-9]*$/.1/')

grep -q '^ORBITAL_AUTH_ENABLED=' .env || cat >> .env <<EOF
ORBITAL_AUTH_ENABLED=true
ORBITAL_OAUTH2_PROXY_AUTH_URL=http://${MINIKUBE_IP}:30480/oauth2/auth
ORBITAL_AUTHZ_BASE_URL=http://${GATEWAY_IP}:8000
EOF
echo ">> .env now contains:"
cat .env
echo ">> done. Restart the control plane to enable auth."
echo "   Demo users: alice/alice123 (group data-team), bob/bob123 (group viewers)"
