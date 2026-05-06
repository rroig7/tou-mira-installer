"""
TOU-Mira Mod Auto-Installer
A simple GUI installer for the TOU-Mira Among Us mod.
"""
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from qtpy.QtCore import QObject, QThread, Qt, Signal
from qtpy.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# --- Configuration -----------------------------------------------------------
MOD_NAME = "TOU-Mira v1.6.1"
STEAM_MOD_URL = (
    "https://github.com/AU-Avengers/TOU-Mira/releases/download/"
    "1.6.1/TouMira-v1.6.1-x86-steam-itch.zip"
)
EPIC_MOD_URL = (
    "https://github.com/AU-Avengers/TOU-Mira/releases/download/"
    "1.6.1/TouMira-v1.6.1-x64-epic-msstore.zip"
)
EPIC_STARTER_URL = (
    "https://github.com/whichtwix/EpicGamesStarter/releases/download/"
    "1.1.0/EpicGamesStarter.exe.zip"
)
AMONG_US_FOLDER_NAME = "Among Us"
AMONG_US_EXE = "Among Us.exe"
BEPINEX_FOLDER = "BepInEx"
EPIC_INSTALL_FOLDER_NAME = "Among Us - TOU Mira"
PLATFORM_STEAM = "steam"
PLATFORM_EPIC = "epic"


