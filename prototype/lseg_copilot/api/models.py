"""Pydantic request/response models for the agent API."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────

class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class IntentType(str, Enum):
    sql = "sql"
    definitional = "definitional"
    navigation = "navigation"
    ambiguous = "ambiguous"


# ── Chat / Conversation ───────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000)
    conversation_id: str | None = None
    include_sql: bool = True
    include_citations: bool = True
    max_results: int = Field(default=10, ge=1, le=50)


class Citation(BaseModel):
    source: str
    title: str
    snippet: str
    relevance_score: float = 0.0


class SQLResult(BaseModel):
    sql: str
    dialect: str = "duckdb"
    validated: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    row_count: int | None = None
    columns: list[str] = Field(default_factory=list)
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)


class AskResponse(BaseModel):
    answer: str
    intent: IntentType
    conversation_id: str
    citations: list[Citation] = Field(default_factory=list)
    sql_result: SQLResult | None = None
    related_tables: list[str] = Field(default_factory=list)
    processing_time_ms: float = 0.0


# ── Conversation ──────────────────────────────────────────────────────────

class ConversationMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class ConversationResponse(BaseModel):
    conversation_id: str
    messages: list[ChatMessage]
    created_at: datetime
    updated_at: datetime


# ── SQL Validation ────────────────────────────────────────────────────────

class ValidateSQLRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=50000)
    row_cap: int = Field(default=1000, ge=1, le=100000)


class ValidateSQLResponse(BaseModel):
    original_sql: str
    rewritten_sql: str
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tables_referenced: list[str] = Field(default_factory=list)


# ── Catalog Search ────────────────────────────────────────────────────────

class CatalogSearchRequest(BaseModel):
    query: str = Field(default="", max_length=500)
    domain: str | None = None
    limit: int = Field(default=20, ge=1, le=200)


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool = True
    description: str | None = None


class TableInfo(BaseModel):
    fqn: str
    domain: str
    description: str | None = None
    update_cadence: str | None = None
    temporal_model: str | None = None
    column_count: int = 0
    columns: list[ColumnInfo] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class CatalogSearchResponse(BaseModel):
    tables: list[TableInfo]
    total_count: int
    domains: list[dict[str, Any]] = Field(default_factory=list)


# ── Domain listing ────────────────────────────────────────────────────────

class DomainInfo(BaseModel):
    code: str
    name: str
    table_count: int
    anchor_keys: list[str] = Field(default_factory=list)


class DomainsResponse(BaseModel):
    domains: list[DomainInfo]
    total_tables: int
