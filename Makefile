.PHONY: help install uninstall test lint fmt check dist clean

PYTHON ?= python3
PREFIX ?= $(HOME)/.local

help:
	@echo "make install     install for the current user (no root needed)"
	@echo "make uninstall   reverse the installation"
	@echo "make test        run the unit tests"
	@echo "make lint        byte-compile and syntax-check everything"
	@echo "make dist        build a source tarball in dist/"
	@echo "make clean       remove build artefacts"

install:
	./install.sh

uninstall:
	./uninstall.sh

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

lint:
	$(PYTHON) -m compileall -q src bin
	@for f in install.sh uninstall.sh; do bash -n $$f && echo "bash -n $$f ok"; done

fmt:
	@command -v ruff >/dev/null && ruff format src || echo "ruff not installed"

dist:
	@mkdir -p dist
	@git archive --format=tar.gz --prefix=headset-button/ \
		-o dist/headset-button.tar.gz HEAD 2>/dev/null \
		|| tar --exclude=dist --exclude=.git -czf dist/headset-button.tar.gz .
	@echo "wrote dist/headset-button.tar.gz"

clean:
	rm -rf dist build *.egg-info
	find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
