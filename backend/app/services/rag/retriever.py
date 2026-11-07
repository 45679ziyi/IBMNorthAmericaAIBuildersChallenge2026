"""Campus knowledge retriever — term-coverage approach with FTS5 + LIKE fallback."""
from __future__ import annotations

import re
from datetime import datetime
from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.models import KnowledgeChunk, KnowledgeDocument
from app.schemas.schemas import KnowledgeSearchResult

# ─── Constants ────────────────────────────────────────────────────────────────

PARTIAL_MIN = 0.30
SUPPORTED_MIN = 0.60

STOP_WORDS = {
    "the", "and", "for", "are", "was", "were", "has", "have", "had", "not",
    "but", "can", "my", "me", "you", "your", "i", "there", "about", "tell",
    "give", "please", "get", "need", "this", "that", "with", "from", "what",
    "how", "who", "when", "where", "why", "which", "will", "does", "did",
    "its", "all", "any", "each", "into", "than", "then", "they", "them",
    "their", "these", "those", "been", "being", "also", "more", "most",
    "some", "such", "just",
}

DOMAIN_WORDS = {
    "university", "stony", "brook", "stonybrook", "sbu", "campus",
    "student", "students",
}


# ─── Term extraction ──────────────────────────────────────────────────────────

def extract_terms(query: str) -> list[str]:
    """Return significant terms from query (lowercase tokens > 2 chars, not stop/domain words)."""
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    result = []
    seen: set[str] = set()
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        # Keep numeric tokens regardless of length; alpha tokens must be > 2 chars
        if t.isdigit() or (len(t) > 2 and t not in STOP_WORDS and t not in DOMAIN_WORDS):
            result.append(t)
    return result


# ─── FTS5 search ─────────────────────────────────────────────────────────────

class _ChunkHit(NamedTuple):
    chunk_id: str
    rank: float


def _fts_hits_for_term(db: Session, term: str) -> set[str]:
    """Return chunk_ids that match a single term via FTS5."""
    try:
        rows = db.execute(
            text(
                """
                SELECT kf.chunk_id, kf.rank
                FROM knowledge_chunks_fts kf
                JOIN knowledge_chunks kc ON kf.chunk_id = kc.id
                JOIN knowledge_documents kd ON kc.document_id = kd.id
                WHERE kd.is_active = 1
                  AND knowledge_chunks_fts MATCH :q
                """
            ),
            {"q": f'"{term}"'},
        ).fetchall()
        return {row[0] for row in rows}
    except Exception:
        return set()


def _like_hits_for_term(db: Session, term: str) -> set[str]:
    """Return chunk_ids that contain a whole-word term via LIKE patterns (fallback)."""
    try:
        rows = db.execute(
            text(
                """
                SELECT kc.id
                FROM knowledge_chunks kc
                JOIN knowledge_documents kd ON kc.document_id = kd.id
                WHERE kd.is_active = 1
                  AND (
                    kc.search_text LIKE :pat_mid
                    OR kc.search_text LIKE :pat_start
                    OR kc.search_text LIKE :pat_end
                    OR kc.search_text = :exact
                  )
                """
            ),
            {
                "pat_mid": f"% {term} %",
                "pat_start": f"{term} %",
                "pat_end": f"% {term}",
                "exact": term,
            },
        ).fetchall()
        return {row[0] for row in rows}
    except Exception:
        return set()


def _fts_rank_for_chunk(db: Session, chunk_id: str, terms: list[str]) -> float:
    """Get FTS rank for a chunk against a multi-term OR query."""
    if not terms:
        return 0.0
    fts_q = " OR ".join(f'"{t}"' for t in terms)
    try:
        row = db.execute(
            text(
                """
                SELECT kf.rank
                FROM knowledge_chunks_fts kf
                WHERE kf.chunk_id = :cid
                  AND knowledge_chunks_fts MATCH :q
                LIMIT 1
                """
            ),
            {"cid": chunk_id, "q": fts_q},
        ).fetchone()
        return float(row[0]) if row else 0.0
    except Exception:
        return 0.0


