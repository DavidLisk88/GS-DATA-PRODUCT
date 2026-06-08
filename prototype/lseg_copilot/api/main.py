"""FastAPI application for the LSEG Data Copilot agent.

Provides endpoints for:
  - POST /api/ask              — single-turn question answering
  - POST /api/conversations/{id}/message — multi-turn conversation
  - GET  /api/conversations/{id}         — get conversation history
  - POST /api/validate-sql     — SQL validation against catalog
  - GET  /api/catalog/search   — schema/table search
  - GET  /api/catalog/domains  — list all domains
  - GET  /api/catalog/tables/{fqn} — single table detail
  - GET  /api/health           — liveness check
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .models import (
    AskRequest,
    AskResponse,
    CatalogSearchResponse,
    ChatMessage,
    Citation,
    ColumnInfo,
    ConversationMessage,
    ConversationResponse,
    DomainInfo,
    DomainsResponse,
    IntentType,
    MessageRole,
    SQLResult,
    TableInfo,
    ValidateSQLRequest,
    ValidateSQLResponse,
)

LOGGER = logging.getLogger(__name__)

# ── Application setup ─────────────────────────────────────────────────────

app = FastAPI(
    title="LSEG Data Copilot",
    description="AI agent for LSEG Quantitative Analytics data — schema discovery, query generation, and knowledge search.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global state (lazily initialised) ─────────────────────────────────────

_catalog = None
_index = None
_conversations: dict[str, list[ChatMessage]] = {}
_conversation_meta: dict[str, dict[str, datetime]] = {}


def _get_catalog():
    global _catalog
    if _catalog is None:
        from ..catalog import Catalog
        _catalog = Catalog.load()
        LOGGER.info(
            "Catalog loaded: %d tables, %d domains, %d symbols",
            len(_catalog.tables),
            len(_catalog.manifest.domains),
            len(_catalog.symbol_index),
        )
    return _catalog


def _get_index():
    global _index
    if _index is None:
        from ..indexer import build_index
        _index = build_index(catalog=_get_catalog(), embed=False)
        LOGGER.info("Index built: %d chunks", len(_index.chunks))
    return _index


# ── Helpers ───────────────────────────────────────────────────────────────

def _classify_intent(question: str) -> IntentType:
    """Lightweight intent classification."""
    lower = question.lower()
    sql_signals = ["select", "query", "join", "where", "sql", "write me", "generate a query"]
    nav_signals = ["navigate", "how to find", "where is the button", "log in"]
    def_signals = ["what is", "what are", "define", "describe", "explain", "meaning"]

    sql_hits = sum(1 for s in sql_signals if s in lower)
    nav_hits = sum(1 for s in nav_signals if s in lower)
    def_hits = sum(1 for s in def_signals if s in lower)

    if sql_hits >= def_hits and sql_hits > nav_hits:
        return IntentType.sql
    if def_hits >= sql_hits and def_hits > nav_hits:
        return IntentType.definitional
    if nav_hits > 0:
        return IntentType.navigation
    return IntentType.ambiguous


def _search_chunks(question: str, *, max_results: int = 10) -> list[dict[str, Any]]:
    """Search the index for relevant chunks."""
    index = _get_index()
    from ..retriever import retrieve
    catalog = _get_catalog()
    results = retrieve(
        query=question,
        index=index,
        catalog=catalog,
        top_k=max_results,
    )
    return [
        {
            "chunk_id": r.chunk.chunk_id,
            "source": r.chunk.source_path,
            "title": r.chunk.title,
            "text": r.chunk.text[:500],
            "score": r.score,
            "symbols": r.chunk.symbols,
        }
        for r in results
    ]


def _resolve_related_tables(question: str) -> list[str]:
    """Find tables whose symbols appear in the question."""
    catalog = _get_catalog()
    words = set(question.lower().split())
    related = set()
    for word in words:
        for fqn in catalog.symbol_index.get(word, []):
            related.add(fqn)
    return sorted(related)[:20]


def _build_answer(question: str, chunks: list[dict[str, Any]], intent: IntentType) -> str:
    """Build an answer from retrieved chunks. In production this would call
    an LLM; for now we compose a structured answer from the top results."""
    if not chunks:
        return (
            "I couldn't find specific information about that in the LSEG knowledge base. "
            "Try rephrasing your question or searching the catalog directly."
        )

    parts = []
    if intent == IntentType.definitional:
        parts.append(f"Based on the LSEG documentation, here's what I found:\n")
    elif intent == IntentType.sql:
        parts.append(f"Here's what I found that can help with your query:\n")
    else:
        parts.append(f"Here are the most relevant results:\n")

    for i, chunk in enumerate(chunks[:5], 1):
        source = chunk.get("title", chunk.get("source", ""))
        text_preview = chunk["text"][:300].strip()
        parts.append(f"**{i}. {source}**\n{text_preview}\n")

    return "\n".join(parts)


def _generate_sql_if_applicable(question: str, related_tables: list[str]) -> SQLResult | None:
    """Attempt SQL generation for query-intent questions."""
    catalog = _get_catalog()
    if not related_tables:
        return None

    from ..planner import plan_query
    try:
        plan = plan_query(question, catalog=catalog)
        if plan.sql:
            from ..sql_validator import validate_sql
            validation = validate_sql(plan.sql, catalog)
            return SQLResult(
                sql=validation.sql,
                validated=validation.ok,
                errors=validation.errors,
                warnings=validation.warnings,
            )
    except Exception as exc:
        LOGGER.warning("SQL generation failed: %s", exc)
    return None


# ── Endpoints ─────────────────────────────────────────────────────────────


@app.get("/api/health")
def health():
    catalog = _get_catalog()
    return {
        "status": "healthy",
        "catalog_tables": len(catalog.tables),
        "catalog_domains": len(catalog.manifest.domains),
        "symbol_index_size": len(catalog.symbol_index),
    }


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest):
    start = time.time()

    intent = _classify_intent(req.question)
    chunks = _search_chunks(req.question, max_results=req.max_results)
    related = _resolve_related_tables(req.question)
    answer = _build_answer(req.question, chunks, intent)

    citations = [
        Citation(
            source=c["source"],
            title=c["title"],
            snippet=c["text"][:200],
            relevance_score=c["score"],
        )
        for c in chunks[:5]
    ]

    sql_result = None
    if req.include_sql and intent in (IntentType.sql, IntentType.ambiguous):
        sql_result = _generate_sql_if_applicable(req.question, related)

    # Manage conversation
    conv_id = req.conversation_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    if conv_id not in _conversations:
        _conversations[conv_id] = []
        _conversation_meta[conv_id] = {"created_at": now, "updated_at": now}
    _conversations[conv_id].append(
        ChatMessage(role=MessageRole.user, content=req.question, timestamp=now)
    )
    _conversations[conv_id].append(
        ChatMessage(role=MessageRole.assistant, content=answer, timestamp=now)
    )
    _conversation_meta[conv_id]["updated_at"] = now

    elapsed = (time.time() - start) * 1000

    return AskResponse(
        answer=answer,
        intent=intent,
        conversation_id=conv_id,
        citations=citations,
        sql_result=sql_result,
        related_tables=related,
        processing_time_ms=round(elapsed, 1),
    )


@app.post("/api/conversations/{conversation_id}/message", response_model=AskResponse)
def conversation_message(conversation_id: str, req: ConversationMessage):
    ask_req = AskRequest(
        question=req.message,
        conversation_id=conversation_id,
    )
    return ask(ask_req)


@app.get("/api/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: str):
    if conversation_id not in _conversations:
        raise HTTPException(404, f"Conversation {conversation_id} not found")
    meta = _conversation_meta[conversation_id]
    return ConversationResponse(
        conversation_id=conversation_id,
        messages=_conversations[conversation_id],
        created_at=meta["created_at"],
        updated_at=meta["updated_at"],
    )


@app.post("/api/validate-sql", response_model=ValidateSQLResponse)
def validate_sql_endpoint(req: ValidateSQLRequest):
    from ..sql_validator import validate_sql
    catalog = _get_catalog()
    result = validate_sql(req.sql, catalog, row_cap=req.row_cap)

    # Extract referenced tables
    tables_ref = []
    lower_tables = {t.fqn.lower(): t.fqn for t in catalog.tables}
    import re
    for match in re.findall(r'[a-zA-Z_]\w*\.[a-zA-Z_]\w*', req.sql):
        if match.lower() in lower_tables:
            tables_ref.append(lower_tables[match.lower()])

    return ValidateSQLResponse(
        original_sql=req.sql,
        rewritten_sql=result.sql,
        valid=result.ok,
        errors=result.errors,
        warnings=result.warnings,
        tables_referenced=tables_ref,
    )


@app.get("/api/catalog/search", response_model=CatalogSearchResponse)
def catalog_search(
    q: str = Query(default="", description="Search query"),
    domain: str | None = Query(default=None, description="Filter by domain code"),
    limit: int = Query(default=20, ge=1, le=200),
):
    catalog = _get_catalog()
    tables = catalog.tables

    if domain:
        tables = [t for t in tables if t.domain == domain]

    if q:
        lower_q = q.lower()
        scored: list[tuple[float, Any]] = []
        for t in tables:
            score = 0.0
            if lower_q in t.fqn.lower():
                score += 10.0
            if lower_q in t.table_name.lower():
                score += 8.0
            if t.description and lower_q in t.description.lower():
                score += 5.0
            for col in t.columns:
                if lower_q in col.name.lower():
                    score += 3.0
                    break
            for tag in t.tags:
                if lower_q in tag.lower():
                    score += 2.0
            if score > 0:
                scored.append((score, t))
        scored.sort(key=lambda x: -x[0])
        tables = [t for _, t in scored[:limit]]
    else:
        tables = tables[:limit]

    # Domain counts
    domain_counts: dict[str, int] = defaultdict(int)
    for t in catalog.tables:
        domain_counts[t.domain] += 1

    domain_info = [
        {"code": d.code, "name": d.name, "table_count": domain_counts.get(d.code, 0)}
        for d in catalog.manifest.domains
    ]

    return CatalogSearchResponse(
        tables=[
            TableInfo(
                fqn=t.fqn,
                domain=t.domain,
                description=t.description,
                update_cadence=t.update_cadence,
                temporal_model=t.temporal_model,
                column_count=len(t.columns),
                columns=[
                    ColumnInfo(
                        name=c.name,
                        type=c.type,
                        nullable=c.nullable,
                        description=c.description,
                    )
                    for c in t.columns
                ],
                tags=t.tags,
            )
            for t in tables
        ],
        total_count=len(catalog.tables),
        domains=domain_info,
    )


@app.get("/api/catalog/tables/{fqn}")
def get_table(fqn: str):
    catalog = _get_catalog()
    table = catalog.get_table(fqn)
    if not table:
        raise HTTPException(404, f"Table {fqn} not found")
    return TableInfo(
        fqn=table.fqn,
        domain=table.domain,
        description=table.description,
        update_cadence=table.update_cadence,
        temporal_model=table.temporal_model,
        column_count=len(table.columns),
        columns=[
            ColumnInfo(
                name=c.name,
                type=c.type,
                nullable=c.nullable,
                description=c.description,
            )
            for c in table.columns
        ],
        tags=table.tags,
    )


@app.get("/api/catalog/domains", response_model=DomainsResponse)
def list_domains():
    catalog = _get_catalog()
    domain_counts: dict[str, int] = defaultdict(int)
    for t in catalog.tables:
        domain_counts[t.domain] += 1

    domains = [
        DomainInfo(
            code=d.code,
            name=d.name,
            table_count=domain_counts.get(d.code, 0),
            anchor_keys=d.anchor_keys,
        )
        for d in catalog.manifest.domains
    ]
    domains.sort(key=lambda d: -d.table_count)

    return DomainsResponse(
        domains=domains,
        total_tables=len(catalog.tables),
    )


# ── Mount the frontend ────────────────────────────────────────────────────

_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
