"""Read and write the install metadata (version + file manifest)."""
from pathlib import Path

from toumira.config import MANIFEST_FILE, VERSION_FILE


def _write_text_safe(path, content):
    """Write text to ``path``, silently ignoring OS errors."""
    try:
        Path(path).write_text(content, encoding="utf-8")
    except OSError:
        pass


def write_metadata(install_path, version, installed_files):
    """Record the installed version and file manifest in the install folder."""
    install_path = Path(install_path)
    _write_text_safe(install_path / VERSION_FILE, version)
    _write_text_safe(install_path / MANIFEST_FILE, "\n".join(installed_files))


def read_version(install_path):
    """Return the installed version string, or ``"0"`` if unknown."""
    if not install_path:
        return "0"
    try:
        return (Path(install_path) / VERSION_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return "0"


def add_manifest_entry(install_path, entry):
    """Append ``entry`` to an existing manifest. No-op without one, or if already listed."""
    entries = read_manifest(install_path)
    if entries is None or entry in entries:
        return
    _write_text_safe(Path(install_path) / MANIFEST_FILE, "\n".join(entries + [entry]))


def read_manifest(install_path):
    """Return the list of non-empty manifest entries, or None if absent."""
    manifest_path = Path(install_path) / MANIFEST_FILE
    if not manifest_path.exists():
        return None
    return [line for line in manifest_path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def remove_metadata(install_path):
    """Delete the version and manifest files, ignoring missing ones."""
    for name in (MANIFEST_FILE, VERSION_FILE):
        try:
            (Path(install_path) / name).unlink(missing_ok=True)
        except OSError:
            pass
