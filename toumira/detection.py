"""Locate the Among Us install folder for Steam and Epic Games."""
import json
import os
import re
import sys
from pathlib import Path

from toumira.config import AMONG_US_EXE, AMONG_US_FOLDER_NAME


def _first_valid(candidates):
    """Return the first candidate containing Among Us.exe, else the first that
    exists at all, else None. Accepts an iterable of Path objects."""
    candidates = list(candidates)
    for path in candidates:
        if path.is_dir() and (path / AMONG_US_EXE).exists():
            return str(path)
    for path in candidates:
        if path.is_dir():
            return str(path)
    return None


# --- Steam -------------------------------------------------------------------
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


_STEAM_FALLBACKS = [
    r"C:\Program Files (x86)\Steam\steamapps\common",
    r"C:\Program Files\Steam\steamapps\common",
    r"D:\Steam\steamapps\common",
    r"D:\SteamLibrary\steamapps\common",
    r"E:\Steam\steamapps\common",
    r"E:\SteamLibrary\steamapps\common",
]


def find_among_us():
    """Try to locate the Steam Among Us install folder. Return path str or None."""
    candidates = []

    steam_path = _get_steam_path_windows()
    if steam_path:
        for lib in _get_steam_libraries(steam_path):
            candidates.append(Path(lib) / "steamapps" / "common" / AMONG_US_FOLDER_NAME)

    for base in _STEAM_FALLBACKS:
        candidates.append(Path(base) / AMONG_US_FOLDER_NAME)

    return _first_valid(candidates)


# --- Epic Games --------------------------------------------------------------
_EPIC_MANIFESTS_DIR = Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests")
_EPIC_FALLBACKS = [
    r"C:\Program Files\Epic Games",
    r"C:\Program Files (x86)\Epic Games",
    r"D:\Epic Games",
    r"D:\EpicGames",
    r"E:\Epic Games",
    r"E:\EpicGames",
]


def _epic_manifest_candidates():
    """Yield install paths parsed from Epic Games Launcher .item manifests."""
    if not _EPIC_MANIFESTS_DIR.exists():
        return
    for manifest_file in _EPIC_MANIFESTS_DIR.glob("*.item"):
        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        if "Among Us" in data.get("DisplayName", ""):
            loc = data.get("InstallLocation", "")
            if loc:
                yield Path(loc)


def find_epic_among_us():
    """Try to locate the Epic Games Among Us install folder. Return path str or None."""
    candidates = list(_epic_manifest_candidates())
    for base in _EPIC_FALLBACKS:
        candidates.append(Path(base) / AMONG_US_FOLDER_NAME)
    return _first_valid(candidates)
