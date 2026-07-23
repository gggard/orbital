VENV := .venv

$(VENV)/bin/python:
	uv venv $(VENV)

install: $(VENV)/bin/python
	uv pip install -p $(VENV)/bin/python -e '.[dev]'

run:
	$(VENV)/bin/uvicorn orbital.main:app --host 0.0.0.0 --port 8000

test:
	$(VENV)/bin/pytest -q --cov=orbital --cov-report=term-missing --cov-report=xml

setup-minikube:
	bash deploy/minikube/setup.sh

setup-auth:
	bash deploy/auth/setup-auth.sh

ui-install:
	cd ui && npm install

ui-dev:
	cd ui && npm run dev

ui:
	cd ui && npm run build && npm run start -- --port 3000

docs-install: $(VENV)/bin/python
	uv pip install -p $(VENV)/bin/python -e '.[docs]'

docs-serve:
	$(VENV)/bin/mkdocs serve

docs-build:
	$(VENV)/bin/mkdocs build --strict

# Container images for cluster deployment (see docs/INSTALL.md)
IMAGE_PREFIX ?= localhost:45000/orbital
TAG ?= 0.1.0

images:
	docker build -t $(IMAGE_PREFIX)/control-plane:$(TAG) .
	docker build -t $(IMAGE_PREFIX)/console:$(TAG) ui

push-images:
	docker push $(IMAGE_PREFIX)/control-plane:$(TAG)
	docker push $(IMAGE_PREFIX)/console:$(TAG)

.PHONY: install run test setup-minikube setup-auth ui-install ui-dev ui docs-install docs-serve docs-build images push-images
