VENV = .venv
PYTHON = $(VENV)/Scripts/python
PIP = $(PYTHON) -m pip

ENTRY = main.py
ICON = assets/icon.png
# Read from toumira/config.py so the exe name always matches the embedded version
VERSION = $(shell python -c "import runpy; print(runpy.run_path('toumira/config.py')['APP_VERSION'])")
APP_NAME = TOU-Mira-Installer-v$(VERSION)

.PHONY: run install build clean

run: $(VENV)
	$(PYTHON) $(ENTRY)

install:
	python -m venv $(VENV)
	$(PIP) install -r requirements.txt

build: $(VENV)
	$(PIP) install pyinstaller pillow
	$(PYTHON) -m PyInstaller --noconfirm --onefile --windowed \
		--name "$(APP_NAME)" --icon=$(ICON) $(ENTRY)

clean:
	powershell -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build,dist; Remove-Item -Force -ErrorAction SilentlyContinue *.spec; Get-ChildItem . -Recurse -Directory -Filter __pycache__ | Where-Object FullName -notlike '*\$(VENV)\*' | Remove-Item -Recurse -Force"
