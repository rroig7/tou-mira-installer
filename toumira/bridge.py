"""Optional TOU-Mira voice bridge install, decoupled from the GUI.

The bridge is a single BepInEx plugin DLL (released on rroig7/whg-tou-mira)
that lets the BetterCrewLink-TOU build react to TOU-Mira role effects. It is
dropped into ``BepInEx/plugins`` after the mod files and recorded in the install
manifest, so the normal mod uninstall removes it too.

Release contract (documented in that repo's README): the asset is named
``TouMiraBclBridge.dll`` and the release notes contain
``Built for TOU-Mira: <tag>[, <tag>...]`` listing every supported mod version,
which we compare with the installed mod version.
"""
import json
import os
import re
from pathlib import Path

from toumira import net
from toumira.config import BEPINEX_FOLDER, BRIDGE_DLL_NAME, BRIDGE_RELEASES_API_URL

_BUILT_FOR = re.compile(r"Built for TOU-Mira:[ \t]*([^\r\n]+)", re.IGNORECASE)


def _parse_built_for(body):
    """Return the supported TOU-Mira versions listed in release notes (may be empty)."""
    match = _BUILT_FOR.search(body or "")
    if not match:
        return []
    return [v.strip().lstrip("vV") for v in match.group(1).split(",") if v.strip()]


def plugin_relpath():
    """Path of the bridge DLL relative to the Among Us folder."""
    return Path(BEPINEX_FOLDER) / "plugins" / BRIDGE_DLL_NAME


def is_installed(install_path):
    return bool(install_path) and (Path(install_path) / plugin_relpath()).is_file()


def fetch_latest(on_log=None):
    """Return ``{version, url, digest, built_for}`` for the newest bridge release,
    where ``built_for`` is the list of supported TOU-Mira versions.

    Prereleases count (the bridge is in alpha). Uses verified TLS only, since
    the game loads the DLL.
    """
    with net.open_url(BRIDGE_RELEASES_API_URL, timeout=10,
                      on_log=on_log, allow_insecure=False) as resp:
        releases = json.loads(resp.read().decode())
    for release in releases:  # GitHub lists newest first
        if release.get("draft"):
            continue
        for asset in release.get("assets", []):
            if asset.get("name") != BRIDGE_DLL_NAME:
                continue
            return {
                "version": release.get("tag_name", "").lstrip("vV"),
                "url": asset.get("browser_download_url", ""),
                "digest": asset.get("digest") or "",
                "built_for": _parse_built_for(release.get("body")),
            }
    raise RuntimeError(f"No voice bridge release has a {BRIDGE_DLL_NAME} download.")


def download_and_install(install_path, mod_version, on_log=None):
    """Install the newest bridge DLL into ``install_path``'s BepInEx/plugins.

    Returns ``(version, manifest_entry, warning)``; ``warning`` is non-empty when
    the bridge was built for a different TOU-Mira version than ``mod_version``.
    """
    info = fetch_latest(on_log)
    if on_log:
        on_log(f"Downloading {BRIDGE_DLL_NAME} (voice bridge v{info['version']})…")
    dest = Path(install_path) / plugin_relpath()
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        net.download_file(info["url"], part, on_log=on_log, timeout=60, allow_insecure=False)
        net.verify_sha256_digest(part, info["digest"])
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)

    warning = ""
    mod_version = mod_version.lstrip("vV")
    if info["built_for"] and mod_version not in info["built_for"]:
        warning = (
            f"The voice bridge supports TOU-Mira {', '.join(info['built_for'])}, but "
            f"TOU-Mira {mod_version} was installed, so voice effects may not work "
            "until a matching bridge is released."
        )
    return info["version"], str(plugin_relpath()), warning
