"""Quick smoke test — designed to run without sentence-transformers or an LLM.

    cd prototype
    pip install -e .
    pytest -q
"""
from __future__ import annotations

import duckdb
import pytest

from lseg_copilot.catalog import Catalog
from lseg_copilot.pipeline import CopilotPipeline, bootstrap
from lseg_copilot.planner import Planner
from lseg_copilot.reasoner import StubReasoner
from lseg_copilot.retriever import HybridRetriever
from lseg_copilot.sql_validator import validate_sql


@pytest.fixture(scope="module")
def pipe() -> CopilotPipeline:
    return bootstrap(load_warehouse=True)


@pytest.fixture(scope="module")
def catalog(pipe: CopilotPipeline) -> Catalog:
    return pipe.catalog


@pytest.fixture(scope="module")
def warehouse(pipe: CopilotPipeline) -> duckdb.DuckDBPyConnection:
    assert pipe.warehouse is not None
    return pipe.warehouse


@pytest.fixture(scope="module")
def retriever(pipe: CopilotPipeline) -> HybridRetriever:
    return pipe.retriever


def test_catalog_loads_expected_minimum_tables(catalog: Catalog) -> None:
    fqns = {t.fqn for t in catalog.tables}
    for must_have in [
        "lseg_ref.entity_master",
        "lseg_ref.instrument_master",
        "lseg_dss.eod_pricing",
        "lseg_wsf.company_fundamentals",
        "lseg_fi.bond_terms",
        "lseg_fi.credit_ratings_history",
        "lseg_drv.options_chain",
        "lseg_lipper.fund_master",
        "lseg_wc.wc_individuals",
    ]:
        assert must_have in fqns, f"{must_have} missing from catalog manifest"


def test_world_check_marked_restricted(catalog: Catalog) -> None:
    wc = catalog.get_table("lseg_wc.wc_individuals")
    assert wc is not None
    assert wc.restricted or wc.has_restricted_columns


def test_aapl_close_2026_05_28(warehouse: duckdb.DuckDBPyConnection) -> None:
    row = warehouse.execute(
        "SELECT close_price FROM lseg_dss.eod_pricing "
        "WHERE ric_as_of = 'AAPL.OQ' AND price_date = DATE '2026-05-28'"
    ).fetchone()
    assert row is not None
    assert abs(row[0] - 218.55) < 0.01


def test_planner_refuses_world_check_without_entitlement(
    catalog: Catalog, retriever: HybridRetriever
) -> None:
    planner = Planner(catalog)
    question = "List all individuals in World-Check on the OFAC SDN list."
    retrieved = retriever.search(question, top_k=8)
    plan = planner.plan(question, retrieved, user_entitlements=[])
    assert plan.intent == "refusal", f"Expected refusal, got {plan.intent}"
    assert "LSEG_WC_VIEWER" in (plan.refusal_reason or "")


def test_sql_validator_rejects_unknown_table(catalog: Catalog) -> None:
    result = validate_sql(
        "SELECT * FROM lseg_ref.no_such_table WHERE x = 1", catalog
    )
    assert not result.ok
    assert any("Unknown table" in e for e in result.errors)


def test_sql_validator_injects_row_cap(catalog: Catalog) -> None:
    result = validate_sql(
        "SELECT close_price FROM lseg_dss.eod_pricing WHERE ric_as_of = 'AAPL.OQ'",
        catalog,
    )
    assert result.ok
    assert "LIMIT" in result.sql.upper()


def test_stub_reasoner_produces_runnable_sql_for_sq0001(
    catalog: Catalog,
    warehouse: duckdb.DuckDBPyConnection,
    retriever: HybridRetriever,
) -> None:
    planner = Planner(catalog)
    question = "List Apple's open, close and volume on 2026-05-28."
    retrieved = retriever.search(question, top_k=8)
    plan = planner.plan(question, retrieved)
    answer = StubReasoner(catalog).answer(plan, question_id="SQ-0001")
    assert answer.sql is not None
    validation = validate_sql(answer.sql, catalog)
    assert validation.ok, validation.errors
    df = warehouse.execute(validation.sql).fetchdf()
    assert len(df) == 1
    assert abs(float(df["close_price"].iloc[0]) - 218.55) < 0.01
