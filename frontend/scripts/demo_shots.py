"""
Demo shots script. Requires: pip install playwright && playwright install chromium
Usage: python scripts/demo_shots.py  (with backend on :8000 and Vite on :5173)

This script:
1. Starts the scenario 'disrupted_tuesday' via POST /api/v1/sim/start
2. Advances to checkpoints 07:30, 10:10, 12:20, 16:15
3. At each checkpoint, takes full-page screenshots at:
   - widths 1440 and 390
   - themes light and dark
4. Saves screenshots to docs/screenshots/m4/
5. Prints the list of files saved

Note: Playwright is not run in CI. This script is provided for manual demo use only.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

BACKEND_BASE = "http://localhost:8000/api/v1"
FRONTEND_URL = "http://localhost:5173"
OUTPUT_DIR   = Path(__file__).parent.parent.parent / "docs" / "screenshots" / "m4"
SCENARIO_ID  = "disrupted_tuesday"
CHECKPOINTS  = ["07:30", "10:10", "12:20", "16:15"]
WIDTHS       = [1440, 390]
THEMES       = ["light", "dark"]


# ── helpers ──────────────────────────────────────────────────────────────────

def api_post(path: str, payload: dict | None = None) -> dict:
    url = f"{BACKEND_BASE}{path}"
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def advance_to(target_time: str) -> dict:
    """Advance simulation to a specific wall-clock time (HH:MM)."""
    return api_post("/sim/advance", {"to": target_time})


# ── screenshot capture ───────────────────────────────────────────────────────

def take_screenshots(page: "playwright.sync_api.Page", checkpoint: str) -> list[str]:  # type: ignore[name-defined]
    saved: list[str] = []
    for width in WIDTHS:
        for theme in THEMES:
            page.set_viewport_size({"width": width, "height": 900})
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
            page.wait_for_timeout(600)  # let CSS transitions settle

            safe_time = checkpoint.replace(":", "")
            filename = OUTPUT_DIR / f"checkpoint_{safe_time}_w{width}_{theme}.png"
            page.screenshot(path=str(filename), full_page=True)
            saved.append(str(filename))
            print(f"  Saved: {filename}")
    return saved


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    # Try importing Playwright; exit cleanly if not installed
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "ERROR: Playwright is not installed.\n"
            "Install it with:\n"
            "  pip install playwright\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(2)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Start scenario
    print(f"Starting scenario: {SCENARIO_ID}")
    try:
        state = api_post("/sim/start", {"scenario_id": SCENARIO_ID})
        print(f"  Scenario started. Virtual now: {state.get('virtual_now')}")
    except urllib.error.URLError as exc:
        print(f"ERROR: Could not reach backend at {BACKEND_BASE}: {exc}", file=sys.stderr)
        sys.exit(2)

    all_saved: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(FRONTEND_URL, wait_until="networkidle")

        for checkpoint in CHECKPOINTS:
            print(f"\nAdvancing to {checkpoint}…")
            try:
                state = advance_to(checkpoint)
                print(f"  Virtual now: {state.get('virtual_now')}")
            except Exception as exc:  # noqa: BLE001
                print(f"  WARNING: advance failed: {exc}")

            # Reload page to pick up new sim state
            page.goto(FRONTEND_URL, wait_until="networkidle")
            page.wait_for_timeout(1500)  # wait for DemoBar + data fetch

            saved = take_screenshots(page, checkpoint)
            all_saved.extend(saved)

        browser.close()

    print(f"\nDone. {len(all_saved)} screenshots saved to {OUTPUT_DIR}")
    for f in all_saved:
        print(f"  {f}")


if __name__ == "__main__":
    main()
