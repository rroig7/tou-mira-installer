# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Windows-only PySide6 (via `qtpy`) GUI that installs the **TOU-Mira** Among Us mod (https://github.com/AU-Avengers/TOU-Mira) for Steam or Epic Games. It is an unofficial installer; the mod itself is made by the TOU-Mira team. Distributed as a single-file PyInstaller `.exe`.

## Commands

The makefile assumes Windows venv layout (`.venv/Scripts/python`).

```bash
make install   # create .venv and install requirements.txt
make run       # run the app (python main.py)
make build     # PyInstaller --onefile --windowed → dist/TOU-Mira-Installer-v$(VERSION).exe
make clean     # remove build/, dist/, *.spec, __pycache__ (via PowerShell)
```

There is no test suite, linter, or formatter configured. `test/` is gitignored (local scratch only). Verify changes by running the app.

**Releasing the installer:** bump `APP_VERSION` in `toumira/config.py` (the single source of truth — the makefile, `__version__` and `USER_AGENT` all derive from it), `make build`, then publish a GitHub release on `rroig7/tou-mira-installer` tagged `v<APP_VERSION>` with the built `.exe` attached, marked as latest. The self-updater depends on this: a tag that doesn't match the embedded version causes endless update prompts, and a release without an `.exe` asset makes the updater offer to open the browser instead. The README's build command is a manual equivalent of `make build`.

## Architecture

`main.py` is a thin shim (kept for the makefile/PyInstaller) → `toumira.app.main()` → `toumira.ui.MainWindow`.

Layering: `ui.py` is the only module that touches widgets/dialogs. Long-running work runs in `QObject` workers moved onto a `QThread` (`releases.ReleaseFetchWorker`, `installer.InstallWorker`, `updater.UpdateCheckWorker`/`UpdateDownloadWorker`) that communicate back only via Qt signals (`progress`, `log`, `finished`/`error`). The pure helper modules (`net`, `archive`, `metadata`, `detection`) have no Qt dependency and report back through optional `on_log` / `on_progress` callbacks, which the workers wire to their signal `.emit` methods. Keep that separation: don't import Qt into the helpers, and don't do I/O-heavy work on the GUI thread.

Progress is a single 0–100 bar shared across phases; helpers take `progress_start`/`progress_end` so the caller assigns each phase a slice (e.g. Steam: download 0–75, extract 75–100; Epic: copy 0–30, starter 30–40, download 40–75, extract 75–100).

### Release discovery
`releases.py` hits the GitHub releases API, skips drafts/prereleases, strips the leading `v` from tags, and picks zip assets by filename: name containing `steam` → Steam URL; `epic` or `msstore` → Epic URL. The first release returned is treated as "latest".

