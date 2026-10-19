"""Self-update for the packaged installer exe.

Flow: on launch, check the installer's latest GitHub release. If it is newer
than :data:`~toumira.config.APP_VERSION`, the UI asks the user; on yes, the new
exe is downloaded next to the running one (under the release asset's name),
launched with ``--cleanup-old <path>``, and this process quits. The new process
then deletes the old exe once its file lock is released.

Only meaningful for the frozen (PyInstaller) build — running from source never
checks for updates.
"""
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from qtpy.QtCore import QObject, Signal

from toumira import net
from toumira.config import APP_RELEASES_API_URL, APP_VERSION
from toumira.version_utils import version_gt

CLEANUP_ARG = "--cleanup-old"
_OLD_SUFFIX = ".old"


def current_exe():
    """Path of the running installer exe, or None when running from source."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve()


def _same_path(a, b):
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


# --- Checking ----------------------------------------------------------------
def parse_latest_release(release):
    """Return update info for a newer release, or None if not newer.

    The info dict has keys ``version``, ``exe_name``, ``exe_url`` and
    ``digest`` (GitHub's ``"sha256:<hex>"`` asset digest, may be empty).
    """
    version = release.get("tag_name", "").lstrip("vV")
    if not version or not version_gt(version, APP_VERSION):
        return None
    exe = next((a for a in release.get("assets", [])
                if a.get("name", "").lower().endswith(".exe")), {})
    return {
        "version": version,
        "exe_name": exe.get("name", ""),
        "exe_url": exe.get("browser_download_url", ""),
        "digest": exe.get("digest") or "",
    }


class UpdateCheckWorker(QObject):
    """Checks GitHub for a newer installer release on a background thread."""

    update_available = Signal(object)  # info dict, or None if up to date
    error = Signal(str)

    def run(self):
        try:
            with net.open_url(APP_RELEASES_API_URL, timeout=10, allow_insecure=False) as resp:
                data = json.loads(resp.read().decode())
            self.update_available.emit(parse_latest_release(data))
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


# --- Downloading -------------------------------------------------------------
def _verify_digest(path, digest):
    """Raise if ``path`` does not match a ``"sha256:<hex>"`` digest (if given)."""
    if not digest.startswith("sha256:"):
        return
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != digest.split(":", 1)[1].lower():
        raise RuntimeError("Downloaded update failed its integrity check (SHA-256 mismatch).")


def download_update(info, on_progress=None):
    """Download the new exe next to the running one. Returns its path.

    Uses verified TLS only, since the result is executed.
    """
    current = current_exe()
    if current is None:
        raise RuntimeError("Self-update is only available in the packaged installer.")
    target = current.parent / info["exe_name"]
    part = target.with_name(target.name + ".part")
    try:
        net.download_file(info["exe_url"], part, on_progress=on_progress,
                          allow_insecure=False, timeout=60)
        _verify_digest(part, info["digest"])
        if _same_path(target, current):
            # Same filename: a running exe can't be overwritten, but it can be renamed.
            current.replace(current.with_name(current.name + _OLD_SUFFIX))
        os.replace(part, target)
    finally:
        part.unlink(missing_ok=True)
    return target


class UpdateDownloadWorker(QObject):
    """Downloads the installer update on a background thread."""

    progress = Signal(int)
    finished = Signal(bool, str)  # success, new exe path or error message

    def __init__(self, info):
        super().__init__()
        self.info = info

    def run(self):
        try:
            new_exe = download_update(self.info, on_progress=self.progress.emit)
            self.finished.emit(True, str(new_exe))
        except Exception as e:  # noqa: BLE001
            self.finished.emit(False, str(e))


# --- Handing over to the new exe ---------------------------------------------
def launch_new_version(new_exe):
    """Start ``new_exe`` detached, asking it to delete the current exe.

    The caller should quit the application right after this returns.
    """
    current = current_exe()
    old = current
    if _same_path(new_exe, current):
        old = current.with_name(current.name + _OLD_SUFFIX)

    # Make the child a fresh PyInstaller instance rather than one that reuses
    # this process's (soon to be deleted) onefile extraction directory.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("_PYI_") and k != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

    subprocess.Popen(
        [str(new_exe), CLEANUP_ARG, str(old)],
        env=env,
        close_fds=True,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def _delete_with_retry(path, attempts=30, delay=1.0):
    """Delete ``path``, retrying while the old process still holds a lock on it."""
    for _ in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return
        except OSError:
            time.sleep(delay)


def schedule_old_exe_cleanup(argv):
    """If launched by a previous version's updater, delete that exe in the background.

    Only deletes an ``.exe`` (or ``.exe.old``) sitting next to the current exe,
    and never the current exe itself.
    """
    try:
        old = Path(argv[argv.index(CLEANUP_ARG) + 1])
    except (ValueError, IndexError):
        return
    current = current_exe()
    if current is None or not old.name.lower().endswith((".exe", ".exe" + _OLD_SUFFIX)):
        return
    if _same_path(old, current) or not _same_path(old.parent, current.parent):
        return
    threading.Thread(target=_delete_with_retry, args=(old,), daemon=True).start()
