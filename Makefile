PREFIX ?= $(HOME)/.local
INSTALL_TARGET_DIR ?= $(CURDIR)/target
INSTALL_TARGET ?= $(shell rustc -vV | sed -n 's/^host: //p')

RUST_TOOLS := biggie parsu kara shish cli-testing

.PHONY: install-local install-rust install-python install-cli-testing check-cli
install-local: install-rust install-python

install-cli-testing: RUST_TOOLS := cli-testing
install-rust install-cli-testing:
	cargo build --target "$(INSTALL_TARGET)" --target-dir "$(INSTALL_TARGET_DIR)" --locked --release $(addprefix -p ,$(RUST_TOOLS))
	install -d "$(PREFIX)/bin"
	for tool in $(RUST_TOOLS); do install -m 755 "$(INSTALL_TARGET_DIR)/$(INSTALL_TARGET)/release/$$tool" "$(PREFIX)/bin/" || exit; done

install-python:
	UV_TOOL_BIN_DIR="$(PREFIX)/bin" uv tool install --python 3.15 --force "$(CURDIR)/tools/cli-check"
	UV_TOOL_BIN_DIR="$(PREFIX)/bin" uv tool install --python 3.15 --force --with "$(CURDIR)/tools/cli-check" "$(CURDIR)/tools/cli-bench"

# Run the checks for one CLI from a maintainer's checkout, including working-tree edits.
export CLI
check-cli:
	uv run --locked cli-check -p "$${CLI:?set CLI to a Cargo package}"
	cargo fmt -p "$$CLI" -- --check
	cargo clippy --locked -p "$$CLI" --all-targets --all-features -- -D warnings -F unsafe_code
	cargo nextest run --locked -p "$$CLI" --all-features --profile ci
	uv run --locked local-dev record -p "$$CLI"
