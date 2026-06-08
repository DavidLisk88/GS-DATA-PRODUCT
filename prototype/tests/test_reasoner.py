"""Unit tests for lseg_copilot.reasoner — covers StubReasoner refusal path,
no-SQL fallback, note/identifier rendering, and LLMReasoner with a mock client."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from lseg_copilot.catalog import Catalog
from lseg_copilot.indexer import Chunk
from lseg_copilot.planner import IdentifierBinding, PlanResult
from lseg_copilot.reasoner import Answer, LLMReasoner, StubReasoner
from lseg_copilot.retriever import RetrievedChunk


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


def _make_retrieved(n: int = 3) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk=Chunk(
                chunk_id=f"chk_{i}",
                source_path=f"docs/page{i}.md",
                title=f"Section {i}",
                text=f"Content of section {i}",
            ),
            score=1.0 / (i + 1),
            why="bm25@1",
        )
        for i in range(n)
    ]


# ------------------------------------------------------------------ #
# StubReasoner                                                        #
# ------------------------------------------------------------------ #

class TestStubReasonerRefusal:
    def test_refusal_returns_refused_answer(self, catalog: Catalog) -> None:
        plan = PlanResult(
            question="Show me World-Check individuals",
            intent="refusal",
            refusal_reason="Table `lseg_wc.wc_individuals` requires entitlement `LSEG_WC_VIEWER`",
            retrieved=_make_retrieved(),
        )
        answer = StubReasoner(catalog).answer(plan)
        assert answer.refusal is True
        assert "REFUSED" in answer.text
        assert answer.sql is None
        assert answer.confidence == 0.95


class TestStubReasonerNoSql:
    def test_no_question_id_returns_citation_only(self, catalog: Catalog) -> None:
        plan = PlanResult(
            question="What is a PermID?",
            intent="definitional",
            retrieved=_make_retrieved(4),
        )
        answer = StubReasoner(catalog).answer(plan)
        assert answer.sql is None
        assert answer.confidence == 0.4
        assert "most relevant" in answer.text
        assert len(answer.citations) == 4

    def test_notes_rendered_in_text(self, catalog: Catalog) -> None:
        plan = PlanResult(
            question="Convert Apple revenue to JPY",
            intent="sql",
            retrieved=_make_retrieved(2),
            notes=["Currency mix detected (JPY, USD)."],
        )
        answer = StubReasoner(catalog).answer(plan)
        assert "Currency mix" in answer.text

    def test_identifiers_rendered_in_text(self, catalog: Catalog) -> None:
        plan = PlanResult(
            question="Show Apple stock price",
            intent="sql",
            retrieved=_make_retrieved(2),
            identifiers=[
                IdentifierBinding(
                    name_in_question="apple",
                    company_key="apple",
                    org_perm_id=4295905573,
                    primary_ric="AAPL.OQ",
                )
            ],
        )
        answer = StubReasoner(catalog).answer(plan)
        assert "AAPL.OQ" in answer.text
        assert "4295905573" in answer.text


class TestStubReasonerWithSql:
    def test_known_question_id_returns_sql(self, catalog: Catalog) -> None:
        plan = PlanResult(
            question="List Apple's open, close and volume on 2026-05-28.",
            intent="sql",
            retrieved=_make_retrieved(),
        )
        answer = StubReasoner(catalog).answer(plan, question_id="SQ-0001")
        assert answer.sql is not None
        assert "eod_pricing" in answer.sql
        assert answer.confidence == 0.6

    def test_unknown_question_id_returns_no_sql(self, catalog: Catalog) -> None:
        plan = PlanResult(
            question="Some unknown question",
            intent="sql",
            retrieved=_make_retrieved(),
        )
        answer = StubReasoner(catalog).answer(plan, question_id="SQ-9999")
        assert answer.sql is None


# ------------------------------------------------------------------ #
# LLMReasoner (mocked client)                                        #
# ------------------------------------------------------------------ #

class _MockLLMClient:
    """Simple mock that returns configurable responses."""

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, *, system: str, user: str) -> str:
        return self._response


class TestLLMReasonerRefusal:
    def test_refusal_skips_llm_call(self, catalog: Catalog) -> None:
        client = _MockLLMClient('{"answer": "should not see this"}')
        plan = PlanResult(
            question="Show World-Check",
            intent="refusal",
            refusal_reason="Not entitled",
            retrieved=_make_retrieved(),
        )
        answer = LLMReasoner(catalog, client).answer(plan)
        assert answer.refusal is True
        assert "REFUSED" in answer.text


class TestLLMReasonerNormal:
    def test_valid_json_response_parsed(self, catalog: Catalog) -> None:
        client = _MockLLMClient(
            '{"answer": "Apple closed at 218.55", "sql": "SELECT 1", "citations": ["docs/a.md"]}'
        )
        plan = PlanResult(
            question="Apple close price",
            intent="sql",
            retrieved=_make_retrieved(),
            candidate_tables=["lseg_dss.eod_pricing"],
            identifiers=[
                IdentifierBinding(
                    name_in_question="apple",
                    company_key="apple",
                    org_perm_id=4295905573,
                    primary_ric="AAPL.OQ",
                )
            ],
        )
        answer = LLMReasoner(catalog, client).answer(plan)
        assert answer.text == "Apple closed at 218.55"
        assert answer.sql == "SELECT 1"
        assert answer.citations == ["docs/a.md"]
        assert answer.confidence == 0.75

    def test_non_json_response_handled(self, catalog: Catalog) -> None:
        client = _MockLLMClient("This is not JSON at all")
        plan = PlanResult(
            question="Anything",
            intent="sql",
            retrieved=_make_retrieved(),
        )
        answer = LLMReasoner(catalog, client).answer(plan)
        assert "non-JSON" in answer.text
        assert answer.confidence == 0.2
