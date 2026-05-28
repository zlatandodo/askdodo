"""
AskLivermore API client.
Login via Playwright once to get Supabase JWT, then calls REST API directly.
"""
import asyncio
import json
import logging
import ssl
import time
import urllib.request
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import os

load_dotenv()

log = logging.getLogger(__name__)

BASE_URL = "https://www.asklivermore.com"
TOKEN_FILE = Path(__file__).parent.parent / "token.json"

# Confirmed slugs from /api/scanner-counts
SCANNER_SLUGS = {
    # Universe
    "trend_template":             "trend-template",
    # Primary swing-trading pattern scanners
    "golden_pocket":              "golden-pocket",
    "vcp":                        "vcp",
    "livermore_buy_the_dip":      "livermore-buy-the-dip",
    "pocket_pivot":               "pocket-pivot",
    # Additional pattern scanners (available but not in default config)
    "high_tight_flag":            "high-tight-flag",
    "episodic_pivot":             "episodic-pivot",
    "power_play":                 "power-play",
    "cup_and_handle":             "cup-and-handle",
    "bull_flag":                  "bull-flag",
    "flat_base":                  "flat-base",
    "buyable_gap_up":             "buyable-gap-up",
    # Confirmation scanners
    "insider_buying":             "insider-buying",
    "institutional_accumulation": "institutional-accumulation",
    "sector_leader":              "sector-leader",
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

MAX_RETRIES = 3
RETRY_DELAY = 5


class AuthError(Exception):
    """JWT could not be obtained or refreshed."""


def _load_saved_token() -> Optional[dict]:
    """Load token from disk. Returns None if missing or expired."""
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text())
        import base64
        payload = data["access_token"].split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        if claims["exp"] - time.time() > 60:
            return data
        log.info("Saved token expired.")
        return None
    except Exception as e:
        log.warning(f"Could not load saved token: {e}")
        return None


def _save_token(token_data: dict) -> None:
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    log.info(f"Token saved to {TOKEN_FILE}")


async def _login_playwright() -> dict:
    """Login via Playwright, extract Supabase JWT from localStorage."""
    from playwright.async_api import async_playwright
    email = os.getenv("ASKLIVERMORE_EMAIL", "")
    password = os.getenv("ASKLIVERMORE_PASSWORD", "")

    log.info("Logging in via Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        await page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.click("button:has-text('Login')")
        await page.wait_for_timeout(1500)
        await page.fill("#loginEmail", email)
        await page.fill("#loginPassword", password)
        await page.click("button:has-text('Sign in')")
        await page.wait_for_timeout(5000)

        ls_raw = await page.evaluate(
            "() => localStorage.getItem('sb-dwihwpjhzssmssdewzof-auth-token')"
        )
        await browser.close()

    if not ls_raw:
        raise AuthError("Login failed: no Supabase token in localStorage. Check credentials.")

    token_data = json.loads(ls_raw)
    log.info("Login successful, JWT obtained.")
    return token_data


def get_token() -> str:
    """Return a valid access token, logging in if necessary."""
    saved = _load_saved_token()
    if saved:
        log.info("Using saved JWT token.")
        return saved["access_token"]

    token_data = asyncio.run(_login_playwright())
    _save_token(token_data)
    return token_data["access_token"]


def _api_get(path: str, token: str) -> dict:
    """Make an authenticated GET request to the AskLivermore API."""
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": f"{BASE_URL}/",
        },
    )
    resp = urllib.request.urlopen(req, timeout=30, context=SSL_CTX)
    return json.loads(resp.read())


def fetch_scanner(scanner_name: str, token: str) -> Optional[list[dict]]:
    """Fetch results for one scanner. Returns list of ticker dicts or None on failure."""
    slug = SCANNER_SLUGS.get(scanner_name)
    if not slug:
        log.warning(f"[{scanner_name}] No slug configured. Skipping.")
        return None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log.info(f"[{scanner_name}] Fetching /api/scanners/{slug}/results (attempt {attempt})")
            data = _api_get(f"/api/scanners/{slug}/results", token)
            matches = data.get("matches", [])
            log.info(f"[{scanner_name}] ✅ {len(matches)} results")
            return matches
        except Exception as e:
            log.warning(f"[{scanner_name}] Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
            else:
                log.error(f"[{scanner_name}] All attempts failed. Skipping.")
                return None


def run_all_downloads(config: dict) -> dict[str, Optional[list[dict]]]:
    """
    Fetch all 13 scanners via API.
    Returns dict: scanner_name -> list of ticker dicts (or None if failed).
    """
    token = get_token()
    results: dict[str, Optional[list[dict]]] = {}

    for scanner_cfg in config.get("scanners", []):
        name = scanner_cfg["name"]
        results[name] = fetch_scanner(name, token)

    ok = sum(1 for v in results.values() if v is not None)
    fail = sum(1 for v in results.values() if v is None)
    log.info(f"API fetch complete: {ok} OK, {fail} failed out of {len(results)}")
    return results