# --- Steam detection ---------------------------------------------------------
def _get_steam_path_windows():
    """Return the Steam install path from the Windows registry, or None."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    candidates = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ]
    for hkey, subkey, value_name in candidates:
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                if value and os.path.isdir(value):
                    return value
        except OSError:
            continue
    return None


def _get_steam_libraries(steam_path):
    """Parse libraryfolders.vdf to discover all Steam library locations."""
    libraries = [steam_path]
    vdf_paths = [
        Path(steam_path) / "steamapps" / "libraryfolders.vdf",
        Path(steam_path) / "config" / "libraryfolders.vdf",
    ]
    for vdf_path in vdf_paths:
        if not vdf_path.exists():
            continue
        try:
            content = vdf_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s*"([^"]+)"', content):
            lib = match.group(1).encode("utf-8").decode("unicode_escape")
            if os.path.isdir(lib) and lib not in libraries:
                libraries.append(lib)
    return libraries


def find_among_us():
    """Try to locate the Steam Among Us install folder. Return path str or None."""
    candidates = []

    steam_path = _get_steam_path_windows()
    if steam_path:
        for lib in _get_steam_libraries(steam_path):
            candidates.append(Path(lib) / "steamapps" / "common" / AMONG_US_FOLDER_NAME)

    fallbacks = [
        r"C:\Program Files (x86)\Steam\steamapps\common",
        r"C:\Program Files\Steam\steamapps\common",
        r"D:\Steam\steamapps\common",
        r"D:\SteamLibrary\steamapps\common",
        r"E:\Steam\steamapps\common",
        r"E:\SteamLibrary\steamapps\common",
    ]
    for base in fallbacks:
        candidates.append(Path(base) / AMONG_US_FOLDER_NAME)

    for path in candidates:
        if path.is_dir() and (path / AMONG_US_EXE).exists():
            return str(path)
    for path in candidates:
        if path.is_dir():
            return str(path)
    return None


# --- Epic Games detection ----------------------------------------------------
def find_epic_among_us():
    """Try to locate the Epic Games Among Us install folder. Return path str or None."""
    candidates = []

    # Parse Epic Games Launcher .item manifests for the exact install path
    manifests_dir = Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests")
    if manifests_dir.exists():
        for manifest_file in manifests_dir.glob("*.item"):
            try:
                data = json.loads(manifest_file.read_text(encoding="utf-8", errors="ignore"))
                if "Among Us" in data.get("DisplayName", ""):
                    loc = data.get("InstallLocation", "")
                    if loc:
                        candidates.append(Path(loc))
            except Exception:
                continue

    fallbacks = [
        r"C:\Program Files\Epic Games",
        r"C:\Program Files (x86)\Epic Games",
        r"D:\Epic Games",
        r"D:\EpicGames",
        r"E:\Epic Games",
        r"E:\EpicGames",
    ]
    for base in fallbacks:
        candidates.append(Path(base) / AMONG_US_FOLDER_NAME)

    for path in candidates:
        if path.is_dir() and (path / AMONG_US_EXE).exists():
            return str(path)
    for path in candidates:
        if path.is_dir():
            return str(path)
    return None


# --- Background worker -------------------------------------------------------
class InstallWorker(QObject):
    """Downloads and installs the mod on a worker thread."""

    progress = Signal(int)
    log = Signal(str)
    finished = Signal(bool, str)  # success, message

    def __init__(self, platform, install_path, mod_url,
                 source_path=None, starter_url=None):
        super().__init__()
        self.platform = platform
        self.install_path = install_path
        self.mod_url = mod_url
        self.source_path = source_path  # Epic only: original Among Us folder
        self.starter_url = starter_url  # Epic only

    def _setup_opener(self):
        """Install a global urllib opener that skips SSL verification."""
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl_ctx)
        )
        opener.addheaders = [("User-Agent", "TOU-Mira-Installer/1.0")]
        urllib.request.install_opener(opener)

    def _download_mod_zip(self, tmp_zip, progress_start, progress_end):
        """Download mod zip with progress from progress_start to progress_end."""
        self.log.emit(f"Downloading mod from:\n  {self.mod_url}")
        span = progress_end - progress_start

        def report_hook(blocks, block_size, total_size):
            if total_size > 0:
                pct = progress_start + min(int(blocks * block_size * span / total_size), span)
                self.progress.emit(pct)

        urllib.request.urlretrieve(self.mod_url, tmp_zip, reporthook=report_hook)
        self.progress.emit(progress_end)
        self.log.emit("Download complete.")

    def _extract_and_copy(self, tmp_zip, dest_root, progress_start, progress_end):
        """Extract zip into dest_root, walking past any wrapper folders."""
        tmp_extract = None
        try:
            tmp_extract = tempfile.mkdtemp(prefix="toumira_extract_")
            self.log.emit("Extracting archive…")
            extract_span = int((progress_end - progress_start) * 0.6)
            copy_span = (progress_end - progress_start) - extract_span

            with zipfile.ZipFile(tmp_zip, "r") as zf:
                members = zf.namelist()
                total = max(len(members), 1)
                for i, member in enumerate(members):
                    zf.extract(member, tmp_extract)
                    pct = progress_start + int((i + 1) * extract_span / total)
                    self.progress.emit(min(pct, progress_start + extract_span))

            content_root = Path(tmp_extract)
            depth = 0
            while True:
                entries = list(content_root.iterdir())
                if len(entries) == 1 and entries[0].is_dir():
                    content_root = entries[0]
                    depth += 1
                else:
                    break
            if depth > 0:
                self.log.emit(
                    f"Detected {depth} wrapper folder(s); "
                    f"using contents of '{content_root.name}'."
                )

            entries = list(content_root.iterdir())
            if not entries:
                raise RuntimeError("Archive appears to be empty after extraction.")
            total = max(len(entries), 1)
            copy_base = progress_start + extract_span
            for i, entry in enumerate(entries):
                dst = Path(dest_root) / entry.name
                if entry.is_dir():
                    shutil.copytree(entry, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(entry, dst)
                pct = copy_base + int((i + 1) * copy_span / total)
                self.progress.emit(min(pct, progress_end))
        finally:
            if tmp_extract and os.path.exists(tmp_extract):
                shutil.rmtree(tmp_extract, ignore_errors=True)

    def run(self):
        if self.platform == PLATFORM_EPIC:
            self._run_epic()
        else:
            self._run_steam()

    def _run_steam(self):
        tmp_zip = None
        try:
            self._setup_opener()

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_zip = tmp.name

            self._download_mod_zip(tmp_zip, progress_start=0, progress_end=75)
            self.log.emit(f"Installing files to:\n  {self.install_path}")
            self._extract_and_copy(tmp_zip, self.install_path,
                                   progress_start=75, progress_end=100)

            self.progress.emit(100)
            self.log.emit("Installation complete.")
            self.finished.emit(True, f"{MOD_NAME} installed successfully!")
        except Exception as e:  # noqa: BLE001
            self.finished.emit(False, f"Installation failed: {e}")
        finally:
            if tmp_zip and os.path.exists(tmp_zip):
                try:
                    os.unlink(tmp_zip)
                except OSError:
                    pass

    def _run_epic(self):
        tmp_zip = None
        try:
            self._setup_opener()
            dest = Path(self.install_path)

            # Step 1: Copy Among Us folder to destination (0–30%)
            self.log.emit(
                f"Copying Among Us from:\n  {self.source_path}\n"
                f"  → {self.install_path}\n"
                "This may take a moment…"
            )
            if dest.exists():
                self.log.emit(f"Removing existing '{dest.name}' folder…")
                shutil.rmtree(dest)

            # Count files first so we can report per-file progress
            source = Path(self.source_path)
            all_files = [f for f in source.rglob("*") if f.is_file()]
            total_files = max(len(all_files), 1)
            copied_files = [0]

            def _copy_fn(src, dst):
                shutil.copy2(src, dst)
                copied_files[0] += 1
                self.progress.emit(min(int(copied_files[0] * 30 / total_files), 30))

            shutil.copytree(self.source_path, str(dest), copy_function=_copy_fn)
            self.progress.emit(30)
            self.log.emit("Among Us folder copied.")

            # Step 2: Download and unzip EpicGamesStarter.exe (30–40%)
            self.log.emit("Downloading EpicGamesStarter.exe…")
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as starter_tmp:
                starter_zip = starter_tmp.name
            try:
                urllib.request.urlretrieve(self.starter_url, starter_zip)
                with zipfile.ZipFile(starter_zip, "r") as zf:
                    exe_names = [n for n in zf.namelist() if n.lower().endswith(".exe")]
                    if not exe_names:
                        raise RuntimeError("EpicGamesStarter zip contains no .exe file.")
                    zf.extract(exe_names[0], str(dest))
                    extracted = dest / exe_names[0]
                    final = dest / "EpicGamesStarter.exe"
                    if extracted != final:
                        extracted.rename(final)
            finally:
                if os.path.exists(starter_zip):
                    try:
                        os.unlink(starter_zip)
                    except OSError:
                        pass
            self.progress.emit(40)
            self.log.emit("EpicGamesStarter.exe downloaded.")

            # Step 3: Download mod zip (40–75%)
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_zip = tmp.name
            self._download_mod_zip(tmp_zip, progress_start=40, progress_end=75)

            # Step 4: Extract and copy mod files (75–100%)
            self.log.emit(f"Installing mod files to:\n  {self.install_path}")
            self._extract_and_copy(tmp_zip, self.install_path,
                                   progress_start=75, progress_end=100)

            self.progress.emit(100)
            self.log.emit("Installation complete.")
            self.finished.emit(
                True,
                f"{MOD_NAME} installed successfully!\n\n"
                f"Launch the game using EpicGamesStarter.exe inside:\n{self.install_path}"
            )
        except Exception as e:  # noqa: BLE001
            self.finished.emit(False, f"Installation failed: {e}")
        finally:
            if tmp_zip and os.path.exists(tmp_zip):
                try:
                    os.unlink(tmp_zip)
                except OSError:
                    pass


# --- Main window -------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{MOD_NAME} Installer")
        self.resize(680, 540)

        self.install_path = None   # Steam: Among Us dir; Epic: destination dir
        self.epic_source_path = None  # Epic: original Among Us dir in Program Files
        self.thread = None
        self.worker = None

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Title
        title = QLabel(f"<h2>{MOD_NAME} Installer</h2>")
        layout.addWidget(title)

        subtitle = QLabel(
            "This will download and install the TOU-Mira mod into your Among Us folder."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # --- Platform selector ---
        platform_box = QGroupBox("Platform")
        platform_layout = QHBoxLayout(platform_box)
        self.btn_steam = QRadioButton("Steam")
        self.btn_epic = QRadioButton("Epic Games")
        self.btn_steam.setChecked(True)
        self._platform_group = QButtonGroup(self)
        self._platform_group.addButton(self.btn_steam)
        self._platform_group.addButton(self.btn_epic)
        platform_layout.addWidget(self.btn_steam)
        platform_layout.addWidget(self.btn_epic)
        platform_layout.addStretch()
        layout.addWidget(platform_box)

        # --- Steam path row ---
        self._steam_widget = QWidget()
        steam_row = QHBoxLayout(self._steam_widget)
        steam_row.setContentsMargins(0, 0, 0, 0)
        steam_row.addWidget(QLabel("Among Us folder:"))
        self.steam_path_edit = QLineEdit()
        self.steam_path_edit.setReadOnly(True)
        steam_row.addWidget(self.steam_path_edit, 1)
        self.steam_browse_btn = QPushButton("Browse…")
        self.steam_browse_btn.clicked.connect(self._browse_steam)
        steam_row.addWidget(self.steam_browse_btn)
        layout.addWidget(self._steam_widget)

        # --- Epic path rows ---
        self._epic_widget = QWidget()
        epic_rows = QVBoxLayout(self._epic_widget)
        epic_rows.setContentsMargins(0, 0, 0, 0)
        epic_rows.setSpacing(6)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Epic Among Us folder:"))
        self.epic_source_edit = QLineEdit()
        self.epic_source_edit.setReadOnly(True)
        source_row.addWidget(self.epic_source_edit, 1)
        self.epic_source_btn = QPushButton("Browse…")
        self.epic_source_btn.clicked.connect(self._browse_epic_source)
        source_row.addWidget(self.epic_source_btn)
        epic_rows.addLayout(source_row)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Install to:"))
        self.epic_dest_edit = QLineEdit()
        self.epic_dest_edit.setReadOnly(True)
        dest_row.addWidget(self.epic_dest_edit, 1)
        self.epic_dest_btn = QPushButton("Browse…")
        self.epic_dest_btn.clicked.connect(self._browse_epic_dest)
        dest_row.addWidget(self.epic_dest_btn)
        epic_rows.addLayout(dest_row)

        dest_hint = QLabel(
            f'A new "{EPIC_INSTALL_FOLDER_NAME}" folder will be created at this location. '
            "It cannot be inside Program Files."
        )
        dest_hint.setWordWrap(True)
        dest_hint.setStyleSheet("color: gray; font-size: 11px;")
        epic_rows.addWidget(dest_hint)

        layout.addWidget(self._epic_widget)
        self._epic_widget.setVisible(False)

        # Log
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box, 1)

        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        # Install button
        self.install_btn = QPushButton("Install Mod")
        self.install_btn.setMinimumHeight(40)
        font = self.install_btn.font()
        font.setBold(True)
        self.install_btn.setFont(font)
        self.install_btn.clicked.connect(self.start_install)
        layout.addWidget(self.install_btn)

        self.setCentralWidget(central)

        # Wire platform toggle
        self.btn_steam.toggled.connect(self._on_platform_changed)
        self.btn_epic.toggled.connect(self._on_platform_changed)

        self._detect_paths()

    # -- helpers --
    def log(self, message):
        self.log_box.append(message)

    def _current_platform(self):
        return PLATFORM_STEAM if self.btn_steam.isChecked() else PLATFORM_EPIC

    def _on_platform_changed(self):
        is_epic = self._current_platform() == PLATFORM_EPIC
        self._steam_widget.setVisible(not is_epic)
        self._epic_widget.setVisible(is_epic)
        self.log_box.clear()
        self._detect_paths()

    def _detect_paths(self):
        if self._current_platform() == PLATFORM_STEAM:
            self.log("Searching for Steam Among Us installation…")
            path = find_among_us()
            if path:
                self.install_path = path
                self.steam_path_edit.setText(path)
                self.log(f"Found Among Us at: {path}")
            else:
                self.steam_path_edit.setText("(not found — please browse)")
                self.log(
                    "Could not auto-detect Among Us. "
                    "Please use Browse to select your Among Us folder."
                )
        else:
            self.log("Searching for Epic Games Among Us installation…")
            source = find_epic_among_us()
            if source:
                self.epic_source_path = source
                self.epic_source_edit.setText(source)
                self.log(f"Found Among Us (Epic) at: {source}")
            else:
                self.epic_source_edit.setText("(not found — please browse)")
                self.log(
                    "Could not auto-detect Epic Games Among Us. "
                    "Please use Browse to select the source folder."
                )
            # Default destination: Desktop\Among Us - TOU Mira
            default_dest = str(Path.home() / "Desktop" / EPIC_INSTALL_FOLDER_NAME)
            self.install_path = default_dest
            self.epic_dest_edit.setText(default_dest)
            self.log(f"Default install location: {default_dest}")

    # -- browse callbacks --
    def _browse_steam(self):
        start = self.install_path or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self, "Select your Among Us folder", start
        )
        if folder:
            self.install_path = folder
            self.steam_path_edit.setText(folder)
            self.log(f"Selected folder: {folder}")

    def _browse_epic_source(self):
        start = self.epic_source_path or r"C:\Program Files\Epic Games"
        folder = QFileDialog.getExistingDirectory(
            self, "Select your Epic Games Among Us folder", start
        )
        if folder:
            self.epic_source_path = folder
            self.epic_source_edit.setText(folder)
            self.log(f"Epic source folder: {folder}")

    def _browse_epic_dest(self):
        start = str(Path(self.install_path).parent) if self.install_path else os.path.expanduser("~")
        parent = QFileDialog.getExistingDirectory(
            self,
            f'Select where to create the "{EPIC_INSTALL_FOLDER_NAME}" folder',
            start,
        )
        if parent:
            dest = str(Path(parent) / EPIC_INSTALL_FOLDER_NAME)
            self.install_path = dest
            self.epic_dest_edit.setText(dest)
            self.log(f"Install destination: {dest}")

    # -- install flow --
    def start_install(self):
        platform = self._current_platform()

        if not self.install_path or (
            platform == PLATFORM_STEAM and not os.path.isdir(self.install_path)
        ):
            QMessageBox.warning(
                self, "No folder selected",
                "Please select your Among Us folder first."
            )
            return

        if platform == PLATFORM_STEAM:
            self._start_steam_install()
        else:
            self._start_epic_install()

    def _start_steam_install(self):
        if not (Path(self.install_path) / AMONG_US_EXE).exists():
            reply = QMessageBox.question(
                self, "Among Us.exe not found",
                f"The selected folder does not contain '{AMONG_US_EXE}'.\n\n"
                "Continue anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        bepinex = Path(self.install_path) / BEPINEX_FOLDER
        if bepinex.exists():
            reply = QMessageBox.question(
                self, "Mod already installed",
                f"A '{BEPINEX_FOLDER}' folder was found — the mod appears "
                "to already be installed.\n\nReinstall and overwrite it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self.log("Installation cancelled by user.")
                return
            self.log(f"Removing existing {BEPINEX_FOLDER} folder…")
            try:
                shutil.rmtree(bepinex)
            except OSError as e:
                QMessageBox.critical(
                    self, "Error",
                    f"Could not remove existing {BEPINEX_FOLDER} folder:\n{e}\n\n"
                    "Make sure Among Us is closed and try again."
                )
                return

        self._launch_worker(
            platform=PLATFORM_STEAM,
            install_path=self.install_path,
            mod_url=STEAM_MOD_URL,
        )

    def _start_epic_install(self):
        if not self.epic_source_path or not os.path.isdir(self.epic_source_path):
            QMessageBox.warning(
                self, "No source folder",
                "Please select your Epic Games Among Us folder first."
            )
            return

        if not (Path(self.epic_source_path) / AMONG_US_EXE).exists():
            reply = QMessageBox.question(
                self, "Among Us.exe not found",
                f"The source folder does not contain '{AMONG_US_EXE}'.\n\n"
                "Continue anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        dest = Path(self.install_path)
        # Warn if inside Program Files
        try:
            dest.relative_to(Path(r"C:\Program Files"))
            in_program_files = True
        except ValueError:
            try:
                dest.relative_to(Path(r"C:\Program Files (x86)"))
                in_program_files = True
            except ValueError:
                in_program_files = False

        if in_program_files:
            QMessageBox.warning(
                self, "Invalid destination",
                "The destination folder is inside Program Files.\n\n"
                "EpicGamesStarter cannot launch the game from there. "
                "Please choose a different location such as your Desktop."
            )
            return

        if dest.exists():
            reply = QMessageBox.question(
                self, "Folder already exists",
                f'"{dest.name}" already exists at this location.\n\n'
                "Delete it and reinstall?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self.log("Installation cancelled by user.")
                return

        self._launch_worker(
            platform=PLATFORM_EPIC,
            install_path=self.install_path,
            mod_url=EPIC_MOD_URL,
            source_path=self.epic_source_path,
            starter_url=EPIC_STARTER_URL,
        )

    def _launch_worker(self, **kwargs):
        self.install_btn.setEnabled(False)
        self.steam_browse_btn.setEnabled(False)
        self.epic_source_btn.setEnabled(False)
        self.epic_dest_btn.setEnabled(False)
        self.btn_steam.setEnabled(False)
        self.btn_epic.setEnabled(False)
        self.install_btn.setText("Installing…")
        self.progress.setValue(0)

        self.thread = QThread()
        self.worker = InstallWorker(**kwargs)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.log.connect(self.log)
        self.worker.finished.connect(self.on_install_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def on_install_finished(self, success, message):
        self.log(message)
        self.install_btn.setEnabled(True)
        self.steam_browse_btn.setEnabled(True)
        self.epic_source_btn.setEnabled(True)
        self.epic_dest_btn.setEnabled(True)
        self.btn_steam.setEnabled(True)
        self.btn_epic.setEnabled(True)
        self.install_btn.setText("Install Mod")
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.critical(self, "Error", message)


# --- Entry point -------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    exit_code = app.exec() if hasattr(app, "exec") else app.exec_()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
