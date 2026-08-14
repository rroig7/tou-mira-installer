"""HTTPS helpers: a non-verifying SSL context and download utilities.

Certificate verification is intentionally disabled because some environments
(packaged exe, corporate proxies) intercept HTTPS with self-signed certs, which
would otherwise break every download.
"""
import ssl
import urllib.request

from toumira.config import USER_AGENT


def make_no_verify_ssl_ctx():
    """Return an SSL context with certificate verification disabled."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def build_opener():
    """Build a urllib opener that skips SSL verification and sets a User-Agent."""
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=make_no_verify_ssl_ctx())
    )
    opener.addheaders = [("User-Agent", USER_AGENT)]
    return opener


def install_opener():
    """Install the non-verifying opener as the process-wide default."""
    urllib.request.install_opener(build_opener())


def open_url(url, timeout=10):
    """Open ``url`` with a User-Agent header and no SSL verification."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, context=make_no_verify_ssl_ctx(), timeout=timeout)


def download_file(url, dest, on_progress=None, progress_start=0, progress_end=100):
    """Download ``url`` to ``dest``, reporting progress in a bounded range.

    ``on_progress`` (if given) is called with an integer percentage clamped to
    ``[progress_start, progress_end]``. It always receives ``progress_end`` once
    the download completes.
    """
    span = progress_end - progress_start

    def report_hook(blocks, block_size, total_size):
        if on_progress and total_size > 0:
            pct = progress_start + min(int(blocks * block_size * span / total_size), span)
            on_progress(pct)

    urllib.request.urlretrieve(url, dest, reporthook=report_hook)
    if on_progress:
        on_progress(progress_end)
