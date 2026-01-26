SHELL:=/bin/bash
.DEFAULT_GOAL=_help

.PHONY: _help
_help:
	@printf "\nUsage: make <command>, valid commands:\n\n"
	@grep -h "##H@@" $(MAKEFILE_LIST) | grep -v IGNORE_ME | sed -e 's/##H@@//' | column -t -s $$'\t'

# help: ## Show this help
# 	@grep -Eh '\s##\s' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'


-include .env

.PHONY: test/e2e
test/e2e:	##H@@ E2E/Smoke test for Bertrand Russell (LZDB-KV4)
	@if [ -z "${FAMILYSEARCH_USER}" ]; then \
		echo "⚠️  Skipping E2E test: FAMILYSEARCH_USER not set"; \
		exit 0; \
	fi
	mkdir -p .tmp
	which python
	coverage run -p -m getmyancestors --verbose \
		-u "${FAMILYSEARCH_USER}"  `# password goes in .env file` \
		--no-cache-control \
		-i LZDB-KV4 -a 0 \
		--outfile .tmp/russell_smoke_test.ged
	echo "✓ Script completed successfully"
	echo "File size: $$(wc -c < .tmp/russell_smoke_test.ged) bytes"
	echo "Line count: $$(wc -l < .tmp/russell_smoke_test.ged) lines"
	echo "--- First 20 lines of output ---"
	head -n 20 .tmp/russell_smoke_test.ged
	echo "--- Last 5 lines of output ---"
	tail -n 5 .tmp/russell_smoke_test.ged


.PHONY: test/unit
test/unit:	##H@@ Run unit tests
	coverage run -p -m pytest getmyancestors/tests

.PHONY: test/
test/:	##H@@ Run unit & E2E tests
test/: test/unit test/e2e

.PHONY: coverage
coverage:	##H@@ Combine all coverage data and show report
	-coverage combine
	coverage report


REMOTE_HEAD ?= origin/master
PY_CHANGED_FILES ?= $(shell git diff --name-only --diff-filter=MACU $(REMOTE_HEAD) '*.py')

.PHONY: format
format:	##H@@ Format with black & isort
	isort ${PY_CHANGED_FILES}
	black ${PY_CHANGED_FILES}
	ruff check --fix --exit-zero ${PY_CHANGED_FILES}

.PHONY: lint
lint:	##H@@ Lint with flake8
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# x-fail as of Dec 2025
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	ruff check --exit-zero ${PY_CHANGED_FILES}
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# Disabled checks, for now
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# pylint ${PY_CHANGED_FILES}
	# mypy ${PY_CHANGED_FILES}


.PHONY: clean
clean:	##H@@ Clean up build files/cache
	rm -rf *.egg-info build dist .coverage .coverage.*
	rm -rf .tmp .pytest_cache .ruff_cache .mypy_cache
	find . \( -name .venv -prune \) \
		-o \( -name __pycache__ -o -name "*.pyc" -o -name "*.pyo" -o -name "*.pyd" -o -name "*.so" \) \
		-exec rm -rf {} +
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name "*.so" -delete
	echo "✓ Cleaned build files, caches, and test artifacts"
