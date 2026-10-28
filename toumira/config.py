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

# --- Installer self-update ---------------------------------------------------
# Single source of truth for the installer's version. Must match the GitHub
# release tag (``v<APP_VERSION>``) or users will be prompted to update forever.
APP_VERSION = "1.2.1"
APP_RELEASES_API_URL = (
    "https://api.github.com/repos/rroig7/tou-mira-installer/releases/latest"
)
APP_RELEASES_PAGE_URL = "https://github.com/rroig7/tou-mira-installer/releases/latest"

# --- Install metadata files (written into the install folder) ----------------
VERSION_FILE = "toumira_version.txt"
MANIFEST_FILE = "toumira_files.txt"

# --- HTTP --------------------------------------------------------------------
USER_AGENT = f"TOU-Mira-Installer/{APP_VERSION}"
