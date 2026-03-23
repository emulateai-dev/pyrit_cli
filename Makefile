SHELL := /bin/bash

.PHONY: help venv-create venv-install venv-update uv-install uv-update phoenix-up phoenix-down

help:
	@echo "pyrit_cli Makefile"
	@echo ""
	@echo "  make venv-create  Create local .venv"
	@echo "  make venv-install Install pyrit-cli into local .venv (editable)"
	@echo "  make venv-update  Reinstall/update pyrit-cli in local .venv (editable + --force-reinstall)"
	@echo "  make uv-install   Install pyrit-cli with uv tool (editable)"
	@echo "  make uv-update    Reinstall/update pyrit-cli with uv tool (editable + --force)"
	@echo "  make phoenix-up   Start local Phoenix via docker compose"
	@echo "  make phoenix-down Stop local Phoenix via docker compose"

venv-create:
	@if [ -x .venv/bin/python ] && .venv/bin/python -c "import sys" >/dev/null 2>&1; then \
		echo ".venv already exists"; \
	else \
		rm -rf .venv; \
		if command -v uv >/dev/null 2>&1; then \
			uv venv .venv; \
		else \
			python3 -m venv .venv; \
		fi; \
	fi

venv-install: venv-create
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install --python .venv/bin/python -e .; \
	else \
		.venv/bin/python -m pip install -e .; \
	fi

venv-update: venv-create
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install --python .venv/bin/python -e . --reinstall; \
	else \
		.venv/bin/python -m pip install -e . --force-reinstall; \
	fi

uv-install:
	uv tool install --editable .

uv-update:
	uv tool install --editable --force .

phoenix-up:
	docker compose -f docker-compose.phoenix.yml up -d

phoenix-down:
	docker compose -f docker-compose.phoenix.yml down
