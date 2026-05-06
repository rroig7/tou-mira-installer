"""Tests for the SSL bypass logic and reachability of all download URLs."""
import ssl
import sys
import urllib.request

STEAM_MOD_URL = (
    "https://github.com/AU-Avengers/TOU-Mira/releases/download/"
    "1.6.1/TouMira-v1.6.1-x86-steam-itch.zip"
)
EPIC_MOD_URL = (
    "https://github.com/AU-Avengers/TOU-Mira/releases/download/"
    "1.6.1/TouMira-v1.6.1-x64-epic-msstore.zip"
)
EPIC_STARTER_URL = (
    "https://github.com/whichtwix/EpicGamesStarter/releases/download/"
    "1.1.0/EpicGamesStarter.exe.zip"
)


def make_ssl_opener():
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_ctx)
    )
    opener.addheaders = [("User-Agent", "TOU-Mira-Installer/1.0")]
    return opener, ssl_ctx


def test_ssl_context_flags():
    _, ctx = make_ssl_opener()
    assert ctx.check_hostname is False, "check_hostname should be False"
    assert ctx.verify_mode == ssl.CERT_NONE, "verify_mode should be CERT_NONE"
    print("PASS  ssl context flags are correct")


def test_set_order_does_not_raise():
    ctx = ssl.create_default_context()
    try:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    except Exception as e:
        print(f"FAIL  unexpected exception setting SSL flags: {e}")
        sys.exit(1)
    print("PASS  SSL flag assignment order is safe")


def test_opener_has_user_agent():
    opener, _ = make_ssl_opener()
    headers = dict(opener.addheaders)
    assert "User-Agent" in headers, "User-Agent header missing"
    assert "TOU-Mira-Installer" in headers["User-Agent"], "unexpected User-Agent value"
    print("PASS  opener carries correct User-Agent")


def _head(url, label):
    """Send a HEAD request and assert a 2xx/3xx response."""
    opener, _ = make_ssl_opener()
    urllib.request.install_opener(opener)
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
    assert code in range(200, 400), f"{label}: unexpected HTTP status {code}"
    print(f"PASS  {label} reachable (status {code})")


def test_steam_mod_url():
    _head(STEAM_MOD_URL, "Steam mod URL")


def test_epic_mod_url():
    _head(EPIC_MOD_URL, "Epic mod URL")


def test_epic_starter_url():
    _head(EPIC_STARTER_URL, "EpicGamesStarter.exe.zip URL")


def test_ssl_bypass_vs_strict():
    """Strict SSL fails on expired cert; bypass opener succeeds."""
    BAD_URL = "https://expired.badssl.com/"
    strict_ctx = ssl.create_default_context()
    strict_opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=strict_ctx)
    )
    strict_opener.addheaders = [("User-Agent", "test")]
    urllib.request.install_opener(strict_opener)
    try:
        urllib.request.urlopen(
            urllib.request.Request(BAD_URL, method="HEAD"), timeout=10
        )
        print("SKIP  strict SSL did not raise (network may be intercepting TLS — skip)")
        return
    except urllib.error.URLError:
        pass

    bypass_opener, _ = make_ssl_opener()
    urllib.request.install_opener(bypass_opener)
    try:
        urllib.request.urlopen(
            urllib.request.Request(BAD_URL, method="HEAD"), timeout=10
        )
        print("PASS  SSL bypass allows connecting to expired-cert host")
    except urllib.error.URLError as e:
        print(f"FAIL  SSL bypass still blocked expired-cert host: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test_ssl_context_flags()
    test_set_order_does_not_raise()
    test_opener_has_user_agent()
    test_steam_mod_url()
    test_epic_mod_url()
    test_epic_starter_url()
    test_ssl_bypass_vs_strict()
    print("\nAll tests passed.")
