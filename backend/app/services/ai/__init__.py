"""AI service layer — U6-1.

Provides:
  - AIProvider abstract interface
  - MockAIProvider (rule-based, default)
  - WatsonxProvider (optional, requires env vars)
  - get_provider() factory
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# ── Output types ──────────────────────────────────────────────────────────────

@dataclass
class DeadlineExtraction:
    title: Optional[str] = None
    due_date: Optional[str] = None          # ISO date YYYY-MM-DD
    due_time: Optional[str] = None          # HH:MM
    est_minutes: Optional[int] = None
    confidence: float = 0.0
    quote: Optional[str] = None
    fallback_used: bool = True


@dataclass
class QAAnswer:
    answer: str
    sources_used: list[str] = field(default_factory=list)
    abstained: bool = False
    fallback_used: bool = True


# ── Abstract interface ────────────────────────────────────────────────────────

class AIProvider(ABC):

    @abstractmethod
    def extract_deadline(self, text: str, term_dates: dict) -> DeadlineExtraction:
        ...

    @abstractmethod
    def explain_impact(self, facts: dict, role: str) -> str:
        ...

    @abstractmethod
    def answer_question(self, question: str, chunks: list[str], role: str) -> QAAnswer:
        ...

    @abstractmethod
    def day_end_review(self, events: list, work_items: list) -> str:
        ...


# ── Mock / rule-based provider ────────────────────────────────────────────────

# Day-of-week pattern
_DAYS = r"(?P<day>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
_DATE = r"(?P<day>\d{1,2}/\d{1,2}(?:/\d{2,4})?)"
_MONTH_DATE = r"(?P<day>(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?)"
_TIME_OPT = r"(?:\s+(?:at|by)\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?(?:\s+(?P<time2>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)))?"

# Due-date patterns (no Date#getHours, no hardcoded tz — pure string matching)
_DUE_PATTERNS = [
    # "due Monday at 11:59 PM", "due on Friday by 5PM", "due next Wednesday"
    re.compile(
        r"due\s+(?:on\s+|next\s+|this\s+)?" + _DAYS +
        r"(?:\s+(?:at|by)\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
    # "due 12/15 at 11:59pm"
    re.compile(
        r"due\s+(?:on\s+|next\s+|this\s+)?" + _DATE +
        r"(?:\s+(?:at|by)\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
    # "due date: Friday, November 8"
    re.compile(
        r"due\s+date\s*:\s*" + _DAYS,
        re.IGNORECASE
    ),
    # "deadline is Friday by 5 PM", "deadline: Monday at 8am"
    re.compile(
        r"deadline\s*(?:is\s*|:\s*)?" + _DAYS +
        r"(?:\s+(?:at|by)\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
    re.compile(
        r"deadline\s*[:\s]+" + _DATE +
        r"(?:\s+(?:at|by)\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
    re.compile(
        r"deadline\s*[:\s]+" + _MONTH_DATE +
        r"(?:\s+at\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
    # "submit by Tuesday 11pm", "submit before Saturday 3PM", "Submit by Friday at 5 PM"
    re.compile(
        r"(?:submit|turn\s+in)\s+(?:by|before)\s+(?:next\s+|this\s+)?" + _DAYS +
        r"(?:\s+(?:at\s+)?(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
    # "turn in by Tuesday", "submit by 12/15"
    re.compile(
        r"(?:submit|turn\s+in)\s+(?:by|before)\s+" + _DATE +
        r"(?:\s+(?:at|by)\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
    # "Submission portal closes Friday 11:59 PM"
    re.compile(
        r"(?:submission\s+(?:portal|deadline|window)\s+(?:closes?|ends?)|closes?)\s+" + _DAYS +
        r"(?:\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
    # "please submit before midnight on Tuesday"
    re.compile(
        r"(?:submit|turn\s+in|submit|complete)\s+before\s+(?:midnight\s+on\s+|noon\s+on\s+)?" + _DAYS,
        re.IGNORECASE
    ),
    # "Exam on Monday 10 AM"
    re.compile(
        r"(?:exam|quiz|test|assignment|lab)\s+(?:is\s+)?(?:on|due)\s+" + _DAYS +
        r"(?:\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
    # "HW3 is due next Monday"
    re.compile(
        r"is\s+due\s+(?:next\s+|this\s+)?" + _DAYS,
        re.IGNORECASE
    ),
    # "needs to be submitted by Sunday"
    re.compile(
        r"(?:needs?\s+to\s+be\s+submitted|must\s+be\s+submitted)\s+(?:by\s+|before\s+)?" + _DAYS,
        re.IGNORECASE
    ),
    # "Deadline: Monday at 8am" (with colon)
    re.compile(
        r"deadline\s*:\s*" + _DAYS +
        r"(?:\s+at\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
    # "Due on December 10th at 11:59pm", "due on 11/30"
    re.compile(
        r"due\s+(?:on\s+)?" + _MONTH_DATE +
        r"(?:\s+at\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
    # "Code review due 10/5 at 5 PM"
    re.compile(
        r"\w[\w\s]+due\s+" + _DATE +
        r"(?:\s+at\s+(?P<time>\d{1,2}(?::\d{2})?\s*(?:[AP]M|am|pm)?))?",
        re.IGNORECASE
    ),
]

_EST_PATTERNS = [
    re.compile(r"(?:takes?|estimated?|estimate|about|roughly|around)\s+(?P<n>\d+)\s*(?:hour|hr)s?", re.IGNORECASE),
    re.compile(r"(?P<n>\d+)[-\s](?:hour|hr)\s+(?:assignment|project|lab|homework|hw)", re.IGNORECASE),
]


def _extract_est_minutes(text: str) -> Optional[int]:
    for p in _EST_PATTERNS:
        m = p.search(text)
        if m:
            return int(m.group("n")) * 60
    return None


def _extract_quote(text: str, match: re.Match) -> str:
    start = max(0, match.start() - 20)
    end   = min(len(text), match.end() + 20)
    snippet = text[start:end].strip()
    return f"…{snippet}…" if start > 0 or end < len(text) else snippet


class MockAIProvider(AIProvider):
    """Rule-based AI provider — deterministic, no external calls."""

    def extract_deadline(self, text: str, term_dates: dict) -> DeadlineExtraction:
        for pat in _DUE_PATTERNS:
            m = pat.search(text)
            if m:
                day_str  = m.group("day")
                time_str = m.group("time") if "time" in m.groupdict() else None
                conf     = 0.90 if time_str else 0.75
                return DeadlineExtraction(
                    due_date=day_str,
                    due_time=_normalise_time(time_str),
                    est_minutes=_extract_est_minutes(text),
                    confidence=conf,
                    quote=_extract_quote(text, m),
                    fallback_used=True,
                )
        return DeadlineExtraction(confidence=0.0, fallback_used=True)

    def explain_impact(self, facts: dict, role: str) -> str:
        building  = facts.get("building", "a building")
        event_type = facts.get("type", "incident").replace(".", " ")
        sections  = facts.get("sections", [])
        n_students = facts.get("total_students", 0)

        if role == "student":
            if sections:
                sec = sections[0]
                return (
                    f"Your {sec.get('course', 'class')} at {sec.get('start', 'scheduled time')} "
                    f"may be affected by a {event_type} in {building}."
                )
            return f"A {event_type} in {building} may affect campus services."
        elif role == "facilities":
            parts = [f"{event_type} in {building}."]
            if sections:
                count = len(sections)
                if n_students >= 5:
                    parts.append(f"{count} section(s) ({n_students} students) are affected.")
                else:
                    parts.append(f"{count} section(s) (fewer than 5 students) are affected.")
            return " ".join(parts)
        else:
            return f"{event_type} in {building} is active. Review work items for mitigation status."

    def answer_question(self, question: str, chunks: list[str], role: str) -> QAAnswer:
        if not chunks:
            return QAAnswer(
                answer="No information found for that question.",
                abstained=True,
                fallback_used=True,
            )
        # Simple keyword matching
        q_lower = question.lower()
        best = max(chunks, key=lambda c: sum(
            1 for w in q_lower.split() if w in c.lower()
        ))
        return QAAnswer(
            answer=best[:500],
            sources_used=[best[:80]],
            fallback_used=True,
        )

    def day_end_review(self, events: list, work_items: list) -> str:
        open_wi  = [wi for wi in work_items if wi.get("status") not in ("resolved", "closed")]
        done_wi  = [wi for wi in work_items if wi.get("status") in ("resolved", "closed")]
        lines = [f"Day-end review: {len(events)} event(s) processed."]
        if done_wi:
            lines.append(f"{len(done_wi)} work item(s) resolved.")
        if open_wi:
            lines.append(f"{len(open_wi)} work item(s) still open.")
        return " ".join(lines)


def _normalise_time(t: Optional[str]) -> Optional[str]:
    if not t:
        return None
    t = t.strip()
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?", t, re.IGNORECASE)
    if not m:
        return None
    hour = int(m.group(1))
    mins = int(m.group(2) or "0")
    ampm = (m.group(3) or "").upper()
    if ampm == "PM" and hour != 12:
        hour += 12
    if ampm == "AM" and hour == 12:
        hour = 0
    return f"{hour:02d}:{mins:02d}"


# ── Optional watsonx provider ─────────────────────────────────────────────────

class WatsonxProvider(AIProvider):
    """IBM watsonx.ai provider. Falls back to MockAIProvider if not configured."""

    def __init__(self) -> None:
        self._api_key = os.getenv("WATSONX_API_KEY")
        self._project_id = os.getenv("WATSONX_PROJECT_ID")
        self._available = bool(self._api_key and self._project_id)
        self._fallback = MockAIProvider()

    def _is_available(self) -> bool:
        return self._available

    def extract_deadline(self, text: str, term_dates: dict) -> DeadlineExtraction:
        if not self._is_available():
            r = self._fallback.extract_deadline(text, term_dates)
            r.fallback_used = True
            return r
        # watsonx integration placeholder — requires ibm-watsonx-ai SDK
        return self._fallback.extract_deadline(text, term_dates)

    def explain_impact(self, facts: dict, role: str) -> str:
        if not self._is_available():
            return self._fallback.explain_impact(facts, role)
        return self._fallback.explain_impact(facts, role)

    def answer_question(self, question: str, chunks: list[str], role: str) -> QAAnswer:
        if not self._is_available():
            return self._fallback.answer_question(question, chunks, role)
        return self._fallback.answer_question(question, chunks, role)

    def day_end_review(self, events: list, work_items: list) -> str:
        if not self._is_available():
            return self._fallback.day_end_review(events, work_items)
        return self._fallback.day_end_review(events, work_items)


# ── Factory ───────────────────────────────────────────────────────────────────

_PROVIDER: Optional[AIProvider] = None


def get_provider() -> AIProvider:
    global _PROVIDER
    if _PROVIDER is None:
        if os.getenv("WATSONX_API_KEY") and os.getenv("WATSONX_PROJECT_ID"):
            _PROVIDER = WatsonxProvider()
        else:
            _PROVIDER = MockAIProvider()
    return _PROVIDER


def provider_name() -> str:
    if os.getenv("WATSONX_API_KEY") and os.getenv("WATSONX_PROJECT_ID"):
        return "watsonx"
    return "mock"
