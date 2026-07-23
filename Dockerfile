# Control plane image
FROM python:3.12-slim-bookworm

# https mirrors: some build environments block outbound port 80
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 app

WORKDIR /srv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install the exact, locked dependency set from uv.lock as prebuilt wheels
# only - reproducible, and rules out a third-party sdist running an
# arbitrary build script during install. orbital itself has no published
# wheel (it's this same checkout), so it's wheel-built locally first with
# `pip wheel` - packaging our own trusted source, not fetching one - and
# then installed the same binary-only way as everything else.
RUN pip install --no-cache-dir --only-binary :all: uv==0.11.31 \
    && uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt \
    && pip wheel --no-cache-dir --no-deps --wheel-dir /tmp/wheels . \
    && pip install --no-cache-dir --only-binary :all: -r requirements.txt /tmp/wheels/orbital-*.whl \
    && rm -rf requirements.txt /tmp/wheels

USER 1000
EXPOSE 8000
CMD ["uvicorn", "orbital.main:app", "--host", "0.0.0.0", "--port", "8000"]
