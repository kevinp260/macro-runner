# Ubuntu / Linux developer convenience targets; Windows builds use PowerShell (see README).
PYTHON ?= python3
VENV ?= .venv
PIPX ?= pipx
APP_NAME ?= MacroRunner
VENV_PYTHON := $(VENV)/bin/python

.PHONY: help setup run test build deb install uninstall

help:
	@echo 'Ubuntu targets:'
	@echo '  make install           Install/update app via pipx; prompts for missing APT packages'
	@echo '  make uninstall         Remove installed pipx app and desktop launcher'
	@echo '  make setup             Create local venv and install app for development'
	@echo '  make run               Run development version (after setup)'
	@echo '  make test              Run unit tests (after setup)'
	@echo '  make build             Build optional standalone Linux executable (after setup)'
	@echo '  make deb               Package executable as Ubuntu .deb (after build)'
	@echo 'Variables: PYTHON=python3 VENV=.venv APP_NAME=MacroRunner'

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install -e .

run:
	$(VENV_PYTHON) macro_runner.py

test:
	QT_QPA_PLATFORM=offscreen $(VENV_PYTHON) -m unittest discover -s tests -v

build:
	$(VENV_PYTHON) -m pip install pyinstaller
	$(VENV_PYTHON) -m PyInstaller --noconfirm --clean MacroRunner.spec
	@echo 'Linux executable: dist/$(APP_NAME)'

deb:
	bash packaging/build-deb.sh

install:
	bash install-ubuntu.sh

uninstall:
	$(PIPX) uninstall macro-runner-desktop
	rm -f $(HOME)/.local/share/applications/macro-runner.desktop
