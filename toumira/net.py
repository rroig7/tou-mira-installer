"""HTTPS helpers: verified TLS by default, with a no-verify fallback.

Certificate verification is attempted first so downloads are authenticated on
normal networks. If (and only if) the TLS handshake fails — e.g. a corporate
proxy or packaged-exe environment intercepting HTTPS with a self-signed cert —
the request is retried with verification disabled. That fallback trades away
authenticity, so it is a last resort and is surfaced to the caller via
``on_log``. Callers that must not accept unauthenticated data (e.g. the
installer self-update, which executes what it downloads) pass
``allow_insecure=False``.
"""
import ssl
import urllib.error
import urllib.request

from toumira.config import USER_AGENT

_CHUNK = 64 * 1024

# Cached SSL contexts (building them, especially the verified one, is not free).
_verified_ctx = None
_no_verify_ctx = None


def _make_verified_ssl_ctx():
    """Return an SSL context that verifies certificates.

    Prefers the OS trust store via ``truststore`` (handles corporate proxies
    whose root CA is installed system-wide), then ``certifi``, then the stdlib
    default (which on Windows already loads the system certificate store).
    """
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        pass
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


def make_no_verify_ssl_ctx():
    """Return an SSL context with certificate verification disabled."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _verified_opener():
    global _verified_ctx
    if _verified_ctx is None:
        _verified_ctx = _make_verified_ssl_ctx()
    return _build_opener(_verified_ctx)


def _no_verify_opener():
    global _no_verify_ctx
    if _no_verify_ctx is None:
        _no_verify_ctx = make_no_verify_ssl_ctx()
    return _build_opener(_no_verify_ctx)


def _build_opener(ctx):
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    opener.addheaders = [("User-Agent", USER_AGENT)]
    return opener


def _is_ssl_error(exc):
    """True if ``exc`` is (or wraps) a TLS/certificate failure."""
    if isinstance(exc, ssl.SSLError):
        return True
    return isinstance(getattr(exc, "reason", None), ssl.SSLError)


def _run_with_fallback(operation, on_log=None, allow_insecure=True):
    """Run ``operation(opener)`` verified; on a TLS failure retry unverified
    (unless ``allow_insecure`` is False, in which case the error propagates)."""
    try:
        return operation(_verified_opener())
    except (urllib.error.URLError, ssl.SSLError) as exc:
        if not allow_insecure or not _is_ssl_error(exc):
            raise
        if on_log:
            on_log(
                "Secure (verified) connection failed; retrying without "
                "certificate verification. The download will not be authenticated."
            )
        return operation(_no_verify_opener())


def open_url(url, timeout=10, on_log=None, allow_insecure=True):
    """Open ``url`` (verified, then unverified on TLS failure). Returns a response."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return _run_with_fallback(lambda opener: opener.open(req, timeout=timeout),
                              on_log, allow_insecure)


def download_file(url, dest, on_progress=None, progress_start=0, progress_end=100,
                  on_log=None, timeout=30, allow_insecure=True):
    """Download ``url`` to ``dest`` (verified, then unverified on TLS failure).

    ``on_progress`` (if given) is called with an integer percentage clamped to
    ``[progress_start, progress_end]``, and always receives ``progress_end`` once
    the download completes.
    """
    span = progress_end - progress_start

    def _do(opener):
        with opener.open(url, timeout=timeout) as resp, open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            read = 0
            while True:
                data = resp.read(_CHUNK)
                if not data:
                    break
                out.write(data)
                read += len(data)
                if on_progress and total > 0:
                    pct = progress_start + min(int(read * span / total), span)
                    on_progress(pct)
        if on_progress:
            on_progress(progress_end)

    _run_with_fallback(_do, on_log, allow_insecure)
