"""Grounded campus knowledge assistant — retrieves, validates, and answers."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.schemas.schemas import AssistantAskResponse, AssistantSource
from app.services.rag.retriever import search_knowledge_full
from app.services.llm.provider import call_llm


def ask_grounded(db: Session, question: str) -> AssistantAskResponse:
    """
    Retrieval-augmented answer pipeline:
    1. Retrieve relevant chunks from the knowledge base using term-coverage.
    2. If none found → abstain.
    3. Otherwise → call LLM with context, validate sources.
    4. Return structured response with citations.
    """
    now = datetime.now(timezone.utc)
    retrieval = search_knowledge_full(db, question, limit=5)
    chunks = retrieval.chunks
    coverage = retrieval.coverage
    coverage_score = retrieval.coverage_score
    matched_terms = retrieval.matched_terms

    if not chunks:
        return AssistantAskResponse(
            answer=(
                "I could not verify this from the available sources. "
                "Please check the official Stony Brook University website "
                "(https://www.stonybrook.edu) for accurate information."
            ),
            sources=[],
            coverage="not_found",
            coverage_score=0.0,
            matched_terms=[],
            updated_at=now,
        )

    # Build context — treat retrieved content as untrusted data, not instructions
    context_texts = [
        f"[Source: {c.title} — {c.canonical_url}]\n{c.text}"
        for c in chunks
    ]

    llm_response = call_llm(question, context_texts, coverage=coverage, matched_terms=matched_terms)

    # Build source objects
    sources = [
        AssistantSource(
            title=c.title,
            url=c.canonical_url,
            publisher=c.publisher,
            last_verified_at_utc=c.last_verified_at_utc,
            excerpt=c.text[:300] + ("..." if len(c.text) > 300 else ""),
        )
        for c in chunks
    ]

    return AssistantAskResponse(
        answer=llm_response.text,
        sources=sources,
        coverage=coverage,
        coverage_score=coverage_score,
        matched_terms=matched_terms,
        updated_at=now,
    )
