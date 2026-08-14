"""Zip extraction and file copying, decoupled from the GUI via callbacks."""
import os
import shutil
import tempfile
import zipfile
from pathlib import Path


def _strip_wrapper_folders(root, on_log=None):
    """Descend past single-folder wrappers so we copy the real contents.

    Some archives nest everything inside one (or more) top-level folders; walk
    into them until we reach a directory with actual mod content.
    """
    content_root = root
    depth = 0
    while True:
        entries = list(content_root.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            content_root = entries[0]
            depth += 1
        else:
            break
    if depth > 0 and on_log:
        on_log(f"Detected {depth} wrapper folder(s); using contents of '{content_root.name}'.")
    return content_root


def extract_and_copy(zip_path, dest_root, on_log=None, on_progress=None,
                     progress_start=0, progress_end=100):
    """Extract ``zip_path`` into ``dest_root``, skipping wrapper folders.

    Progress is reported (via ``on_progress``) across ``[progress_start,
    progress_end]``, split 60/40 between extraction and copying. Returns a list
    of paths (relative to ``dest_root``, as strings) for every file and
    directory written — used to build the uninstall manifest.
    """
    installed = []
    tmp_extract = None
    try:
        tmp_extract = tempfile.mkdtemp(prefix="toumira_extract_")
        if on_log:
            on_log("Extracting archive…")
        extract_span = int((progress_end - progress_start) * 0.6)
        copy_span = (progress_end - progress_start) - extract_span

        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.namelist()
            total = max(len(members), 1)
            for i, member in enumerate(members):
                zf.extract(member, tmp_extract)
                if on_progress:
                    pct = progress_start + int((i + 1) * extract_span / total)
                    on_progress(min(pct, progress_start + extract_span))

        content_root = _strip_wrapper_folders(Path(tmp_extract), on_log)

        entries = list(content_root.iterdir())
        if not entries:
            raise RuntimeError("Archive appears to be empty after extraction.")
        total = max(len(entries), 1)
        copy_base = progress_start + extract_span
        dest_root_path = Path(dest_root)
        for i, entry in enumerate(entries):
            dst = dest_root_path / entry.name
            if entry.is_dir():
                shutil.copytree(entry, dst, dirs_exist_ok=True)
                # Record every file and directory placed under dst
                for item in dst.rglob("*"):
                    installed.append(str(item.relative_to(dest_root_path)))
            else:
                shutil.copy2(entry, dst)
                installed.append(str(dst.relative_to(dest_root_path)))
            if on_progress:
                pct = copy_base + int((i + 1) * copy_span / total)
                on_progress(min(pct, progress_end))
    finally:
        if tmp_extract and os.path.exists(tmp_extract):
            shutil.rmtree(tmp_extract, ignore_errors=True)
    return installed


def extract_single_exe(zip_path, dest_dir, final_name):
    """Extract the first .exe from ``zip_path`` into ``dest_dir`` as ``final_name``."""
    dest_dir = Path(dest_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        exe_names = [n for n in zf.namelist() if n.lower().endswith(".exe")]
        if not exe_names:
            raise RuntimeError("Archive contains no .exe file.")
        zf.extract(exe_names[0], str(dest_dir))
        extracted = dest_dir / exe_names[0]
        final = dest_dir / final_name
        if extracted != final:
            extracted.rename(final)
    return final
