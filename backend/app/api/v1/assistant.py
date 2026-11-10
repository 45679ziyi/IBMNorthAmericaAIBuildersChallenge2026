"""Campus knowledge assistant endpoints — U6-4: role-aware Ask."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.tenancy import ActorContext, resolve_actor
from app.db.session import get_db
from app.schemas.schemas import AssistantAskRequest, AssistantAskResponse, AssistantSource, KnowledgeSearchResult
from app.services.authz import authorize
from app.services.rag.retriever import search_knowledge
from app.services.rag.assistant import ask_grounded

router = APIRouter()

# Valid ask modes and their required authz actions
_ASK_MODES = {
    "personal":     "ask:personal",
    "course":       "ask:course",
    "campus":       "ask:campus",
    "operations":   "ask:operations",
    "service_desk": "ask:service_desk",
}


@router.get("/knowledge/search", response_model=list[KnowledgeSearchResult])
def knowledge_search(
    q: str = Query(..., min_length=2, max_length=500),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    return search_knowledge(db, q, limit=limit)


@router.post("/assistant/ask", response_model=AssistantAskResponse)
def assistant_ask(
    payload: AssistantAskRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    now = get_now()

    # U6-4: authorize BEFORE retrieve
    mode = getattr(payload, "mode", "campus") or "campus"
    if mode not in _ASK_MODES:
        mode = "campus"
    action = _ASK_MODES[mode]
    d = authorize(actor, action)
    if not d:
        raise HTTPException(
            status_code=403,
            detail={"reason_code": d.reason_code, "message": d.reason},
        )

    # ── Personal-context answerer (M5): try personal intents first ────────────
    if mode in ("personal", "course", "campus"):
        from app.services.campus.ask_personal import answer_personal
        personal = answer_personal(db, payload.question, now)

        if personal is not None:
            coverage_score = (
                1.0 if personal.coverage == "supported"
                else 0.5 if personal.coverage == "partial"
                else 0.0
            )
            sources = [
                AssistantSource(
                    title=src.get("text", src.get("feed", "Campus data")),
                    url="#",
                    publisher=src.get("feed", "aurora"),
                    last_verified_at_utc=now,
                    excerpt=personal.answer[:300],
                )
                for src in personal.sources
            ]
            return AssistantAskResponse(
                answer=personal.answer,
                sources=sources,
                coverage=personal.coverage,  # type: ignore[arg-type]
                coverage_score=coverage_score,
                matched_terms=[personal.intent],
                updated_at=now,
                disclaimer="Answer built from your campus data for today. Not from real SBU systems.",
            )

    # ── Fall back to public knowledge retriever ───────────────────────────────
    return ask_grounded(db, payload.question)
