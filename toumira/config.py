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

# --- Install metadata files (written into the install folder) ----------------
VERSION_FILE = "toumira_version.txt"
MANIFEST_FILE = "toumira_files.txt"

# --- HTTP --------------------------------------------------------------------
USER_AGENT = "TOU-Mira-Installer/1.0"
