VENV = .venv
PYTHON = $(VENV)/Scripts/python

.PHONY: run install

run: $(VENV)
	$(PYTHON) tou-mira-installer.py

install:
	python -m venv $(VENV)
	$(PYTHON) -m pip install -r requirements.txt
