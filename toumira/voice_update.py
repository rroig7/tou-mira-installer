"""Keeps an existing BetterCrewLink-TOU + voice bridge install current.

When a new BetterCrewLink-TOU release is published, :func:`check` reports what to
update for the selected install. That's a newer app, or a bridge whose bytes differ
from the newest build for the installed TOU-Mira version (or a missing half of the
pair). :class:`VoiceUpdateWorker` applies it without reinstalling the mod. The app
also self-updates via electron-updater; the bridge, which must match the TOU-Mira
version, only updates through here.
"""
from qtpy.QtCore import QObject, Signal

from toumira import bettercrewlink, bridge, metadata
from toumira.version_utils import semver_gt

TOU = bettercrewlink.TOU


def check(install_path, mod_version, on_log=None):
    """Return ``{"app": version|None, "bridge": version|None}`` (what to install), or
    None when neither the app nor the bridge is installed. ``mod_version`` is the
    installed TOU-Mira version, used to pick the matching bridge."""
    app_installed = bettercrewlink.installed_version(TOU)
    bridge_digest = bridge.installed_digest(install_path)
    if app_installed is None and bridge_digest is None:
        return None

    releases = bettercrewlink.fetch_releases(TOU, on_log)
    latest_app = bettercrewlink.latest_setup(releases, TOU)["version"]
    app = latest_app if app_installed is None or semver_gt(latest_app, app_installed) else None

    match = bridge.find_for(releases, mod_version) if mod_version else None
    bridge_update = None
    if match and match["digest"] and match["digest"] != bridge_digest:
        bridge_update = match["version"]
    return {"app": app, "bridge": bridge_update}


class VoiceUpdateCheckWorker(QObject):
    """Runs :func:`check` on a background thread."""

    result = Signal(object)  # check() result
    error = Signal(str)

    def __init__(self, install_path, mod_version):
        super().__init__()
        self.install_path = install_path
        self.mod_version = mod_version

    def run(self):
        try:
            self.result.emit(check(self.install_path, self.mod_version))
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class VoiceUpdateWorker(QObject):
    """Installs the bridge and/or app updates reported by :func:`check`, leaving the mod alone.
    Same signals as ``InstallWorker`` so the UI can treat it like an install."""

    progress = Signal(int)
    log = Signal(str)
    finished = Signal(bool, str)  # success, message

    def __init__(self, install_path, mod_version, update_app, update_bridge):
        super().__init__()
        self.install_path = install_path
        self.mod_version = mod_version
        self.update_app = update_app
        self.update_bridge = update_bridge

    def run(self):
        try:
            releases = bettercrewlink.fetch_releases(TOU, self.log.emit)
            done = []
            if self.update_bridge:
                version, entry = bridge.download_and_install(
                    self.install_path, self.mod_version, on_log=self.log.emit, releases=releases,
                )
                metadata.add_manifest_entry(self.install_path, entry)
                done.append(f"Voice bridge (from v{version})")
            self.progress.emit(10)
            if self.update_app:
                version = bettercrewlink.download_and_install(
                    on_log=self.log.emit, on_progress=self.progress.emit,
                    progress_start=10, progress_end=100, source=TOU, releases=releases,
                )
                done.append(f"{TOU.name} v{version}")
            self.progress.emit(100)
            self.finished.emit(True, " and ".join(done) + " installed." if done else "Nothing to update.")
        except Exception as e:  # noqa: BLE001
            self.finished.emit(False, f"Voice chat update failed: {e}")
