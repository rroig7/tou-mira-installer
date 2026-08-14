"""TOU-Mira Mod Auto-Installer — entry point.

The implementation lives in the :mod:`toumira` package; this thin shim keeps the
original filename working for the makefile and the PyInstaller build command in
README.md.
"""
from toumira.app import main

if __name__ == "__main__":
    main()
