"""LLM provider abstraction — mock (deterministic) and watsonx adapters."""
from __future__ import annotations

import re

from app.core.config import settings


class LLMResponse:
    def __init__(self, text: str, provider: str):
        self.text = text
        self.provider = provider


_ABSTENTION = (
    "I could not verify this from the available sources. "
    "Please check the official Stony Brook University website for accurate information."
)

_PARTIAL_PREFIX = "I found related information but couldn't fully verify this. "


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on '. ', '! ', '? '."""
    parts = re.split(r"(?<=[.!?]) +", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _score_sentence(sentence: str, terms: list[str]) -> int:
    """Count how many terms appear in the sentence (lowercased)."""
    sl = sentence.lower()
    return sum(1 for t in terms if t in sl)


def _mock_answer(
    question: str,
    context_chunks: list[str],
    coverage: str = "supported",
    matched_terms: list[str] | None = None,
) -> str:
    """Deterministic extractive answer for demo — no external call."""
    if not context_chunks:
        return _ABSTENTION

    if matched_terms is None:
        matched_terms = []

    # Collect (sentence, chunk_index) pairs
    candidates: list[tuple[str, int]] = []
    for i, chunk in enumerate(context_chunks):
        # Strip leading "[Source: ...]" header line
        body = re.sub(r"^\[Source:[^\]]*\]\s*", "", chunk, count=1)
        sentences = _split_sentences(body)
        for s in sentences:
            candidates.append((s, i))

    if not candidates:
        return _ABSTENTION

    # Score each sentence by term overlap
    scored = [(s, idx, _score_sentence(s, matched_terms)) for s, idx in candidates]
    scored.sort(key=lambda x: -x[2])

    # Pick top 2 from different chunks when possible, never cut mid-sentence
    selected: list[tuple[str, int]] = []
    seen_chunks: set[int] = set()
    for s, idx, _ in scored:
        if idx not in seen_chunks:
            selected.append((s, idx))
            seen_chunks.add(idx)
        elif len(seen_chunks) >= 2:
            # also allow a second sentence from same chunk if we don't have 2 yet
            pass
        if len(selected) == 2:
            break

    # If we still have fewer than 2, fill from any chunk
    if len(selected) < 2:
        for s, idx, _ in scored:
            if (s, idx) not in selected:
                selected.append((s, idx))
            if len(selected) == 2:
                break

    # Sort selected by original chunk order (source order)
    selected.sort(key=lambda x: x[1])

    # Build answer — cap at ~450 chars without cutting mid-sentence
    parts: list[str] = []
    total = 0
    for i, (s, idx) in enumerate(selected):
        citation = f" [{idx + 1}]"
        piece = s + citation
        if total + len(piece) > 450:
            break
        parts.append(piece)
        total += len(piece) + 1  # +1 for space

    if not parts:
        # At least include the highest-scored sentence even if it's long
        s, idx, _ = scored[0]
        parts = [s + f" [{idx + 1}]"]

    answer = " ".join(parts) + " (Please verify with the official source linked below.)"

    if coverage == "partial":
        answer = _PARTIAL_PREFIX + answer

    return answer


def call_llm(
    question: str,
    context_chunks: list[str],
    coverage: str = "supported",
    matched_terms: list[str] | None = None,
) -> LLMResponse:
    """Route to the configured LLM provider."""
    provider = settings.ai_provider.lower()

    if provider == "mock" or not provider:
        return LLMResponse(
            text=_mock_answer(question, context_chunks, coverage=coverage, matched_terms=matched_terms),
            provider="mock",
        )

    if provider == "watsonx":
        return _watsonx_call(question, context_chunks)

    # Unknown provider → fall back to mock
    return LLMResponse(
        text=_mock_answer(question, context_chunks, coverage=coverage, matched_terms=matched_terms),
        provider="mock-fallback",
    )


def _watsonx_call(question: str, context_chunks: list[str]) -> LLMResponse:
    """IBM watsonx.ai inference (opt-in, requires credentials)."""
    try:
        import httpx

        context = "\n\n".join(context_chunks)
        prompt = (
            "You are AURORA, a campus knowledge assistant for Stony Brook University. "
            "Answer strictly from the provided sources. "
            "If the sources do not contain enough information to answer, say: "
            "'I could not verify this from the available sources.'\n\n"
            f"SOURCES:\n{context}\n\nQUESTION: {question}\n\nANSWER:"
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.watsonx_api_key}",
        }
        body = {
            "model_id": settings.watsonx_model_id,
            "input": prompt,
            "parameters": {"max_new_tokens": 512, "temperature": 0.0},
            "project_id": settings.watsonx_project_id,
        }
        resp = httpx.post(
            f"{settings.watsonx_url}/ml/v1/text/generation?version=2023-05-29",
            json=body,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["results"][0]["generated_text"].strip()
        return LLMResponse(text=text, provider="watsonx")
    except Exception as exc:
        return LLMResponse(
            text=(
                "AI provider is temporarily unavailable. "
                "Please see the source links below for official information. "
                f"(Error: {type(exc).__name__})"
            ),
            provider="watsonx-error",
        )
