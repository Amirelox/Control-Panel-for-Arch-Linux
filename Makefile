.PHONY: run install test lint format check screenshot self-test clean

PYTHON ?= .venv/bin/python
VENV ?= .venv

$(VENV)/bin/python:
	python3 -m venv --system-site-packages $(VENV)
	$(VENV)/bin/pip install -q -e '.[dev]'

run: $(VENV)/bin/python
	./run.sh

install: $(VENV)/bin/python
	./install.sh

test: $(VENV)/bin/python
	$(PYTHON) -m pytest

lint: $(VENV)/bin/python
	$(VENV)/bin/ruff check src tests

format: $(VENV)/bin/python
	$(VENV)/bin/ruff format src tests

check: lint
	$(VENV)/bin/ruff format --check src tests
	$(PYTHON) -m pytest

self-test: $(VENV)/bin/python
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m control_panel --self-test

screenshot: $(VENV)/bin/python
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m control_panel --page Overview --screenshot docs/screenshot.png

clean:
	rm -rf build dist .pytest_cache .ruff_cache
	find src tests -name '__pycache__' -type d -prune -exec rm -rf {} +
