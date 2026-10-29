"""The Qt main window and all user-facing install/uninstall flows."""
import os
import shutil
from pathlib import Path

from qtpy.QtCore import Qt, QThread, QUrl
from qtpy.QtGui import QDesktopServices
from qtpy.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from toumira import bettercrewlink, bridge, metadata, updater, voice_update
from toumira.config import (
    AMONG_US_EXE,
    APP_RELEASES_PAGE_URL,
    APP_VERSION,
    BCL_TOU_NAME,
    BEPINEX_FOLDER,
    BETTERCREWLINK_NAME,
    BETTERCREWLINK_REPO_URL,
    BRIDGE_NAME,
    BRIDGE_REPO_URL,
    EPIC_INSTALL_FOLDER_NAME,
    EPIC_STARTER_URL,
    MOD_NAME,
    PLATFORM_EPIC,
    PLATFORM_STEAM,
    VERSION_FILE,
)
from toumira.detection import find_among_us, find_epic_among_us
from toumira.installer import InstallWorker
from toumira.releases import ReleaseFetchWorker
from toumira.version_utils import version_gt

_PROGRAM_FILES_DIRS = (
    Path(r"C:\Program Files"),
    Path(r"C:\Program Files (x86)"),
)


def _is_in_program_files(path):
    """Return True if ``path`` lives under a Program Files directory."""
    path = Path(path)
    for base in _PROGRAM_FILES_DIRS:
        try:
            path.relative_to(base)
            return True
        except ValueError:
            continue
    return False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{MOD_NAME} Installer")
        self.resize(680, 540)

        self.install_path = None   # Steam: Among Us dir; Epic: destination dir
        self.epic_source_path = None  # Epic: original Among Us dir in Program Files
        self.thread = None
        self.worker = None
        self._releases = []
        self._update_version = None
        self._fetch_thread = None
        self._fetch_worker = None
        self._installing = False
        self._pending_app_update = None  # deferred until a running install finishes
        self._app_check_thread = None
        self._app_check_worker = None
        self._app_update_thread = None
        self._app_update_worker = None
        self._app_update_dialog = None
        self._voice_update = None  # voice_update.check() result offered in the banner
        self._voice_check_thread = None
        self._voice_check_worker = None
        self._voice_check_again = False

        self._build_ui()

        # Wire platform toggle
        self.btn_steam.toggled.connect(self._on_platform_changed)
        self.btn_epic.toggled.connect(self._on_platform_changed)

        self._detect_paths()
        self._fetch_releases()
        if updater.current_exe():
            self._check_for_app_update()

    # -- UI construction --
    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel(f"<h2>{MOD_NAME} Installer</h2>")
        layout.addWidget(title)

        subtitle = QLabel(
            "This will download and install the TOU-Mira mod into your Among Us folder."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addWidget(self._build_update_banner())
        layout.addWidget(self._build_voice_update_banner())
        layout.addWidget(self._build_platform_box())
        layout.addWidget(self._build_steam_widget())
        layout.addWidget(self._build_epic_widget())
        self._epic_widget.setVisible(False)
        layout.addLayout(self._build_version_row())
        layout.addLayout(self._build_bettercrewlink_row())
        layout.addLayout(self._build_tou_voice_row())

        # Log
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box, 1)

        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        layout.addLayout(self._build_button_row())
        self.setCentralWidget(central)

    def _build_update_banner(self):
        """Warning banner, hidden until an update is detected."""
        self.update_banner = QFrame()
        self.update_banner.setStyleSheet(
            "QFrame { background-color: #FFF3CD; border: 1px solid #FFC107; "
            "border-radius: 4px; padding: 4px; } "
            "QLabel { color: #1a1a1a; background: transparent; }"
        )
        row = QHBoxLayout(self.update_banner)
        row.setContentsMargins(8, 4, 8, 4)
        self.update_label = QLabel()
        self.update_label.setWordWrap(True)
        row.addWidget(self.update_label, 1)
        self.update_banner.setVisible(False)
        return self.update_banner

    def _build_voice_update_banner(self):
        """Banner offering BetterCrewLink-TOU / voice bridge updates, hidden until one is found."""
        self.voice_update_banner = QFrame()
        self.voice_update_banner.setStyleSheet(
            "QFrame { background-color: #E3F2FD; border: 1px solid #64B5F6; "
            "border-radius: 4px; padding: 4px; } "
            "QLabel { color: #1a1a1a; background: transparent; border: none; }"
        )
        row = QHBoxLayout(self.voice_update_banner)
        row.setContentsMargins(8, 4, 8, 4)
        self.voice_update_label = QLabel()
        self.voice_update_label.setWordWrap(True)
        row.addWidget(self.voice_update_label, 1)
        self.voice_update_btn = QPushButton("Update voice chat")
        self.voice_update_btn.clicked.connect(self._start_voice_update)
        row.addWidget(self.voice_update_btn)
        self.voice_update_banner.setVisible(False)
        return self.voice_update_banner

    def _build_platform_box(self):
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
        return platform_box

    def _build_steam_widget(self):
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
        return self._steam_widget

    def _build_epic_widget(self):
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
        return self._epic_widget

    def _build_version_row(self):
        version_row = QHBoxLayout()
        version_row.addWidget(QLabel("Version:"))
        self.version_combo = QComboBox()
        self.version_combo.addItem("Loading versions…")
        self.version_combo.setEnabled(False)
        self.version_combo.currentIndexChanged.connect(self._update_button_states)
        version_row.addWidget(self.version_combo, 1)
        return version_row

    def _build_bettercrewlink_row(self):
        row = QHBoxLayout()
        self.bcl_checkbox = QCheckBox(
            f"Also install {BETTERCREWLINK_NAME} (proximity voice chat)"
        )
        row.addWidget(self.bcl_checkbox)
        link = QLabel(f'<a href="{BETTERCREWLINK_REPO_URL}">What is this?</a>')
        link.setOpenExternalLinks(True)
        row.addWidget(link)
        row.addStretch()
        self.bcl_status_label = QLabel()
        self.bcl_status_label.setStyleSheet("color: gray; font-size: 11px;")
        row.addWidget(self.bcl_status_label)
        self._refresh_bettercrewlink_status()
        return row

    def _refresh_bettercrewlink_status(self):
        version = bettercrewlink.installed_version()
        if version is None:
            self.bcl_status_label.setText("Not installed")
        else:
            self.bcl_status_label.setText(
                f"Installed: v{version}" if version else "Installed"
            )

    def _build_tou_voice_row(self):
        """BetterCrewLink-TOU + voice bridge: an alternative to official BetterCrewLink."""
        row = QHBoxLayout()
        self.tou_checkbox = QCheckBox(f"Or install {BCL_TOU_NAME} + voice bridge (alpha)")
        self.tou_checkbox.setToolTip(
            f"{BCL_TOU_NAME} is a BetterCrewLink build that, with the {BRIDGE_NAME}\n"
            "plugin, mutes jailed, blackmailed and controlled players.\n"
            "Installed instead of official BetterCrewLink. The bridge goes into\n"
            "BepInEx/plugins and is removed by Uninstall Mod."
        )
        row.addWidget(self.tou_checkbox)
        link = QLabel(f'<a href="{BRIDGE_REPO_URL}">What is this?</a>')
        link.setOpenExternalLinks(True)
        row.addWidget(link)
        row.addStretch()
        self.tou_status_label = QLabel()
        self.tou_status_label.setStyleSheet("color: gray; font-size: 11px;")
        row.addWidget(self.tou_status_label)
        self._refresh_tou_voice_status()

        # Either BetterCrewLink or neither, never both: they're separate apps.
        self.tou_checkbox.toggled.connect(
            lambda on: on and self.bcl_checkbox.setChecked(False))
        self.bcl_checkbox.toggled.connect(
            lambda on: on and self.tou_checkbox.setChecked(False))
        return row

    def _refresh_tou_voice_status(self):
        # The bridge part depends on the selected folder, so this is refreshed
        # with the button states.
        version = bettercrewlink.installed_version(bettercrewlink.TOU)
        app = "App: not installed" if version is None else f"App: v{version}" if version else "App: installed"
        plugin = "bridge installed" if bridge.is_installed(self.install_path) else "bridge not installed"
        self.tou_status_label.setText(f"{app} · {plugin}")

    def _build_button_row(self):
        btn_row = QHBoxLayout()
        self.uninstall_btn = QPushButton("Uninstall Mod")
        self.uninstall_btn.setMinimumHeight(40)
        self.uninstall_btn.setEnabled(False)
        self.uninstall_btn.clicked.connect(self.uninstall_mod)
        btn_row.addWidget(self.uninstall_btn)

        self.install_btn = QPushButton("Install Mod")
        self.install_btn.setMinimumHeight(40)
        self.install_btn.setEnabled(False)
        font = self.install_btn.font()
        font.setBold(True)
        self.install_btn.setFont(font)
        self.install_btn.clicked.connect(self.start_install)
        btn_row.addWidget(self.install_btn)
        return btn_row

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

    # -- release fetching --
    def _fetch_releases(self):
        self.version_combo.clear()
        self.version_combo.addItem("Loading versions…")
        self.version_combo.setEnabled(False)
        self.install_btn.setEnabled(False)
        self.log("Fetching available versions from GitHub…")

        thread = QThread()
        worker = ReleaseFetchWorker()
        self._fetch_thread = thread
        self._fetch_worker = worker

        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.releases_fetched.connect(self._on_releases_fetched)
        worker.error.connect(self._on_fetch_error)
        for sig in (worker.releases_fetched, worker.error):
            sig.connect(thread.quit)
            sig.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: setattr(self, "_fetch_thread", None))
        thread.finished.connect(lambda: setattr(self, "_fetch_worker", None))
        thread.start()

    def _on_releases_fetched(self, releases):
        self._releases = releases
        self.version_combo.clear()

        if not releases:
            self.version_combo.addItem("No releases found")
            self.log("No releases found on GitHub.")
            return

        for i, release in enumerate(releases):
            label = f"v{release['version']}" + (" (latest)" if i == 0 else "")
            self.version_combo.addItem(label)

        self.version_combo.setEnabled(True)
        self.log(f"Found {len(releases)} release(s). Latest: v{releases[0]['version']}")
        self._refresh_update_state()

    def _on_fetch_error(self, error_msg):
        self.version_combo.clear()
        self.version_combo.addItem("Failed to load versions")
        self.log(f"Could not fetch releases: {error_msg}")

    def _refresh_update_state(self):
        """Update the banner and button text based on installed vs latest version."""
        if not self._releases:
            return
        latest = self._releases[0]["version"]
        installed = metadata.read_version(self.install_path)
        if self._is_mod_installed() and version_gt(latest, installed):
            self._update_version = latest
            self.update_label.setText(
                f"<b>Update available:</b> TOU-Mira v{latest} is ready to install."
            )
            self.update_banner.setVisible(True)
            self.log(f"Update available: v{latest} (installed: v{installed})")
        else:
            self._update_version = None
            self.update_banner.setVisible(False)
            if self._is_mod_installed():
                self.log(f"TOU-Mira is up to date (v{installed}).")
        self._update_button_states()
        self._check_voice_update()

    def _is_mod_installed(self):
        if not self.install_path:
            return False
        if self._current_platform() == PLATFORM_STEAM:
            return (Path(self.install_path) / BEPINEX_FOLDER).exists()
        return (Path(self.install_path) / VERSION_FILE).exists()

    def _update_button_states(self):
        has_releases = bool(self._releases)
        installed = self._is_mod_installed()
        self._refresh_tou_voice_status()
        self.install_btn.setEnabled(has_releases)
        self.uninstall_btn.setEnabled(installed)
        if self._update_version and installed:
            self.install_btn.setText("Update Mod")
        else:
            self.install_btn.setText("Install Mod")

    # -- installer self-update --
    def _run_in_thread(self, worker, done_signals):
        """Run ``worker.run`` on a new QThread, torn down when any of
        ``done_signals`` fires. Returns the thread."""
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        for sig in done_signals:
            sig.connect(thread.quit)
            sig.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        return thread

    def _check_for_app_update(self):
        worker = updater.UpdateCheckWorker()
        worker.update_available.connect(self._on_app_update_available)
        worker.error.connect(
            lambda msg: self.log(f"Could not check for installer updates: {msg}")
        )
        self._app_check_worker = worker
        self._app_check_thread = self._run_in_thread(
            worker, (worker.update_available, worker.error)
        )

    def _on_app_update_available(self, info):
        if not info:
            return
        self.log(f"Installer update available: v{info['version']} (current: v{APP_VERSION})")
        if self._installing:
            self._pending_app_update = info
        else:
            self._prompt_app_update(info)

    def _prompt_app_update(self, info):
        reply = QMessageBox.question(
            self, "Installer update available",
            f"A new version of the {MOD_NAME} Installer is available.\n\n"
            f"Current version: v{APP_VERSION}\n"
            f"New version: v{info['version']}\n\n"
            "Download it and restart now?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            self.log("Installer update skipped.")
            return
        if not info["exe_url"]:
            self._offer_release_page("The new release has no installer download attached.")
            return
        self._start_app_update(info)

    def _start_app_update(self, info):
        self._set_controls_enabled(False)
        self.log(f"Downloading installer v{info['version']}…")

        dialog = QProgressDialog(
            f"Downloading installer v{info['version']}…", "", 0, 100, self
        )
        dialog.setCancelButton(None)  # download can't be interrupted mid-way
        dialog.setWindowTitle("Updating installer")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setValue(0)
        dialog.show()
        self._app_update_dialog = dialog

        worker = updater.UpdateDownloadWorker(info)
        worker.progress.connect(dialog.setValue)
        worker.finished.connect(self._on_app_update_downloaded)
        self._app_update_worker = worker
        self._app_update_thread = self._run_in_thread(worker, (worker.finished,))

    def _on_app_update_downloaded(self, success, result):
        self._app_update_dialog.close()
        self._app_update_dialog = None
        if success:
            try:
                updater.launch_new_version(result)
            except OSError as e:
                success, result = False, f"Could not start the new installer:\n{e}"
        if not success:
            self.log(f"Installer update failed: {result}")
            self._set_controls_enabled(True)
            self._update_button_states()
            self._offer_release_page(f"The installer could not be updated:\n{result}")
            return
        self.log("Restarting into the new installer…")
        QApplication.instance().quit()

    def _offer_release_page(self, reason):
        reply = QMessageBox.question(
            self, "Installer update",
            f"{reason}\n\nOpen the download page in your browser instead?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl(APP_RELEASES_PAGE_URL))

    # -- uninstall flow --
    def uninstall_mod(self):
        if self._current_platform() == PLATFORM_STEAM:
            self._uninstall_steam()
        else:
            self._uninstall_epic()
        self._update_button_states()

    def _uninstall_steam(self):
        install_path = Path(self.install_path)
        try:
            entries = metadata.read_manifest(install_path)
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Could not read uninstall manifest:\n{e}")
            return
        if entries is not None:
            self._uninstall_steam_via_manifest(install_path, entries)
        else:
            self._uninstall_steam_fallback(install_path)

    def _uninstall_steam_via_manifest(self, install_path, entries):
        reply = QMessageBox.question(
            self, "Uninstall mod",
            f"This will remove {len(entries)} mod file(s) from:\n{self.install_path}\n\n"
            "Among Us itself will not be affected. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        files, dirs = [], []
        for entry in entries:
            p = install_path / entry
            if p.is_file():
                files.append(p)
            elif p.is_dir():
                dirs.append(p)
        # rmdir only removes empty dirs, so delete files first then prune deepest dirs first
        dirs.sort(key=lambda p: len(p.parts), reverse=True)

        errors = []
        for f in files:
            try:
                f.unlink()
            except OSError as e:
                errors.append(str(e))
        for d in dirs:
            try:
                d.rmdir()
            except OSError:
                pass  # not empty or already gone — leave it

        # BepInEx accumulates runtime files (logs, config, cache) that were never
        # in the manifest, so it survives the per-file cleanup above. Remove
        # whatever remains so the mod is no longer detected as installed.
        bepinex = install_path / BEPINEX_FOLDER
        if bepinex.exists():
            try:
                shutil.rmtree(bepinex)
            except OSError as e:
                errors.append(str(e))

        metadata.remove_metadata(install_path)

        if errors:
            self.log(f"Uninstall finished with {len(errors)} error(s).")
            QMessageBox.warning(self, "Uninstall incomplete",
                f"{len(errors)} file(s) could not be removed. "
                "Make sure Among Us is closed and try again.")
        else:
            self.log("Mod uninstalled successfully.")
            QMessageBox.information(self, "Uninstalled", "TOU-Mira has been uninstalled.")

    def _uninstall_steam_fallback(self, install_path):
        bepinex = install_path / BEPINEX_FOLDER
        reply = QMessageBox.question(
            self, "Uninstall mod",
            f"No file manifest found. This will remove the '{BEPINEX_FOLDER}' folder from:\n"
            f"{self.install_path}\n\nAmong Us itself will not be affected. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            shutil.rmtree(bepinex)
            (install_path / VERSION_FILE).unlink(missing_ok=True)
            self.log("Mod uninstalled successfully.")
            QMessageBox.information(self, "Uninstalled", "TOU-Mira has been uninstalled.")
        except OSError as e:
            QMessageBox.critical(self, "Error",
                f"Could not uninstall the mod:\n{e}\n\nMake sure Among Us is closed.")

    def _uninstall_epic(self):
        dest = Path(self.install_path)
        if not dest.exists():
            QMessageBox.warning(self, "Not found", f'"{dest}" does not exist.')
            return
        reply = QMessageBox.question(
            self, "Uninstall mod",
            f'This will permanently delete:\n{self.install_path}\n\nContinue?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            shutil.rmtree(dest)
            self.log("Mod uninstalled successfully.")
            QMessageBox.information(self, "Uninstalled", "TOU-Mira has been uninstalled.")
        except OSError as e:
            QMessageBox.critical(self, "Error",
                f"Could not delete the folder:\n{e}\n\nMake sure Among Us is closed.")

    # -- path detection --
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
        self._refresh_update_state()

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
    def _selected_release(self):
        idx = self.version_combo.currentIndex()
        if 0 <= idx < len(self._releases):
            return self._releases[idx]
        return None

    def start_install(self):
        release = self._selected_release()
        if not release:
            return

        platform = self._current_platform()
        mod_url = release["steam_url"] if platform == PLATFORM_STEAM else release["epic_url"]
        mod_version = release["version"]

        if not mod_url:
            QMessageBox.warning(
                self, "No download URL",
                f"No {platform.capitalize()} download found for v{mod_version}.\n"
                "Try selecting a different version."
            )
            return

        if platform == PLATFORM_STEAM:
            if not self.install_path or not os.path.isdir(self.install_path):
                QMessageBox.warning(self, "No folder selected",
                    "Please select your Among Us folder first.")
                return
            self._start_steam_install(mod_url, mod_version)
        else:
            self._start_epic_install(mod_url, mod_version)

    def _start_steam_install(self, mod_url, mod_version):
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
            mod_url=mod_url,
            mod_version=mod_version,
        )

    def _start_epic_install(self, mod_url, mod_version):
        if not self.epic_source_path or not os.path.isdir(self.epic_source_path):
            QMessageBox.warning(self, "No source folder",
                "Please select your Epic Games Among Us folder first.")
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
        if _is_in_program_files(dest):
            QMessageBox.warning(self, "Invalid destination",
                "The destination folder is inside Program Files.\n\n"
                "EpicGamesStarter cannot launch the game from there. "
                "Please choose a different location such as your Desktop.")
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
            mod_url=mod_url,
            source_path=self.epic_source_path,
            starter_url=EPIC_STARTER_URL,
            mod_version=mod_version,
        )

    def _launch_worker(self, **kwargs):
        self._run_install_worker(InstallWorker(
            install_bettercrewlink=self.bcl_checkbox.isChecked(),
            install_tou_voice=self.tou_checkbox.isChecked(),
            **kwargs,
        ))

    # -- BetterCrewLink-TOU / voice bridge updates --
    def _check_voice_update(self):
        """Look for BetterCrewLink-TOU / voice bridge updates for the selected install
        in the background; the result shows or hides the voice update banner."""
        if self._voice_check_thread is not None:
            self._voice_check_again = True  # re-run once the current check finishes
            return
        if self._installing or not self._is_mod_installed():
            self._show_voice_update(None)
            return
        worker = voice_update.VoiceUpdateCheckWorker(
            self.install_path, metadata.read_version(self.install_path),
        )
        worker.result.connect(self._show_voice_update)
        worker.error.connect(
            lambda msg: self.log(f"Could not check for voice chat updates: {msg}")
        )
        self._voice_check_worker = worker
        self._voice_check_thread = self._run_in_thread(worker, (worker.result, worker.error))
        # Drop our references only once the thread has stopped: a QThread garbage-collected
        # while still running aborts the whole app.
        self._voice_check_thread.finished.connect(self._on_voice_check_done)

    def _on_voice_check_done(self):
        self._voice_check_thread = self._voice_check_worker = None
        if self._voice_check_again:
            self._voice_check_again = False
            self._check_voice_update()

    def _show_voice_update(self, info):
        parts = []
        if info and info.get("app"):
            parts.append(f"{BCL_TOU_NAME} v{info['app']}")
        if info and info.get("bridge"):
            parts.append(f"the voice bridge for TOU-Mira {metadata.read_version(self.install_path)}")
        self._voice_update = info if parts else None
        self.voice_update_banner.setVisible(bool(parts))
        if parts:
            self.voice_update_label.setText(
                "<b>Voice chat update available:</b> " + " and ".join(parts) + "."
            )
            self.log("Voice chat update available: " + ", ".join(parts))

    def _start_voice_update(self):
        info = self._voice_update
        if not info or self._installing:
            return
        self._run_install_worker(voice_update.VoiceUpdateWorker(
            self.install_path, metadata.read_version(self.install_path),
            update_app=bool(info.get("app")), update_bridge=bool(info.get("bridge")),
        ))

    def _run_install_worker(self, worker):
        """Run an install-style worker (``progress``/``log``/``finished`` signals),
        locking the controls until ``on_install_finished``."""
        self._installing = True
        self._set_controls_enabled(False)
        self.install_btn.setText("Installing…")
        self.progress.setValue(0)

        self.thread = QThread()
        self.worker = worker
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.log.connect(self.log)
        self.worker.finished.connect(self.on_install_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _set_controls_enabled(self, enabled):
        """Enable/disable the interactive controls during an install."""
        self.install_btn.setEnabled(enabled)
        self.uninstall_btn.setEnabled(enabled)
        self.version_combo.setEnabled(enabled and bool(self._releases))
        self.steam_browse_btn.setEnabled(enabled)
        self.epic_source_btn.setEnabled(enabled)
        self.epic_dest_btn.setEnabled(enabled)
        self.btn_steam.setEnabled(enabled)
        self.btn_epic.setEnabled(enabled)
        self.bcl_checkbox.setEnabled(enabled)
        self.tou_checkbox.setEnabled(enabled)
        self.voice_update_btn.setEnabled(enabled)

    def on_install_finished(self, success, message):
        self._installing = False
        self.log(message)
        self._set_controls_enabled(True)
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.critical(self, "Error", message)
        self._refresh_update_state()
        self._refresh_bettercrewlink_status()
        if self._pending_app_update:
            info, self._pending_app_update = self._pending_app_update, None
            self._prompt_app_update(info)
