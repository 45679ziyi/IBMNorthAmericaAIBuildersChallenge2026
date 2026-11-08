"""UI check: screenshots, horizontal-overflow check and axe (WCAG A/AA) audit.

Usage (backend on :8000 seeded, Vite dev server on :5173):
    pip install playwright && playwright install chromium
    npm install            # installs axe-core (dev dependency)
    python scripts/ui_check.py --label after

Writes PNGs and report.json to docs/screenshots/<label>/.
Exit code is 1 when the label does not end with "before" and an overflow or a
serious/critical axe violation is found (labels like "before" or "m0-before" are baselines
and never fail). The script never modifies app data.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
AXE = ROOT / "node_modules" / "axe-core" / "axe.min.js"
ROUTES = [
    "/", "/planner", "/tasks",
    "/campus?tab=events", "/campus?tab=announcements", "/campus?tab=operations",
    "/assistant", "/privacy",
]
VIEWPORTS = [(390, 844), (768, 1024), (1440, 900)]
THEMES = ["light", "dark"]


def reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=3)
        return True
    except Exception:
        return False


def slug(route: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", route.lower()).strip("-")
    return s or "today"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="after")
    ap.add_argument("--base", default="http://127.0.0.1:5173")
    ap.add_argument("--api", default="http://127.0.0.1:8000/api/v1/health")
    ap.add_argument("--no-images", action="store_true")
    args = ap.parse_args()

    if not reachable(args.base):
        print(f"Frontend not reachable at {args.base}. Start it with `npm run dev`.")
        return 2
    if not reachable(args.api):
        print(f"Backend not reachable at {args.api}. Start it and seed demo data first.")
        return 2
    if not AXE.exists():
        print("axe-core missing. Run `npm install` in frontend/.")
        return 2

    out = ROOT.parent / "docs" / "screenshots" / args.label
    out.mkdir(parents=True, exist_ok=True)
    axe_src = AXE.read_text(encoding="utf-8")
    rows, bad = [], 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in THEMES:
            for (w, h) in VIEWPORTS:
                ctx = browser.new_context(
                    viewport={"width": w, "height": h}, color_scheme=theme, reduced_motion="reduce"
                )
                ctx.add_init_script(
                    f"try{{localStorage.setItem('aurora-theme','{theme}')}}catch(e){{}}"
                )
                page = ctx.new_page()
                for route in ROUTES:
                    page.goto(args.base + route, wait_until="networkidle")
                    page.wait_for_timeout(700)
                    if not args.no_images:
                        page.screenshot(path=str(out / f"{slug(route)}-{w}-{theme}.png"), full_page=True)
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth > window.innerWidth + 1"
                    )
                    page.evaluate(axe_src)
                    res = page.evaluate(
                        "axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa']}})"
                        ".then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,n:v.nodes.length})))"
                    )
                    counts: dict[str, int] = {}
                    for v in res:
                        counts[v["impact"]] = counts.get(v["impact"], 0) + 1
                    serious = counts.get("serious", 0) + counts.get("critical", 0)
                    if overflow or serious:
                        bad += 1
                    rows.append({
                        "route": route, "width": w, "theme": theme, "overflow": bool(overflow),
                        "violations": counts, "rules": sorted({v["id"] for v in res}),
                    })
                ctx.close()
        browser.close()

    (out / "report.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"{'route':30} {'w':>5} {'theme':6} overflow  serious+critical  all")
    for r in rows:
        sc = r["violations"].get("serious", 0) + r["violations"].get("critical", 0)
        print(f"{r['route']:30} {r['width']:>5} {r['theme']:6} {str(r['overflow']):8}  {sc:>16}  {sum(r['violations'].values())}")
    print(f"\n{len(rows)} combinations checked, {bad} with overflow or serious/critical violations.")
    return 1 if (bad and not args.label.endswith("before")) else 0


if __name__ == "__main__":
    sys.exit(main())
