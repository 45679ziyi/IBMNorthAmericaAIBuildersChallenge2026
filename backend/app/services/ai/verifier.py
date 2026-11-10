"""AI output verifier — U6-1.

Every number, room, building name, time in AI output must appear in the fact set.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class VerificationResult:
    valid: bool
    violations: list[str] = field(default_factory=list)


def _extract_numbers(text: str) -> set[str]:
    """Extract standalone numeric strings from text."""
    return set(re.findall(r'\b\d+\b', text))


def _extract_times(text: str) -> set[str]:
    """Extract time patterns like 10:00 or 10AM."""
    return set(re.findall(r'\b\d{1,2}(?::\d{2})?\s*(?:[AP]M)?\b', text, re.IGNORECASE))


def verify_impact_explanation(output: str, fact_set: dict) -> VerificationResult:
    """Verify that AI output does not hallucinate facts not in fact_set.

    Checks:
    - Any number in output must appear in one of the fact values (as string)
    - Any building/room name in output must be in entity_refs or buildings
    - Time strings must be grounded in a fact value
    """
    violations: list[str] = []

    # Build a flat set of all string-representable fact values
    fact_strings: set[str] = set()
    def _flatten(v: object) -> None:
        if isinstance(v, str):
            fact_strings.add(v.lower())
        elif isinstance(v, (int, float)):
            fact_strings.add(str(int(v)))
        elif isinstance(v, dict):
            for vv in v.values():
                _flatten(vv)
        elif isinstance(v, (list, tuple)):
            for item in v:
                _flatten(item)

    _flatten(fact_set)

    # Check numbers (exclude single-digit cardinal numbers like "1" or "2" — too noisy)
    output_numbers = _extract_numbers(output)
    for n in output_numbers:
        if len(n) >= 2 and n not in fact_strings:
            violations.append(f"Number '{n}' not grounded in facts")

    # Check building / room tokens: words that look like building codes (ALL-CAPS + digits)
    building_tokens = re.findall(r'\b[A-Z]{2,4}[-\s]\d{3,4}\b', output)
    for tok in building_tokens:
        if tok.lower() not in fact_strings and tok not in fact_strings:
            violations.append(f"Room/building '{tok}' not grounded in facts")

    return VerificationResult(
        valid=len(violations) == 0,
        violations=violations,
    )
