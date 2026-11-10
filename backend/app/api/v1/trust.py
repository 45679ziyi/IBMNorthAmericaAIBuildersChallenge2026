"""Trust & Quality API — U6-6.

GET /trust/quality → quality metrics from eval_report.json (or "not run")
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_REPORT_PATH = Path(__file__).parents[5] / "data" / "eval_report.json"


class TrustQualityResponse(BaseModel):
    authorization: dict
    deadline_extraction: dict
    retrieval: dict
    injection: dict
    tenant_leakage: dict
    determinism: dict
    ai_provider: str
    watsonx_configured: bool


_DEFAULT_RESPONSE: dict = {
    "authorization":       {"cases": 0,  "pass_rate": None,   "status": "not_run"},
    "deadline_extraction": {"cases": 0,  "exact_match": None, "status": "not_run"},
    "retrieval":           {"cases": 0,  "coverage_accuracy": None, "status": "not_run"},
    "injection":           {"cases": 0,  "successful_injections": None, "status": "not_run"},
    "tenant_leakage":      {"probes": 0, "leaks": None,        "status": "not_run"},
    "determinism":         {"tenants": 0,"identical_hashes": None, "status": "not_run"},
    "ai_provider": "mock",
    "watsonx_configured": False,
}


@router.get("/quality")
def get_trust_quality():
    """Return eval suite results. Reads from data/eval_report.json if present."""
    # Try alternate relative paths for the report
    candidates = [
        _REPORT_PATH,
        Path("data/eval_report.json"),
        Path("../data/eval_report.json"),
    ]
    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                data["watsonx_configured"] = bool(
                    os.getenv("WATSONX_API_KEY") and os.getenv("WATSONX_PROJECT_ID")
                )
                data["ai_provider"] = "watsonx" if data["watsonx_configured"] else "mock"
                return data
            except Exception:
                pass

    result = dict(_DEFAULT_RESPONSE)
    result["watsonx_configured"] = bool(
        os.getenv("WATSONX_API_KEY") and os.getenv("WATSONX_PROJECT_ID")
    )
    result["ai_provider"] = "watsonx" if result["watsonx_configured"] else "mock"
    return result
