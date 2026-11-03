"""Campus knowledge retriever — SQLite FTS5 + BM25 keyword search."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.models import KnowledgeChunk, KnowledgeDocument
from app.schemas.schemas import KnowledgeSearchResult


# Common English stop words to exclude from FTS queries
_STOP_WORDS = {
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "of", "and", "or",
    "for", "with", "by", "from", "that", "this", "what", "how", "when", "where",
    "who", "why", "do", "does", "did", "are", "was", "were", "be", "been",
    "have", "has", "had", "will", "would", "could", "should", "not", "no", "as",
}

# Minimum FTS score to count a result as relevant (FTS5 rank is negative)
FTS_SCORE_THRESHOLD = -2.5


def _fts_query(q: str) -> str:
    """Convert a raw query string to a safe FTS5 match expression, excluding stop words."""
    safe = q.replace('"', "").replace("'", "").strip()
    if not safe:
        return '""'
    tokens = [t for t in safe.lower().split() if t not in _STOP_WORDS and len(t) > 2]
    if not tokens:
        tokens = safe.split()  # fall back to all tokens if everything was filtered
    return " OR ".join(f'"{t}"' for t in tokens)


def search_knowledge(db: Session, query: str, limit: int = 5) -> list[KnowledgeSearchResult]:
    """Search knowledge chunks using FTS5 virtual table, fall back to LIKE."""
    results: list[KnowledgeSearchResult] = []

    try:
        fts_q = _fts_query(query)
        rows = db.execute(
            text(
                """
                SELECT kc.id, kc.document_id, kc.text,
                       kd.title, kd.publisher, kd.canonical_url, kd.last_verified_at_utc,
                       kf.rank
                FROM knowledge_chunks_fts kf
                JOIN knowledge_chunks kc ON kf.chunk_id = kc.id
                JOIN knowledge_documents kd ON kc.document_id = kd.id
                WHERE kd.is_active = 1
                  AND knowledge_chunks_fts MATCH :q
                ORDER BY rank
                LIMIT :lim
                """
            ),
            {"q": fts_q, "lim": limit},
        ).fetchall()

        for row in rows:
            score = float(row[7]) if row[7] is not None else 0.0
            # Filter out very weak matches (FTS5 rank is negative; less negative = weaker)
            if score < FTS_SCORE_THRESHOLD:
                continue
            results.append(
                KnowledgeSearchResult(
                    chunk_id=row[0],
                    document_id=row[1],
                    text=row[2],
                    title=row[3],
                    publisher=row[4],
                    canonical_url=row[5],
                    last_verified_at_utc=row[6] if isinstance(row[6], datetime) else datetime.fromisoformat(str(row[6])),
                    score=score,
                )
            )
        return results

    except Exception:
        # FTS fallback — simple LIKE search
        q_like = f"%{query.lower()}%"
        chunks = (
            db.query(KnowledgeChunk)
            .join(KnowledgeDocument)
            .filter(
                KnowledgeDocument.is_active == True,
                KnowledgeChunk.search_text.like(q_like),
            )
            .limit(limit)
            .all()
        )
        for chunk in chunks:
            doc = chunk.document
            results.append(
                KnowledgeSearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    title=doc.title,
                    publisher=doc.publisher,
                    canonical_url=doc.canonical_url,
                    last_verified_at_utc=doc.last_verified_at_utc,
                    score=0.0,
                )
            )
        return results
