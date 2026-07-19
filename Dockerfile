# Control plane image
FROM python:3.12-slim-bookworm

# https mirrors: some build environments block outbound port 80
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 app

WORKDIR /srv
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

USER 1000
EXPOSE 8000
CMD ["uvicorn", "orbital.main:app", "--host", "0.0.0.0", "--port", "8000"]