def _get_chunk_result(db: Session, chunk_id: str, coverage_score: float) -> KnowledgeSearchResult | None:
    """Fetch chunk + document metadata and return a KnowledgeSearchResult."""
    row = db.execute(
        text(
            """
            SELECT kc.id, kc.document_id, kc.text,
                   kd.title, kd.publisher, kd.canonical_url, kd.last_verified_at_utc
            FROM knowledge_chunks kc
            JOIN knowledge_documents kd ON kc.document_id = kd.id
            WHERE kc.id = :cid
            """
        ),
        {"cid": chunk_id},
    ).fetchone()
    if not row:
        return None
    lv = row[6]
    if not isinstance(lv, datetime):
        lv = datetime.fromisoformat(str(lv))
    return KnowledgeSearchResult(
        chunk_id=row[0],
        document_id=row[1],
        text=row[2],
        title=row[3],
        publisher=row[4],
        canonical_url=row[5],
        last_verified_at_utc=lv,
        score=coverage_score,
    )


# ─── Public API ───────────────────────────────────────────────────────────────

class RetrievalResult(NamedTuple):
    chunks: list[KnowledgeSearchResult]
    coverage: str           # "supported" | "partial" | "not_found"
    coverage_score: float
    matched_terms: list[str]


def search_knowledge(
    db: Session,
    query: str,
    limit: int = 5,
) -> list[KnowledgeSearchResult]:
    """Thin wrapper — returns only chunks (backward-compatible)."""
    result = search_knowledge_full(db, query, limit)
    return result.chunks


def search_knowledge_full(
    db: Session,
    query: str,
    limit: int = 5,
) -> RetrievalResult:
    """Term-coverage retrieval. Returns chunks + coverage label."""
    terms = extract_terms(query)
    if not terms:
        return RetrievalResult([], "not_found", 0.0, [])

    # --- FTS5 per-term hits ---
    term_to_chunks: dict[str, set[str]] = {}
    use_like = False

    for term in terms:
        hits = _fts_hits_for_term(db, term)
        term_to_chunks[term] = hits

    # If all terms returned empty hits, try LIKE fallback
    if all(len(v) == 0 for v in term_to_chunks.values()):
        use_like = True
        for term in terms:
            term_to_chunks[term] = _like_hits_for_term(db, term)

    # Gather all chunk ids across all terms
    all_chunk_ids: set[str] = set()
    for hits in term_to_chunks.values():
        all_chunk_ids |= hits

    if not all_chunk_ids:
        return RetrievalResult([], "not_found", 0.0, [])

    # Coverage per chunk
    total_terms = len(terms)
    chunk_coverage: dict[str, float] = {}
    for cid in all_chunk_ids:
        matched = sum(1 for t in terms if cid in term_to_chunks[t])
        chunk_coverage[cid] = matched / total_terms

    # Filter: only chunks with coverage >= PARTIAL_MIN
    candidates = [
        (cid, cov)
        for cid, cov in chunk_coverage.items()
        if cov >= PARTIAL_MIN
    ]

    if not candidates:
        return RetrievalResult([], "not_found", 0.0, [])

    # Sort: coverage desc, then rank asc (more negative = better in FTS5)
    if not use_like:
        ranks: dict[str, float] = {}
        for cid, _ in candidates:
            ranks[cid] = _fts_rank_for_chunk(db, cid, terms)
        candidates.sort(key=lambda x: (-x[1], ranks.get(x[0], 0.0)))
    else:
        candidates.sort(key=lambda x: -x[1])

    # Take top `limit`
    top = candidates[:limit]

    best_coverage = top[0][1] if top else 0.0

    # Determine matched_terms (those that matched at least one chunk in top)
    top_ids = {cid for cid, _ in top}
    matched_terms = [t for t in terms if term_to_chunks[t] & top_ids]

    # Build results
    results: list[KnowledgeSearchResult] = []
    for cid, cov in top:
        r = _get_chunk_result(db, cid, cov)
        if r:
            results.append(r)

    # Coverage label
    if best_coverage >= SUPPORTED_MIN:
        coverage = "supported"
    else:
        coverage = "partial"

    return RetrievalResult(results, coverage, best_coverage, matched_terms)
