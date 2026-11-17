PREFIX ?= $(HOME)/.local
INSTALL_TARGET_DIR ?= $(CURDIR)/target
INSTALL_TARGET ?= $(shell rustc -vV | sed -n 's/^host: //p')

RUST_TOOLS := biggie parsu kara shish cli-testing

.PHONY: install-local install-rust install-python install-cli-testing
install-local: install-rust install-python

install-cli-testing: RUST_TOOLS := cli-testing
install-rust install-cli-testing:
	cargo build --target "$(INSTALL_TARGET)" --target-dir "$(INSTALL_TARGET_DIR)" --locked --release $(addprefix -p ,$(RUST_TOOLS))
	install -d "$(PREFIX)/bin"
	for tool in $(RUST_TOOLS); do install -m 755 "$(INSTALL_TARGET_DIR)/$(INSTALL_TARGET)/release/$$tool" "$(PREFIX)/bin/" || exit; done

install-python:
	UV_TOOL_BIN_DIR="$(PREFIX)/bin" uv tool install --python 3.15 --force "$(CURDIR)/tools/cli-check"
	UV_TOOL_BIN_DIR="$(PREFIX)/bin" uv tool install --python 3.15 --force --with "$(CURDIR)/tools/cli-check" "$(CURDIR)/tools/cli-bench"
