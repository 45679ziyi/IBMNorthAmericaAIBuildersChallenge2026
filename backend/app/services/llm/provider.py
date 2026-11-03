"""LLM provider abstraction — mock (deterministic) and watsonx adapters."""
from __future__ import annotations

from app.core.config import settings


class LLMResponse:
    def __init__(self, text: str, provider: str):
        self.text = text
        self.provider = provider


def _mock_answer(question: str, context_chunks: list[str]) -> str:
    """Deterministic rule-based answer for demo without any external call."""
    q_lower = question.lower()
    if not context_chunks:
        return (
            "I could not verify this from the available sources. "
            "Please check the official Stony Brook University website for accurate information."
        )
    # Return a summary of retrieved context
    combined = " ".join(context_chunks[:2])
    if len(combined) > 600:
        combined = combined[:600] + "..."
    return (
        f"Based on the available campus knowledge sources: {combined} "
        "(Please verify with the official source linked below.)"
    )


def call_llm(question: str, context_chunks: list[str]) -> LLMResponse:
    """Route to the configured LLM provider."""
    provider = settings.ai_provider.lower()

    if provider == "mock" or not provider:
        return LLMResponse(
            text=_mock_answer(question, context_chunks),
            provider="mock",
        )

    if provider == "watsonx":
        return _watsonx_call(question, context_chunks)

    # Unknown provider → fall back to mock
    return LLMResponse(
        text=_mock_answer(question, context_chunks),
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
