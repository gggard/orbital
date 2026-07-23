# Control plane image
FROM python:3.12-slim-bookworm

# https mirrors: some build environments block outbound port 80
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 app

WORKDIR /srv
ENV UV_PROJECT_ENVIRONMENT=/usr/local
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Sync the exact, locked dependency set from uv.lock straight into the
# system site-packages - reproducible, and every third-party package comes
# from a resolved, pinned lockfile entry rather than an unpinned "whatever
# pip finds today". uv itself is removed afterward; it's only needed here.
RUN pip install --no-cache-dir --only-binary :all: uv==0.11.31 \
    && uv sync --locked --no-dev --no-cache --no-editable \
    && pip uninstall -y --no-input uv

USER 1000
EXPOSE 8000
CMD ["uvicorn", "orbital.main:app", "--host", "0.0.0.0", "--port", "8000"]
