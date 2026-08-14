"""TOU-Mira Mod Auto-Installer package.

A small GUI installer for the TOU-Mira Among Us mod. The package is split into
focused modules:

* :mod:`toumira.config`        – shared constants and URLs
* :mod:`toumira.version_utils` – version-string comparison
* :mod:`toumira.net`           – HTTPS/SSL helpers and downloads
* :mod:`toumira.detection`     – Steam/Epic Among Us discovery
* :mod:`toumira.archive`       – zip extraction and file copying
* :mod:`toumira.metadata`      – install version/manifest bookkeeping
* :mod:`toumira.releases`      – GitHub release parsing and fetch worker
* :mod:`toumira.installer`     – background install worker
* :mod:`toumira.ui`            – the Qt main window
* :mod:`toumira.app`           – application entry point
"""

from toumira.app import main

__all__ = ["main"]
__version__ = "1.0.0"
