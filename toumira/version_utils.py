"""Helpers for comparing dotted version strings (e.g. ``"1.6.1"``)."""


def _parts(version):
    """Split a dotted version string into an int tuple, tolerating garbage."""
    try:
        return tuple(int(x) for x in version.split("."))
    except ValueError:
        return (0,)


def version_gt(a, b):
    """Return True if version string ``a`` is strictly greater than ``b``."""
    return _parts(a) > _parts(b)


def _semver_key(version):
    """Sort key where ``1.0.0-alpha.2 < 1.0.0-alpha.10 < 1.0.0`` (semver precedence)."""
    core, _, pre = version.strip().lstrip("vV").split("+", 1)[0].partition("-")
    if not pre:
        return (_parts(core), (1,))
    # Numeric identifiers sort before alphanumeric ones, as semver requires.
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return (_parts(core), (0,) + ids)


def semver_gt(a, b):
    """Return True if semver ``a`` (pre-release suffixes allowed) is newer than ``b``."""
    return _semver_key(a) > _semver_key(b)
