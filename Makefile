# Makefile - developer entrypoints. Run `make` (no target) to list them.
# CI (.github/workflows) delegates the stack-specific work here, so the
# workflows stay generic: fill in ci-build and ci-test for your stack and the
# same commands run locally and in CI.

PYTHON ?= python3

.DEFAULT_GOAL := help
.PHONY: help hygiene verify ci-build ci-test apply-ruleset install-hooks

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	 awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

hygiene: ## Doc style + link checks (fast, no build toolchain needed)
	$(PYTHON) scripts/check_doc_style.py
	$(PYTHON) scripts/check_doc_links.py

verify: hygiene ci-build ci-test ## The local pre-push gate: run before every push
	@echo "verify: OK. Now run /review-gate before pushing."

ci-build: ## Build everything. STUB - wire up your stack.
	@echo "ci-build: no build configured yet. Edit the Makefile."
	@# Examples (replace the echo above):
	@#   dotnet build -c Release
	@#   npm ci && npm run build
	@#   flutter build apk --debug

ci-test: ## Run the test estate. STUB - wire up your stack.
	@echo "ci-test: no tests configured yet. Edit the Makefile."
	@#   dotnet test
	@#   npm test
	@#   flutter test

apply-ruleset: ## Apply the main-protection ruleset to this repo (needs gh + admin)
	@repo=$$(gh repo view --json nameWithOwner -q .nameWithOwner); \
	 echo "Applying main-protection ruleset to $$repo ..."; \
	 gh api -X POST "repos/$$repo/rulesets" --input .github/rulesets/main-protection.json

install-hooks: ## Point git at the repo's hooks (one-time)
	git config core.hooksPath scripts/git-hooks
	@echo "Hooks installed from scripts/git-hooks."
