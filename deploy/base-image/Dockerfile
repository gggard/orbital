# Shared base image for hosted Streamlit apps (SPEC §5.2).
# One image per supported Python version; apps layer their pip deps on top.
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_NO_CACHE=1

RUN pip install uv streamlit \
    && useradd -m -u 1000 -U appuser

ENV HOME=/home/appuser
