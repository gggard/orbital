# orbital CLI image, for CI systems that run steps in containers.
# No ENTRYPOINT, so GitLab CI / Tekton can run shell scripts in it:
#   docker run --rm -e ORBITAL_URL -e ORBITAL_TOKEN ghcr.io/gggard/orbital/cli orbital apps list
FROM python:3.12-slim-bookworm

RUN useradd -m -u 1000 orbital

WORKDIR /src
ENV UV_PROJECT_ENVIRONMENT=/usr/local
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Same supply-chain posture as the control-plane image: third-party
# packages come only from pinned uv.lock entries, as prebuilt wheels.
RUN pip install --no-cache-dir --only-binary :all: uv==0.11.31 \
    && uv build --wheel -o /tmp/dist \
    && uv sync --locked --no-dev --no-cache --no-build --no-install-project \
    && uv pip install --system --no-cache --only-binary :all: --no-deps /tmp/dist/orbital_cli-*.whl \
    && pip uninstall -y --no-input uv \
    && rm -rf /tmp/dist /src

USER 1000
WORKDIR /work
CMD ["orbital", "--help"]
