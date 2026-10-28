"""Background worker that downloads and installs the mod."""
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from qtpy.QtCore import QObject, Signal

from toumira import archive, bettercrewlink, metadata, net
from toumira.config import PLATFORM_EPIC


@contextmanager
def _temp_zip():
    """Yield a path to a fresh temp .zip file, deleting it on exit."""
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        path = tmp.name
    try:
        yield path
    finally:
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass


class InstallWorker(QObject):
    """Downloads and installs the mod on a worker thread."""

    progress = Signal(int)
    log = Signal(str)
    finished = Signal(bool, str)  # success, message

    def __init__(self, platform, install_path, mod_url,
                 source_path=None, starter_url=None, mod_version=None,
                 install_bettercrewlink=False):
        super().__init__()
        self.platform = platform
        self.install_path = install_path
        self.mod_url = mod_url
        self.source_path = source_path  # Epic only: original Among Us folder
        self.starter_url = starter_url  # Epic only
        self.mod_version = mod_version or ""
        self.install_bettercrewlink = install_bettercrewlink
        # Mod phases are written against a 0–100 bar; when BetterCrewLink is
        # also installed they are squeezed into 0–60 and it takes 60–100.
        self._mod_progress_end = 60 if install_bettercrewlink else 100

    def _report_progress(self, pct):
        """Emit a mod-phase percentage, scaled into the mod's share of the bar."""
        self.progress.emit(int(pct * self._mod_progress_end / 100))

    # -- shared steps --
    def _download_mod_zip(self, tmp_zip, progress_start, progress_end):
        self.log.emit(f"Downloading mod from:\n  {self.mod_url}")
        net.download_file(self.mod_url, tmp_zip, on_progress=self._report_progress,
                          progress_start=progress_start, progress_end=progress_end,
                          on_log=self.log.emit)
        self.log.emit("Download complete.")

    def _install_mod_files(self, tmp_zip, progress_start, progress_end):
        self.log.emit(f"Installing mod files to:\n  {self.install_path}")
        return archive.extract_and_copy(
            tmp_zip, self.install_path,
            on_log=self.log.emit, on_progress=self._report_progress,
            progress_start=progress_start, progress_end=progress_end,
        )

    def _finalize(self, installed, message):
        self._report_progress(100)
        metadata.write_metadata(self.install_path, self.mod_version, installed)
        self.log.emit("Mod installation complete.")
        if self.install_bettercrewlink:
            message += self._install_bettercrewlink()
        self.progress.emit(100)
        self.finished.emit(True, message)

    def _install_bettercrewlink(self):
        """Install BetterCrewLink (60–100%). Returns text to append to the
        result message. A failure here doesn't fail the (already done) mod install."""
        try:
            version = bettercrewlink.download_and_install(
                on_log=self.log.emit, on_progress=self.progress.emit,
                progress_start=self._mod_progress_end, progress_end=100,
            )
        except Exception as e:  # noqa: BLE001
            self.log.emit(f"BetterCrewLink installation failed: {e}")
            return f"\n\nBetterCrewLink could not be installed:\n{e}"
        self.log.emit(f"BetterCrewLink v{version} installed.")
        return f"\n\nBetterCrewLink v{version} was also installed."

    # -- entry point --
    def run(self):
        try:
            if self.platform == PLATFORM_EPIC:
                self._run_epic()
            else:
                self._run_steam()
        except Exception as e:  # noqa: BLE001
            self.finished.emit(False, f"Installation failed: {e}")

    def _run_steam(self):
        with _temp_zip() as tmp_zip:
            self._download_mod_zip(tmp_zip, progress_start=0, progress_end=75)
            installed = self._install_mod_files(tmp_zip, progress_start=75, progress_end=100)
        self._finalize(
            installed,
            f"TOU-Mira v{self.mod_version} installed successfully!",
        )

    def _run_epic(self):
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
        self._copy_among_us_folder(dest)
        self._report_progress(30)
        self.log.emit("Among Us folder copied.")

        # Step 2: Download and unzip EpicGamesStarter.exe (30–40%)
        self.log.emit("Downloading EpicGamesStarter.exe…")
        with _temp_zip() as starter_zip:
            net.download_file(self.starter_url, starter_zip, on_log=self.log.emit)
            archive.extract_single_exe(starter_zip, dest, "EpicGamesStarter.exe")
        self._report_progress(40)
        self.log.emit("EpicGamesStarter.exe downloaded.")

        # Steps 3 & 4: Download (40–75%) then extract mod files (75–100%)
        with _temp_zip() as tmp_zip:
            self._download_mod_zip(tmp_zip, progress_start=40, progress_end=75)
            installed = self._install_mod_files(tmp_zip, progress_start=75, progress_end=100)

        self._finalize(
            installed,
            f"TOU-Mira v{self.mod_version} installed successfully!\n\n"
            f"Launch the game using EpicGamesStarter.exe inside:\n{self.install_path}",
        )

    def _copy_among_us_folder(self, dest):
        """Copy the source Among Us folder to ``dest``, reporting 0–30% progress."""
        source = Path(self.source_path)
        total_files = max(len([f for f in source.rglob("*") if f.is_file()]), 1)
        copied = [0]

        def _copy_fn(src, dst):
            shutil.copy2(src, dst)
            copied[0] += 1
            self._report_progress(min(int(copied[0] * 30 / total_files), 30))

        shutil.copytree(self.source_path, str(dest), copy_function=_copy_fn)
