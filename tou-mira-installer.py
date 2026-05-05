"""
TOU-Mira Mod Auto-Installer
A simple GUI installer for the TOU-Mira Among Us mod.
"""
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from qtpy.QtCore import QObject, QThread, Qt, Signal
from qtpy.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# --- Configuration -----------------------------------------------------------
MOD_NAME = "TOU-Mira v1.6.1"
MOD_URL = (
    "https://github.com/AU-Avengers/TOU-Mira/releases/download/"
    "1.6.1/TouMira-v1.6.1-x86-steam-itch.zip"
)
AMONG_US_FOLDER_NAME = "Among Us"
AMONG_US_EXE = "Among Us.exe"
BEPINEX_FOLDER = "BepInEx"


# --- Steam / Among Us detection ---------------------------------------------
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
        # libraryfolders.vdf stores each library as: "path"  "C:\\Some\\Path"
        for match in re.finditer(r'"path"\s*"([^"]+)"', content):
            lib = match.group(1).encode("utf-8").decode("unicode_escape")
            if os.path.isdir(lib) and lib not in libraries:
                libraries.append(lib)
    return libraries


def find_among_us():
    """Try to locate the Among Us install folder. Return path str or None."""
    candidates = []

    steam_path = _get_steam_path_windows()
    if steam_path:
        for lib in _get_steam_libraries(steam_path):
            candidates.append(Path(lib) / "steamapps" / "common" / AMONG_US_FOLDER_NAME)

    # Fallback common paths (cover users with non-standard installs)
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

    # Prefer folders that actually contain the game executable
    for path in candidates:
        if path.is_dir() and (path / AMONG_US_EXE).exists():
            return str(path)
    for path in candidates:
        if path.is_dir():
            return str(path)
    return None


# --- Background worker -------------------------------------------------------
class InstallWorker(QObject):
    """Downloads and extracts the mod on a worker thread."""

    progress = Signal(int)
    log = Signal(str)
    finished = Signal(bool, str)  # success, message

    def __init__(self, install_path, mod_url):
        super().__init__()
        self.install_path = install_path
        self.mod_url = mod_url

    def run(self):
        tmp_zip = None
        tmp_extract = None
        try:
            # Set a User-Agent so GitHub doesn't reject the request
            opener = urllib.request.build_opener()
            opener.addheaders = [("User-Agent", "TOU-Mira-Installer/1.0")]
            urllib.request.install_opener(opener)

            self.log.emit(f"Downloading mod from:\n  {self.mod_url}")

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_zip = tmp.name

            def report_hook(blocks, block_size, total_size):
                if total_size > 0:
                    downloaded = blocks * block_size
                    pct = min(int(downloaded * 75 / total_size), 75)
                    self.progress.emit(pct)

            urllib.request.urlretrieve(self.mod_url, tmp_zip, reporthook=report_hook)
            self.progress.emit(75)
            self.log.emit("Download complete.")

            # Extract into a temp directory first so we can detect and skip
            # any wrapper folders (e.g. zip contains "tou/BepInEx/..." instead
            # of "BepInEx/..." at the top level).
            tmp_extract = tempfile.mkdtemp(prefix="toumira_extract_")
            self.log.emit("Extracting archive…")
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                members = zf.namelist()
                total = max(len(members), 1)
                for i, member in enumerate(members):
                    zf.extract(member, tmp_extract)
                    pct = 75 + int((i + 1) * 15 / total)  # 75 -> 90
                    self.progress.emit(min(pct, 90))

            # Walk past any wrapper folders. Keep descending while the current
            # directory has exactly one entry and that entry is a directory.
            # Handles cases like:
            #   zip/BepInEx/...           (no wrapper)        -> stays at root
            #   zip/tou/BepInEx/...       (one wrapper)       -> descends 1x
            #   zip/tou/tou/BepInEx/...   (nested wrapper)    -> descends 2x
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

            # Copy contents into the Among Us folder, merging with anything
            # already there (dirs_exist_ok=True overwrites file-by-file).
            self.log.emit(f"Installing files to:\n  {self.install_path}")
            entries = list(content_root.iterdir())
            if not entries:
                raise RuntimeError("Archive appears to be empty after extraction.")
            total = max(len(entries), 1)
            dest_root = Path(self.install_path)
            for i, entry in enumerate(entries):
                dest = dest_root / entry.name
                if entry.is_dir():
                    shutil.copytree(entry, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(entry, dest)
                pct = 90 + int((i + 1) * 10 / total)  # 90 -> 100
                self.progress.emit(min(pct, 100))

            self.progress.emit(100)
            self.log.emit("Installation complete.")
            self.finished.emit(True, f"{MOD_NAME} installed successfully!")
        except Exception as e:  # noqa: BLE001 - user-facing message
            self.finished.emit(False, f"Installation failed: {e}")
        finally:
            if tmp_zip and os.path.exists(tmp_zip):
                try:
                    os.unlink(tmp_zip)
                except OSError:
                    pass
            if tmp_extract and os.path.exists(tmp_extract):
                shutil.rmtree(tmp_extract, ignore_errors=True)


# --- Main window -------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{MOD_NAME} Installer")
        self.resize(640, 460)

        self.install_path = None
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
            "This will download and install the TOU-Mira mod into your "
            "Among Us folder."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Path row
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Among Us folder:"))
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        path_row.addWidget(self.path_edit, 1)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(self.browse_folder)
        path_row.addWidget(self.browse_btn)
        layout.addLayout(path_row)

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

        self.detect_among_us()

    # -- helpers --
    def log(self, message):
        self.log_box.append(message)

    def detect_among_us(self):
        self.log("Searching for Among Us installation…")
        path = find_among_us()
        if path:
            self.install_path = path
            self.path_edit.setText(path)
            self.log(f"Found Among Us at: {path}")
        else:
            self.path_edit.setText("(not found — please browse)")
            self.log(
                "Could not auto-detect Among Us. "
                "Please use the Browse button to select your Among Us folder."
            )

    def browse_folder(self):
        start = self.install_path or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self, "Select your Among Us folder", start
        )
        if folder:
            self.install_path = folder
            self.path_edit.setText(folder)
            self.log(f"Selected folder: {folder}")

    # -- install flow --
    def start_install(self):
        if not self.install_path or not os.path.isdir(self.install_path):
            QMessageBox.warning(
                self, "No folder selected",
                "Please select your Among Us folder first."
            )
            return

        # Sanity check for Among Us.exe
        if not (Path(self.install_path) / AMONG_US_EXE).exists():
            reply = QMessageBox.question(
                self, "Among Us.exe not found",
                f"The selected folder does not contain '{AMONG_US_EXE}'.\n\n"
                "Continue anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        # Check for existing BepInEx (mod already installed)
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

        # Disable UI and start worker
        self.install_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.install_btn.setText("Installing…")
        self.progress.setValue(0)

        self.thread = QThread()
        self.worker = InstallWorker(self.install_path, MOD_URL)
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
        self.browse_btn.setEnabled(True)
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
    # qtpy: exec() works across PyQt5/6 and PySide2/6
    exit_code = app.exec() if hasattr(app, "exec") else app.exec_()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()