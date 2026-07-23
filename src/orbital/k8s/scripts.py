"""Shell scripts run inside build Jobs (mounted via ConfigMap).

fetch.sh  - clones the repo at the requested branch/commit (init container, alpine/git)
detect.sh - branches on APP_TYPE: for streamlit apps, detects the Python
            dependency file per SPEC §4.3; for static apps, optionally runs
            an npm build. Either way, generates a Dockerfile.
build.sh  - builds and pushes the image with rootless BuildKit (daemonless)
"""

FETCH_SH = r"""#!/bin/sh
set -eu
SRC_DIR="${SRC_DIR:-/workspace/src}"
echo "[fetch] cloning $REPO_URL (branch $BRANCH)"
git clone --depth 50 --branch "$BRANCH" "$REPO_URL" "$SRC_DIR"
cd "$SRC_DIR"
if [ -n "${COMMIT_SHA:-}" ]; then
  if git -c advice.detachedHead=false checkout -q "$COMMIT_SHA" 2>/dev/null; then
    echo "[fetch] checked out $COMMIT_SHA"
  else
    echo "[fetch] WARNING: commit $COMMIT_SHA not in shallow clone; using branch head"
  fi
fi
echo "[fetch] at commit $(git rev-parse HEAD)"
"""

DETECT_SH = r"""#!/bin/sh
# Detects the app's Python dependency file and generates Dockerfile.orbital.
# Search order (SPEC 4.3): entrypoint directory first, then repository root.
# Priority: uv.lock (+pyproject.toml) > requirements.txt > pyproject.toml.
set -eu
SRC_DIR="${SRC_DIR:-/workspace/src}"
APP_TYPE="${APP_TYPE:-streamlit}"
cd "$SRC_DIR"

if [ "$APP_TYPE" = "static" ]; then
  BUILD_COMMAND="${BUILD_COMMAND:-}"
  OUTPUT_DIR="${OUTPUT_DIR:-.}"
  DF="$SRC_DIR/Dockerfile.orbital"

  if [ -n "$BUILD_COMMAND" ]; then
    if [ ! -f package.json ]; then
      echo "[detect] ERROR: build_command is set but no package.json found in repository root; only npm-based builds are supported"
      exit 1
    fi
    echo "[detect] npm build: $BUILD_COMMAND (output: $OUTPUT_DIR)"
    # carry the manifest into the final image (outside the nginx webroot, so
    # it's never served) purely so the vulnerability scanner can see npm
    # dependency versions - the multi-stage build otherwise discards
    # node_modules/package-lock.json along with the rest of the build stage.
    LOCKFILE=""
    for f in package-lock.json yarn.lock pnpm-lock.yaml; do
      if [ -f "$f" ]; then LOCKFILE="$f"; break; fi
    done
    {
      echo "FROM node:20-alpine AS build"
      echo "WORKDIR /src"
      echo "COPY . ."
      echo "RUN npm ci || npm install"
      printf 'RUN sh -c "%s"\n' "$BUILD_COMMAND"
      echo "FROM $BASE_IMAGE"
      echo "COPY --from=build --chown=1000:1000 /src/$OUTPUT_DIR /usr/share/nginx/html"
      echo "COPY --from=build /src/package.json /opt/app-manifest/package.json"
      if [ -n "$LOCKFILE" ]; then
        echo "COPY --from=build /src/$LOCKFILE /opt/app-manifest/$LOCKFILE"
      fi
    } > "$DF"
  else
    if [ ! -d "$OUTPUT_DIR" ]; then
      echo "[detect] ERROR: output_dir '$OUTPUT_DIR' not found in repository"
      exit 1
    fi
    echo "[detect] serving $OUTPUT_DIR as-is (no build step)"
    {
      echo "FROM $BASE_IMAGE"
      echo "COPY --chown=1000:1000 $OUTPUT_DIR /usr/share/nginx/html"
    } > "$DF"
  fi

  echo "[detect] generated Dockerfile:"
  cat "$DF"
  exit 0
fi

if [ ! -f "$MAIN_FILE" ]; then
  echo "[detect] ERROR: main file '$MAIN_FILE' not found in repository"
  exit 1
fi
MAIN_DIR=$(dirname "$MAIN_FILE")

DEP_TYPE=""
DEP_DIR=""
for dir in "$MAIN_DIR" "."; do
  if [ -n "$DEP_TYPE" ]; then break; fi
  if [ -f "$dir/uv.lock" ] && [ -f "$dir/pyproject.toml" ]; then
    DEP_TYPE=uvlock DEP_DIR="$dir"
  elif [ -f "$dir/requirements.txt" ]; then
    DEP_TYPE=requirements DEP_DIR="$dir"
  elif [ -f "$dir/pyproject.toml" ]; then
    DEP_TYPE=pyproject DEP_DIR="$dir"
  fi
done

for dir in "$MAIN_DIR" "."; do
  if [ -f "$dir/packages.txt" ]; then
    echo "[detect] WARNING: $dir/packages.txt found - Linux (apt) packages are NOT supported on this platform and will be ignored"
    break
  fi
done
for f in Pipfile environment.yml environment.yaml; do
  for dir in "$MAIN_DIR" "."; do
    if [ -f "$dir/$f" ]; then
      if [ -z "$DEP_TYPE" ]; then
        echo "[detect] ERROR: $dir/$f found but Pipfile/conda environments are not supported. Provide requirements.txt, uv.lock or pyproject.toml."
        exit 1
      fi
      echo "[detect] WARNING: $dir/$f found but ignored ($DEP_DIR dependency file takes precedence)"
    fi
  done
done

DF="$SRC_DIR/Dockerfile.orbital"
{
  echo "FROM $BASE_IMAGE"
  echo "WORKDIR /app"
} > "$DF"

case "$DEP_TYPE" in
  uvlock)
    echo "[detect] using $DEP_DIR/uv.lock"
    {
      echo "COPY $DEP_DIR/pyproject.toml $DEP_DIR/uv.lock /tmp/deps/"
      echo "RUN cd /tmp/deps && uv export --frozen --no-dev --no-emit-project -o req.txt && uv pip install --system -r req.txt"
    } >> "$DF"
    ;;
  requirements)
    echo "[detect] using $DEP_DIR/requirements.txt"
    {
      echo "COPY $DEP_DIR/requirements.txt /tmp/deps/requirements.txt"
      echo "RUN uv pip install --system -r /tmp/deps/requirements.txt"
    } >> "$DF"
    ;;
  pyproject)
    echo "[detect] using $DEP_DIR/pyproject.toml"
    {
      echo "COPY $DEP_DIR/pyproject.toml /tmp/deps/pyproject.toml"
      echo "RUN cd /tmp/deps && uv pip compile pyproject.toml -o req.txt && uv pip install --system -r req.txt"
    } >> "$DF"
    ;;
  *)
    echo "[detect] WARNING: no dependency file found; deploying with base image packages only"
    ;;
esac

{
  echo "COPY --chown=1000:1000 . /app"
  echo "USER 1000"
  echo "ENV HOME=/home/appuser"
  echo "EXPOSE 8501"
  printf 'CMD ["streamlit", "run", "%s", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--client.showErrorDetails=false", "--server.enableXsrfProtection=true", "--browser.gatherUsageStats=false"]\n' "$MAIN_FILE"
} >> "$DF"

echo "[detect] generated Dockerfile:"
cat "$DF"
"""

BUILD_SH = r"""#!/bin/sh
set -eu
SRC_DIR="${SRC_DIR:-/workspace/src}"
echo "[build] building and pushing $IMAGE"
buildctl-daemonless.sh build \
  --frontend dockerfile.v0 \
  --local context="$SRC_DIR" \
  --local dockerfile="$SRC_DIR" \
  --opt filename=Dockerfile.orbital \
  --output type=image,name="$IMAGE",push=true,registry.insecure=true
echo "[build] pushed $IMAGE"
"""


def buildkitd_toml(registry_host: str) -> str:
    """buildkitd config allowing plain-http access to the in-cluster registry."""
    return f'[registry."{registry_host}"]\n  http = true\n'
