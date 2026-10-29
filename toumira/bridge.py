"""TOU-Mira voice bridge install, decoupled from the GUI.

The bridge is a BepInEx plugin DLL that lets BetterCrewLink-TOU react to TOU-Mira
role effects. Each BetterCrewLink-TOU release (rroig7/BetterCrewLink) attaches one
build per supported TOU-Mira release, named ``TouMiraBclBridge-<tou-mira-tag>.dll``
and compiled against that release. This is how releases are tied to TOU-Mira
versions. We install the build matching the installed TOU-Mira version, from the
newest release that has one, as ``BepInEx/plugins/TouMiraBclBridge.dll``. It's
recorded in the install manifest, so the normal mod uninstall removes it too.
That release contract is documented in whg-tou-mira's README; keep both sides in sync.
"""
import hashlib
import os
from pathlib import Path

from toumira import bettercrewlink, net
from toumira.config import BEPINEX_FOLDER, BRIDGE_DLL_NAME


def plugin_relpath():
    """Path of the bridge DLL relative to the Among Us folder."""
    return Path(BEPINEX_FOLDER) / "plugins" / BRIDGE_DLL_NAME


def is_installed(install_path):
    return bool(install_path) and (Path(install_path) / plugin_relpath()).is_file()


def installed_digest(install_path):
    """GitHub-style ``"sha256:<hex>"`` of the installed bridge, or None if absent."""
    if not is_installed(install_path):
        return None
    data = (Path(install_path) / plugin_relpath()).read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def asset_name(mod_version):
    """Release asset name of the bridge built for TOU-Mira ``mod_version``."""
    return f"TouMiraBclBridge-{mod_version.lstrip('vV')}.dll"


def find_for(releases, mod_version):
    """Return ``{version, url, digest}`` of the newest bridge built for ``mod_version``
    in a newest-first GitHub releases list, or None if there isn't one."""
    want = asset_name(mod_version)
    for release in releases:
        if release.get("draft"):
            continue
        for asset in release.get("assets", []):
            if asset.get("name") == want:
                return {
                    "version": release.get("tag_name", "").lstrip("vV"),
                    "url": asset.get("browser_download_url", ""),
                    "digest": asset.get("digest") or "",
                }
    return None


def download_and_install(install_path, mod_version, on_log=None, releases=None):
    """Install the bridge built for TOU-Mira ``mod_version`` into ``install_path``.

    ``releases`` are BetterCrewLink-TOU releases (fetched if not given). Returns
    ``(version, manifest_entry)``; raises if no bridge exists for that TOU-Mira version.
    """
    if releases is None:
        releases = bettercrewlink.fetch_releases(bettercrewlink.TOU, on_log)
    info = find_for(releases, mod_version)
    if info is None:
        raise RuntimeError(
            f"No voice bridge has been released for TOU-Mira {mod_version.lstrip('vV')} yet."
        )
    if on_log:
        on_log(f"Downloading {asset_name(mod_version)} (from BetterCrewLink-TOU v{info['version']})…")
    dest = Path(install_path) / plugin_relpath()
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        # Verified TLS only + digest check: the game loads this DLL.
        net.download_file(info["url"], part, on_log=on_log, timeout=60, allow_insecure=False)
        net.verify_sha256_digest(part, info["digest"])
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)
    return info["version"], str(plugin_relpath())