### The two install flows differ fundamentally
- **Steam**: installs *in place* into the detected Among Us folder (registry `SteamPath` → `libraryfolders.vdf` → hard-coded drive fallbacks). An existing `BepInEx/` folder is deleted before reinstall. "Installed" = `BepInEx/` exists.
- **Epic**: *copies* the whole Epic Among Us folder (found via Epic Launcher `.item` manifests or fallbacks) to a separate destination (default `~/Desktop/Among Us - TOU Mira`), downloads `EpicGamesStarter.exe` (third-party, `whichtwix/EpicGamesStarter`) into it, then extracts the mod there. The destination may not be under Program Files (the starter can't launch from there). Uninstall deletes the entire destination folder. "Installed" = `toumira_version.txt` exists.

### Optional BetterCrewLink add-on (`bettercrewlink.py`)
A checkbox in the UI adds BetterCrewLink (https://github.com/OhMyGuus/BetterCrewLink, a standalone Electron app — not mod files) to either flow. After the mod is installed and its metadata written, `InstallWorker` fetches BetterCrewLink's `/releases/latest`, downloads the `*Setup*.exe` asset to a fresh temp dir (verified TLS only + SHA-256 `digest` check via `net.verify_sha256_digest`, since it's executed) and runs it with `/S` (silent, per-user NSIS, no UAC). When enabled the mod phases are scaled into 0–60 of the bar via `InstallWorker._report_progress` and BetterCrewLink takes 60–100. A BetterCrewLink failure doesn't fail the install; it's appended to the success message. Installed state/version is read from the `Uninstall` registry key (`DisplayName` starting `Better-CrewLink`). The installer never uninstalls it.

### Optional BetterCrewLink-TOU + voice bridge (alpha; `bridge.py`, `bettercrewlink.TOU`)
A second checkbox (`tou_checkbox`, worker flag `install_tou_voice`) is the *alternative* to
official BetterCrewLink. It installs two things:

* **BetterCrewLink-TOU**, the `rroig7/BetterCrewLink` fork, as a separate app. It has its own
  install folder (`Programs\bettercrewlink-tou`), settings and Uninstall entry (`DisplayName`
  `BetterCrewLink-TOU …`).
* **`TouMiraBclBridge.dll`**, a BepInEx plugin from `rroig7/whg-tou-mira`, which lets that build
  mute jailed, blackmailed and controlled players. Official BetterCrewLink ignores it.

The two checkboxes are mutually exclusive: ticking one unticks the other, and neither is fine. If
both reach the worker, TOU wins. `bettercrewlink.py` serves both builds through a `Source`
(`OFFICIAL` / `TOU`): the same download, digest check and `/S` run, and the same 60–100% progress
slice. TOU's releases, and the bridge's, are read from `/releases` (not `/releases/latest`)
because alpha builds are prereleases. The newest non-draft release with a matching asset wins. If
official BetterCrewLink is already installed, the result message suggests uninstalling it. We
still never uninstall anything ourselves.

`InstallWorker._finalize` installs the bridge after the mod files and *before* `write_metadata`, appending
`BepInEx\plugins\TouMiraBclBridge.dll` to the manifest so the normal uninstall removes it. It's
downloaded with verified TLS only plus the SHA-256 `digest` check (the game loads it), to a `.part`
file that is then `os.replace`d. It's ~30 KB, so it gets no progress slice. As with BetterCrewLink,
a failure doesn't fail the install. The release notes' `Built for TOU-Mira: <tag>[, <tag>…]` line
lists the supported mod versions; installing an unlisted one still installs the bridge but appends
a warning. That release contract is documented in whg-tou-mira's README; keep both sides in sync.
"Installed" = the DLL exists in the selected folder's `BepInEx/plugins`.

### Install metadata
After a successful install, `metadata.write_metadata` writes two files into the install folder: `toumira_version.txt` (used for the "Update available" banner via `version_utils.version_gt`, a numeric dotted-tuple compare) and `toumira_files.txt` (manifest of every path written, relative to the install root). Steam uninstall uses the manifest to delete only mod files, then removes leftover `BepInEx/` (runtime logs/config aren't in the manifest); with no manifest it falls back to deleting `BepInEx/`.

### Archive handling
`archive.extract_and_copy` extracts to a temp dir, descends through any single-folder wrapper directories, then merges contents into the destination (`copytree(dirs_exist_ok=True)`), returning the manifest list.

### Networking / TLS
All HTTP goes through `net.py` (`open_url`, `download_file`). It tries a verified TLS context first (`truststore` OS store → `certifi` → stdlib default) and, **only on an SSL error**, retries with verification disabled, logging a warning via `on_log`. This fallback was added deliberately to fix SSL failures behind intercepting proxies/in the packaged exe — preserve the verified-first ordering and the user-visible warning when touching it. `truststore`/`certifi` are optional imports. Pass `allow_insecure=False` to disable the fallback (the self-updater does, since it executes what it downloads).

### Installer self-update (`updater.py`)
Only active in the frozen build (`sys.frozen`); `make run` from source never checks. On launch `MainWindow` queries the installer repo's `/releases/latest`; if the tag is newer than `APP_VERSION` it prompts (deferred until any running mod install finishes). On yes it downloads the release's `.exe` asset next to the running exe under the asset's own name (via `.part` + `os.replace`), verifies GitHub's SHA-256 asset `digest` when present, launches it detached with `--cleanup-old <old exe>`, and quits. The new process (`app.main` → `schedule_old_exe_cleanup`) deletes the old exe in a background thread, retrying until the old process releases its lock; it only deletes an `.exe` in its own directory and never itself. The child is launched with `PYINSTALLER_RESET_ENVIRONMENT=1` and `_PYI_*` vars stripped so the onefile bootloader doesn't reuse the parent's soon-deleted extraction dir. Any failure falls back to offering the GitHub releases page.
