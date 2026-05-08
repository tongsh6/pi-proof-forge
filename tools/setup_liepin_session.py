#!/usr/bin/env python3
"""Capture Liepin login session — reads directly from your Chrome cookies.

Usage:
    python3 tools/setup_liepin_session.py [--session-dir <dir>]

How it works:
  1. Open https://www.liepin.com/ in your Chrome (the one you're using
     right now — with saved passwords).
  2. Log in (password autofill works because it's your real Chrome).
  3. Run this script — it reads your Chrome cookie database, decrypts
     Liepin cookies using your Keychain, and saves them for automation.

No Chrome restart. No tab loss. No CDP. Just reads the cookie file.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import gettempdir

COOKIE_DB = Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
LIEPIN_DOMAINS = ("liepin.com", ".liepin.com", "lpt.liepin.com", "www.liepin.com")


def _get_decryption_key() -> bytes | None:
    """Retrieve the Chrome Safe Storage key from macOS Keychain."""
    result = subprocess.run(
        [
            "security", "find-generic-password",
            "-w",
            "-s", "Chrome Safe Storage",
            "-a", "Chrome",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print("[ERROR] Could not get decryption key from Keychain.")
        print("        macOS may have blocked access. Try running:")
        print("        security find-generic-password -s 'Chrome Safe Storage' -a Chrome -w")
        return None
    key_hex = result.stdout.strip()
    try:
        return bytes.fromhex(key_hex)
    except ValueError:
        print(f"[ERROR] Invalid key format: {key_hex[:20]}...")
        return None


def _decrypt_cookie(encrypted_value: bytes, key: bytes) -> str | None:
    """Decrypt a Chrome-encrypted cookie value."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if len(encrypted_value) < 16:
        return None
    try:
        # Chrome v10+ cookie format: b'v10' or b'v11' prefix + 12-byte nonce + ciphertext
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception:
        return None


def _read_liepin_cookies(key: bytes) -> list[dict]:
    """Copy Chrome's cookie DB, read and decrypt Liepin cookies."""
    # Chrome locks the DB while running — copy to a temp file
    tmp = Path(gettempdir()) / f"ppf_chrome_cookies_{Path(COOKIE_DB).stat().st_mtime}.sqlite"
    shutil.copy2(COOKIE_DB, tmp)

    conn = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT host_key, name, encrypted_value, path, is_secure, is_httponly, expires_utc "
        "FROM cookies WHERE host_key LIKE '%liepin%'"
    ).fetchall()
    conn.close()
    tmp.unlink()

    cookies: list[dict] = []
    for row in rows:
        value = _decrypt_cookie(bytes(row["encrypted_value"]), key)
        if value is None:
            continue
        cookies.append({
            "domain": row["host_key"].lstrip("."),
            "name": row["name"],
            "value": value,
            "path": row["path"] or "/",
            "secure": bool(row["is_secure"]),
            "httpOnly": bool(row["is_httponly"]),
        })
    return cookies


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture Liepin cookies from your existing Chrome session"
    )
    _ = parser.add_argument(
        "--session-dir",
        default="outputs/sessions",
        help="Directory to store session cookies (default: outputs/sessions)",
    )
    args = parser.parse_args()

    if not COOKIE_DB.exists():
        print("[ERROR] Chrome cookie database not found.")
        print(f"        Expected at: {COOKIE_DB}")
        return 1

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    except ImportError:
        print("[ERROR] cryptography package not installed.")
        print("        Run: pip install cryptography")
        return 3

    session_root = Path(args.session_dir) / "liepin"
    session_root.mkdir(parents=True, exist_ok=True)
    cookie_file = session_root / "cookies.json"

    # Check if user is logged into Liepin in Chrome
    print("Reading Chrome cookies for Liepin ...")
    print()

    key = _get_decryption_key()
    if key is None:
        return 4

    cookies = _read_liepin_cookies(key)
    if not cookies:
        print("[ERROR] No Liepin cookies found in Chrome.")
        print("        Please open liepin.com in Chrome and log in first.")
        print("        Then re-run this script.")
        return 5

    print(f"Found {len(cookies)} Liepin cookies:")
    for c in cookies:
        value_preview = c["value"][:30] + "..." if len(c["value"]) > 30 else c["value"]
        print(f"  {c['domain']:<25s} {c['name']:<25s} = {value_preview}")

    # Save
    cookie_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved to {cookie_file}")

    # Verify by injecting into automation profile and checking
    print("Testing with automation profile ...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(session_root),
                headless=True,
            )
            ctx.add_cookies(cookies)
            page = ctx.new_page()
            page.goto("https://www.liepin.com/", wait_until="domcontentloaded", timeout=15000)
            url = page.url.lower()
            if "passport" in url or "login" in url:
                print("  ⚠️  Login page detected — session may be expired.")
            else:
                print("  ✅ Session active!")
            ctx.close()
    except ImportError:
        print("  (playwright not available, skipping verification)")
    except Exception as exc:
        print(f"  [WARN] Verification skipped: {exc}")

    print()
    print("Ready. Enable real submission:")
    print(f"  export PPF_SESSION_DIR={Path(args.session_dir).resolve()}")
    print("  export PPF_SUBMIT_ENABLED=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
