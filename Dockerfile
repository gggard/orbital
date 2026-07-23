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
# only - reproducible, and rules out arbitrary sdist build-script execution
# for third-party deps during install. orbital itself has no wheel to fetch
# (it's this same checkout being packaged), so it's built from source here -
# that's just our own setup.py running, not an untrusted download.
RUN pip install --no-cache-dir --only-binary :all: uv==0.11.31 \
    && uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.lock.txt \
    && uv pip install --system --no-cache --only-binary :all: -r requirements.lock.txt \
    && uv pip install --system --no-cache --no-deps . \
    && rm requirements.lock.txt

USER 1000
EXPOSE 8000
CMD ["uvicorn", "orbital.main:app", "--host", "0.0.0.0", "--port", "8000"]
