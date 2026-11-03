"""Campus knowledge assistant endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.schemas import AssistantAskRequest, AssistantAskResponse, KnowledgeSearchResult
from app.services.rag.retriever import search_knowledge
from app.services.rag.assistant import ask_grounded

router = APIRouter()


@router.get("/knowledge/search", response_model=list[KnowledgeSearchResult])
def knowledge_search(
    q: str = Query(..., min_length=2, max_length=500),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    return search_knowledge(db, q, limit=limit)


@router.post("/assistant/ask", response_model=AssistantAskResponse)
def assistant_ask(payload: AssistantAskRequest, db: Session = Depends(get_db)):
    return ask_grounded(db, payload.question)
