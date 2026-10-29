"""Optional BetterCrewLink (proximity voice chat) install, decoupled from the GUI.

BetterCrewLink is a standalone app, not a mod file: we download its Windows
setup from GitHub releases and run it silently. Its NSIS installer is per-user
(no admin prompt) and registers itself under the Uninstall registry key, which
is how we detect an existing install. Uninstall is left to Windows "Installed
apps" — we never remove it.

Two builds share this code (see ``OFFICIAL`` / ``TOU``): official BetterCrewLink,
and the BetterCrewLink-TOU fork, which installs as a separate app.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from toumira import net
from toumira.config import (
    BCL_TOU_DISPLAY_NAME,
    BCL_TOU_NAME,
    BCL_TOU_RELEASES_API_URL,
    BETTERCREWLINK_DISPLAY_NAME,
    BETTERCREWLINK_NAME,
    BETTERCREWLINK_RELEASES_API_URL,
)

_SETUP_TIMEOUT = 10 * 60  # seconds


@dataclass(frozen=True)
class Source:
    name: str
    # Either /releases/latest (one release object) or /releases (newest-first list,
    # prereleases included).
    releases_api_url: str
    # Prefix of the DisplayName its NSIS setup writes to the Uninstall registry key.
    display_name: str


OFFICIAL = Source(BETTERCREWLINK_NAME, BETTERCREWLINK_RELEASES_API_URL, BETTERCREWLINK_DISPLAY_NAME)
TOU = Source(BCL_TOU_NAME, BCL_TOU_RELEASES_API_URL, BCL_TOU_DISPLAY_NAME)


def installed_version(source=OFFICIAL):
    """Return the installed version string, or None if not installed."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    uninstall = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    roots = [
        (winreg.HKEY_CURRENT_USER, uninstall),
        (winreg.HKEY_LOCAL_MACHINE, uninstall),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hkey, path in roots:
        try:
            root = winreg.OpenKey(hkey, path)
        except OSError:
            continue
        with root:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(root, name) as key:
                        display = winreg.QueryValueEx(key, "DisplayName")[0]
                        if not str(display).startswith(source.display_name):
                            continue
                        try:
                            return str(winreg.QueryValueEx(key, "DisplayVersion")[0])
                        except OSError:
                            return ""
                except OSError:
                    continue
    return None


def fetch_releases(source=OFFICIAL, on_log=None):
    """Return the source's releases, newest first (a /releases/latest answer becomes a
    one-item list). Uses verified TLS only, since the setup is executed."""
    with net.open_url(source.releases_api_url, timeout=10,
                      on_log=on_log, allow_insecure=False) as resp:
        data = json.loads(resp.read().decode())
    return data if isinstance(data, list) else [data]


def latest_setup(releases, source=OFFICIAL):
    """Return ``{version, name, url, digest}`` for the newest Windows setup exe."""
    for release in releases:
        if release.get("draft"):
            continue
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            lower = name.lower()
            if lower.endswith(".exe") and "setup" in lower:
                return {
                    "version": release.get("tag_name", "").lstrip("vV"),
                    "name": name,
                    "url": asset.get("browser_download_url", ""),
                    "digest": asset.get("digest") or "",
                }
    raise RuntimeError(f"No {source.name} release has a Windows setup download.")


def fetch_latest_setup(on_log=None, source=OFFICIAL):
    """Return ``{version, name, url, digest}`` for the newest Windows setup exe."""
    return latest_setup(fetch_releases(source, on_log), source)


def download_and_install(on_log=None, on_progress=None, progress_start=0, progress_end=100,
                         source=OFFICIAL, releases=None):
    """Download the newest setup and run it silently.

    ``releases`` (from :func:`fetch_releases`) saves a request when the caller has them.
    The download takes ``progress_start``–95% of the slice; the silent setup
    run (which reports no progress) takes the rest. Returns the version installed.
    """
    info = latest_setup(releases if releases is not None else fetch_releases(source, on_log), source)
    if on_log:
        on_log(f"Downloading {info['name']} ({source.name} v{info['version']})…")
    download_end = progress_start + int((progress_end - progress_start) * 0.95)
    tmp_dir = tempfile.mkdtemp(prefix="toumira_bcl_")
    try:
        # Keep the asset's own name: NSIS setups behave better when not renamed.
        setup = Path(tmp_dir) / Path(info["name"]).name
        net.download_file(info["url"], setup, on_progress=on_progress,
                          progress_start=progress_start, progress_end=download_end,
                          on_log=on_log, timeout=60, allow_insecure=False)
        net.verify_sha256_digest(setup, info["digest"])
        if on_log:
            on_log(f"Running {source.name} setup…")
        result = subprocess.run([str(setup), "/S"], timeout=_SETUP_TIMEOUT)
        if result.returncode != 0:
            raise RuntimeError(f"{source.name} setup exited with code {result.returncode}.")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    if on_progress:
        on_progress(progress_end)
    return info["version"]
