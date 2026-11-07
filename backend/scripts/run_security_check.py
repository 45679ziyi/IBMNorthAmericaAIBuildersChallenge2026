"""Run the AURORA security watchdog check on demand.

Usage (from backend/ directory with venv active):
    python -m scripts.run_security_check

Intended to be called from cron on the machine that hosts AURORA.
This script does NOT make any network calls — all checks are local.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.security.report import run_report, clear_cache


def main() -> None:
    print("AURORA Security Watchdog — running checks...")
    clear_cache()
    report = run_report()
    summary = report["summary"]
    print(
        f"  Critical: {summary['critical']}  "
        f"Warn: {summary['warn']}  "
        f"Info: {summary['info']}"
    )
    print(f"  Total findings: {len(report['findings'])}")
    print(f"  Last run: {report['last_run_at_utc']}")
    print(f"\nNote: {report['schedule_note']}")

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
