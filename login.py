#!/usr/bin/env python3
"""
bits-wifi-keepalive
Keeps your BITS Pilani WiFi session alive automatically.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from datetime import datetime, timedelta

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    print("Error: 'requests' is not installed.  Run: pip3 install requests")
    sys.exit(1)

try:
    from config import USERNAME, PASSWORD, INTERVAL, KEEPALIVE_URL
except ImportError:
    USERNAME      = ""
    PASSWORD      = ""
    INTERVAL      = 13000
    KEEPALIVE_URL = ""   # paste from browser on first run


HTTP_PROBES = [
    "http://captive.apple.com",
    "http://neverssl.com",
    "http://connectivitycheck.gstatic.com/generate_204",
    "http://example.com",
]

CONNECT_TIMEOUT = 8
READ_TIMEOUT    = 12
RETRY_WAIT      = 30   # seconds between login retries


# ─── Logging ─────────────────────────────────────────────────────────────────

def setup_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("bits-wifi")
    if logger.handlers:
        logger.handlers.clear()
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(h)
    logger.propagate = False
    return logger


log = setup_logger()


# ─── Portal helpers ───────────────────────────────────────────────────────────

def ping_keepalive(session: requests.Session, keepalive_url: str) -> bool:
    """
    GET the keepalive URL.
    Returns True  → session still alive (timer reset).
    Returns False → session expired (need to re-login).
    """
    try:
        r = session.get(keepalive_url,
                        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                        verify=False,
                        allow_redirects=True)
    except requests.exceptions.RequestException as e:
        log.error("Keepalive ping error: %s", e)
        return False

    if "keepalive" in r.url and r.status_code == 200:
        secs = _parse_countdown(r.text)
        if secs:
            log.info("✅  Keepalive OK — resets in %s", _fmt_time(secs))
        else:
            log.info("✅  Keepalive OK.")
        return True

    if "login" in r.url:
        log.warning("Session expired — portal redirected to login page.")
        return False

    log.warning("Unexpected keepalive response: status=%d url=%s", r.status_code, r.url)
    return False


def login(username: str, password: str) -> str | None:
    """
    Trigger the firewall redirect by probing plain HTTP URLs, then POST credentials.
    Returns the new keepalive URL, or None on failure.
    """
    session = requests.Session()
    session.verify = False

    for probe in HTTP_PROBES:
        log.info("Probing %s to trigger firewall redirect ...", probe)
        try:
            r = session.get(probe,
                            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                            allow_redirects=True)
        except requests.exceptions.RequestException as e:
            log.warning("  Probe failed: %s", e)
            continue

        login_url = r.url
        log.debug("Probe landed on: %s", login_url)

        # If the firewall intercepted, we'll be on the BITS login page
        if "fw.bits-pilani.ac.in" in login_url and "login" in login_url:
            log.info("Firewall redirect captured: %s", login_url)
            return _post_credentials(session, login_url, username, password)

        # If we reached the actual site, we're already authenticated
        if "fw.bits-pilani.ac.in" not in login_url:
            log.info("Probe reached %s directly — already authenticated?", login_url)
            # Try the keepalive URL from config if available
            if KEEPALIVE_URL:
                log.info("Using KEEPALIVE_URL from config to verify ...")
                if ping_keepalive(session, KEEPALIVE_URL):
                    return KEEPALIVE_URL
            log.warning("Already online but no valid keepalive URL found.")
            return None

    log.error("❌  All probes failed. Check WiFi connection.")
    return None


def _post_credentials(session: requests.Session,
                      login_url: str,
                      username: str,
                      password: str) -> str | None:
    log.info("Posting credentials for user '%s' ...", username)
    try:
        r = session.post(
            login_url,
            data={"username": username, "password": password},
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            allow_redirects=True,
            verify=False,
        )
    except requests.exceptions.RequestException as e:
        log.error("POST failed: %s", e)
        return None

    if "keepalive" in r.url:
        log.info("✅  Login successful. Keepalive URL: %s", r.url)
        return r.url

    if "login" in r.url:
        log.error("❌  Login rejected — wrong username or password?")
        return None

    log.error("❌  Unexpected post-login URL: %s", r.url)
    return None


def _parse_countdown(html: str) -> int | None:
    m = re.search(r"Authentication refresh in\s+(\d+)\s+seconds", html)
    return int(m.group(1)) if m else None


def _fmt_time(seconds: int) -> str:
    return str(timedelta(seconds=seconds))


# ─── Main loop ────────────────────────────────────────────────────────────────

def run(username: str, password: str, interval: int, once: bool = False) -> None:
    log.info("=" * 56)
    log.info("  BITS Pilani WiFi Keepalive")
    log.info("  User     : %s", username)
    log.info("  Interval : %d s (~%d min)", interval, interval // 60)
    log.info("=" * 56)

    session      = requests.Session()
    session.verify = False
    keepalive_url: str | None = KEEPALIVE_URL or None

    while True:

        # ── If we have a keepalive URL, try to ping it first ─────────────────
        if keepalive_url:
            log.info("🔄  Pinging keepalive ...")
            if ping_keepalive(session, keepalive_url):
                if once:
                    log.info("--once: done.")
                    return
                wake = datetime.now() + timedelta(seconds=interval)
                log.info("💤  Next ping at %s", wake.strftime("%H:%M:%S"))
                time.sleep(interval)
                continue
            else:
                # Session expired — fall through to re-login
                keepalive_url = None
                session = requests.Session()
                session.verify = False

        # ── Login (first run or after session expiry) ─────────────────────────
        log.info("🔑  Logging in ...")
        keepalive_url = login(username, password)

        if keepalive_url is None:
            log.warning("Login failed. Retrying in %d s ...", RETRY_WAIT)
            time.sleep(RETRY_WAIT)
            continue

        if once:
            log.info("--once: done.")
            return

        wake = datetime.now() + timedelta(seconds=interval)
        log.info("💤  Next ping at %s", wake.strftime("%H:%M:%S"))
        time.sleep(interval)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Keep your BITS Pilani WiFi session alive.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--username", default=USERNAME,  help="Your BITS ID")
    p.add_argument("--password", default=PASSWORD,  help="Your WiFi password")
    p.add_argument("--interval", type=int, default=INTERVAL,
                   help="Seconds between keepalive pings")
    p.add_argument("--once",    action="store_true", help="Run one cycle and exit")
    p.add_argument("--verbose", action="store_true", help="Debug logging")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    global log
    log = setup_logger(verbose=args.verbose)

    if not args.username or not args.password:
        log.error("No credentials. Edit config.py or use --username / --password.")
        return 1

    try:
        run(args.username, args.password, args.interval, once=args.once)
    except KeyboardInterrupt:
        log.info("👋  Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())