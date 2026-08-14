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
