"""Shared configuration: constants, folder names, and remote URLs."""

# --- Branding ----------------------------------------------------------------
MOD_NAME = "Town of Us Mira"

# --- Among Us / mod layout ---------------------------------------------------
AMONG_US_FOLDER_NAME = "Among Us"
AMONG_US_EXE = "Among Us.exe"
BEPINEX_FOLDER = "BepInEx"
EPIC_INSTALL_FOLDER_NAME = "Among Us - TOU Mira"

# --- Platform identifiers ----------------------------------------------------
PLATFORM_STEAM = "steam"
PLATFORM_EPIC = "epic"

# --- Remote endpoints --------------------------------------------------------
GITHUB_API_URL = "https://api.github.com/repos/AU-Avengers/TOU-Mira/releases"
EPIC_STARTER_URL = (
    "https://github.com/whichtwix/EpicGamesStarter/releases/download/"
    "1.1.0/EpicGamesStarter.exe.zip"
)

# --- BetterCrewLink (optional proximity voice chat add-on) -------------------
BETTERCREWLINK_NAME = "BetterCrewLink"
BETTERCREWLINK_REPO_URL = "https://github.com/OhMyGuus/BetterCrewLink"
BETTERCREWLINK_RELEASES_API_URL = (
    "https://api.github.com/repos/OhMyGuus/BetterCrewLink/releases/latest"
)
# Prefix of the DisplayName its NSIS setup writes to the Uninstall registry key.
BETTERCREWLINK_DISPLAY_NAME = "Better-CrewLink"

# --- BetterCrewLink-TOU + TOU-Mira voice bridge (optional, alpha) -------------
# BetterCrewLink-TOU is a BetterCrewLink fork that, with the voice bridge BepInEx
# plugin, applies TOU-Mira role effects to voice (jailed, blackmailed and
# controlled players muted, ...). Official BetterCrewLink ignores the bridge, so
# the two are installed together, instead of official BetterCrewLink.
BCL_TOU_NAME = "BetterCrewLink-TOU"
# The full list, not /releases/latest: alpha builds are prereleases, which it skips.
BCL_TOU_RELEASES_API_URL = "https://api.github.com/repos/rroig7/BetterCrewLink/releases"
# DisplayName prefix in the Uninstall key; doesn't collide with "Better-CrewLink".
BCL_TOU_DISPLAY_NAME = "BetterCrewLink-TOU"

BRIDGE_NAME = "TOU-Mira voice bridge"
BRIDGE_REPO_URL = "https://github.com/rroig7/whg-tou-mira"
# Installed name. BetterCrewLink-TOU releases attach one build per supported TOU-Mira
# release as TouMiraBclBridge-<tou-mira-tag>.dll; see bridge.py.
BRIDGE_DLL_NAME = "TouMiraBclBridge.dll"

# --- Installer self-update ---------------------------------------------------
# Single source of truth for the installer's version. Must match the GitHub
# release tag (``v<APP_VERSION>``) or users will be prompted to update forever.
APP_VERSION = "1.5.0"
APP_RELEASES_API_URL = (
    "https://api.github.com/repos/rroig7/tou-mira-installer/releases/latest"
)
APP_RELEASES_PAGE_URL = "https://github.com/rroig7/tou-mira-installer/releases/latest"

# --- Install metadata files (written into the install folder) ----------------
VERSION_FILE = "toumira_version.txt"
MANIFEST_FILE = "toumira_files.txt"

# --- HTTP --------------------------------------------------------------------
USER_AGENT = f"TOU-Mira-Installer/{APP_VERSION}"
