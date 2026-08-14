"""Fetch and parse TOU-Mira releases from the GitHub API."""
import json

from qtpy.QtCore import QObject, Signal

from toumira.config import GITHUB_API_URL
from toumira import net


def _asset_urls(release):
    """Return (steam_url, epic_url) for a GitHub release's zip assets."""
    steam_url = epic_url = ""
    for asset in release.get("assets", []):
        name = asset.get("name", "").lower()
        url = asset.get("browser_download_url", "")
        if not name.endswith(".zip"):
            continue
        if "steam" in name:
            steam_url = url
        elif "epic" in name or "msstore" in name:
            epic_url = url
    return steam_url, epic_url


def parse_releases(data):
    """Convert raw GitHub API data into a list of release dicts.

    Draft and prerelease entries are skipped. Each returned dict has keys
    ``version``, ``steam_url`` and ``epic_url``.
    """
    releases = []
    for release in data:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name", "").lstrip("v")
        if not tag:
            continue
        steam_url, epic_url = _asset_urls(release)
        releases.append({"version": tag, "steam_url": steam_url, "epic_url": epic_url})
    return releases


class ReleaseFetchWorker(QObject):
    """Fetches all TOU-Mira releases from GitHub on a background thread."""

    releases_fetched = Signal(object)  # list of release dicts
    error = Signal(str)

    def run(self):
        try:
            with net.open_url(GITHUB_API_URL, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            self.releases_fetched.emit(parse_releases(data))
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))
