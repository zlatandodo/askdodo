"""
Test login AskLivermore con email + password.
Apre Chrome visibile, fa login, fa screenshot della dashboard.

Run:  python3 login_setup.py
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

EMAIL = os.getenv("ASKLIVERMORE_EMAIL", "")
PASSWORD = os.getenv("ASKLIVERMORE_PASSWORD", "")
SCREENSHOT_PATH = Path(__file__).parent / "logs" / "login_test.png"
LOGIN_URL = "https://asklivermore.com/login"


async def main() -> None:
    print("=== AskLivermore Login Test ===")
    print(f"Email: {EMAIL}")
    print(f"Password: {'*' * len(PASSWORD)}")
    print()

    SCREENSHOT_PATH.parent.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, slow_mo=500)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        print(f"Apro {LOGIN_URL}...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        print(f"URL corrente: {page.url}")
        await page.screenshot(path=str(SCREENSHOT_PATH))
        print(f"Screenshot salvato: {SCREENSHOT_PATH}")

        # Try to find and fill login form
        # Common selectors for email/password forms
        email_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[id="email"]',
            'input[placeholder*="email" i]',
            'input[placeholder*="Email" i]',
        ]
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id="password"]',
        ]

        # Fill email
        email_filled = False
        for sel in email_selectors:
            try:
                await page.fill(sel, EMAIL, timeout=3000)
                print(f"✅ Email inserita ({sel})")
                email_filled = True
                break
            except Exception:
                continue

        if not email_filled:
            print("❌ Campo email non trovato — controlla il selettore")
            await page.screenshot(path=str(SCREENSHOT_PATH))
            await browser.close()
            return

        # Fill password
        password_filled = False
        for sel in password_selectors:
            try:
                await page.fill(sel, PASSWORD, timeout=3000)
                print(f"✅ Password inserita ({sel})")
                password_filled = True
                break
            except Exception:
                continue

        if not password_filled:
            print("❌ Campo password non trovato")
            await page.screenshot(path=str(SCREENSHOT_PATH))
            await browser.close()
            return

        # Submit
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
            'button:has-text("Accedi")',
        ]
        submitted = False
        for sel in submit_selectors:
            try:
                await page.click(sel, timeout=3000)
                print(f"✅ Submit cliccato ({sel})")
                submitted = True
                break
            except Exception:
                continue

        if not submitted:
            print("❌ Bottone submit non trovato — provo ENTER")
            await page.keyboard.press("Enter")

        print("Attendo redirect post-login...")
        await page.wait_for_timeout(4000)

        final_url = page.url
        print(f"URL finale: {final_url}")
        await page.screenshot(path=str(SCREENSHOT_PATH))
        print(f"Screenshot finale: {SCREENSHOT_PATH}")

        if "login" in final_url.lower():
            print("⚠️  Sembra ancora sulla pagina di login — credenziali errate o form diverso")
        else:
            print("✅ Login apparentemente riuscito!")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
