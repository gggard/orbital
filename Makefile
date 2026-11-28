VENV := .venv

$(VENV)/bin/python:
	uv venv $(VENV)

install: $(VENV)/bin/python
	uv pip install -p $(VENV)/bin/python -e '.[dev]'

run:
	$(VENV)/bin/uvicorn orbital.main:app --host 0.0.0.0 --port 8000

test:
	$(VENV)/bin/pytest -q --cov=orbital --cov-report=term-missing --cov-report=xml

lint:
	$(VENV)/bin/ruff check src tests

typecheck:
	$(VENV)/bin/mypy src

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

# CLI (cli/): installed into the same venv as the control plane so the
# contract tests can run CLI commands against the real API in-process
cli-install: install
	uv pip install -p $(VENV)/bin/python -e './cli[dev]'

cli-test:
	cd cli && ../$(VENV)/bin/pytest -q --cov=orbital_cli --cov-report=term-missing --cov-report=xml

cli-lint:
	cd cli && ../$(VENV)/bin/ruff check . ../e2e && ../$(VENV)/bin/ruff format --check . ../e2e

cli-typecheck:
	cd cli && ../$(VENV)/bin/mypy

# End-to-end tests (e2e/README.md). Local tier: the real CLI binary against a
# real control plane, Kubernetes simulated. Cluster tier: needs ORBITAL_E2E_URL.
e2e-local:
	$(VENV)/bin/pytest e2e/test_cli_local.py -v -p no:cacheprovider

e2e-cluster:
	$(VENV)/bin/pytest e2e/test_cli_cluster.py -v -p no:cacheprovider

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
	docker build -t $(IMAGE_PREFIX)/cli:$(TAG) cli

push-images:
	docker push $(IMAGE_PREFIX)/control-plane:$(TAG)
	docker push $(IMAGE_PREFIX)/console:$(TAG)
	docker push $(IMAGE_PREFIX)/cli:$(TAG)

.PHONY: install run test lint typecheck cli-install cli-test cli-lint cli-typecheck e2e-local e2e-cluster setup-minikube setup-auth ui-install ui-dev ui docs-install docs-serve docs-build images push-images
