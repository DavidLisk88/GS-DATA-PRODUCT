"""Unit tests for lseg_copilot.planner — covers company resolution,
date normalisation, PIT as-of / as-known-on detection, currency-mix
detection, SQL intent classification, and _question_targets_table."""
from __future__ import annotations

import pytest

from lseg_copilot.catalog import Catalog
from lseg_copilot.indexer import build_index
from lseg_copilot.planner import Planner
from lseg_copilot.retriever import HybridRetriever


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


@pytest.fixture(scope="module")
def retriever(catalog: Catalog) -> HybridRetriever:
    artifacts = build_index(catalog=catalog, embed=False)
    return HybridRetriever(artifacts, catalog)


# ------------------------------------------------------------------ #
# _resolve_companies                                                  #
# ------------------------------------------------------------------ #

class TestResolveCompanies:
    def test_apple_resolved(self, catalog: Catalog) -> None:
        planner = Planner(catalog)
        ids = planner._resolve_companies("Show Apple's revenue.")
        assert len(ids) == 1
        assert ids[0].primary_ric == "AAPL.OQ"
        assert ids[0].org_perm_id == 4295905573

    def test_multiple_companies(self, catalog: Catalog) -> None:
        planner = Planner(catalog)
        ids = planner._resolve_companies("Compare Apple and Microsoft earnings.")
        rics = {b.primary_ric for b in ids}
        assert "AAPL.OQ" in rics
        assert "MSFT.OQ" in rics

    def test_deduplication(self, catalog: Catalog) -> None:
        # "apple" and "aapl" both map to the same org_perm_id.
        planner = Planner(catalog)
        ids = planner._resolve_companies("Apple AAPL stock")
        assert len(ids) == 1

    def test_meta_has_historical_rics(self, catalog: Catalog) -> None:
        planner = Planner(catalog)
        ids = planner._resolve_companies("What is Meta's stock price?")
        assert len(ids) == 1
        assert ids[0].historical_rics == ["FB.OQ"]

    def test_no_match(self, catalog: Catalog) -> None:
        planner = Planner(catalog)
        ids = planner._resolve_companies("Tell me about the weather.")
        assert ids == []


# ------------------------------------------------------------------ #
# _normalise_date                                                     #
# ------------------------------------------------------------------ #

class TestNormaliseDate:
    def test_slash_format(self) -> None:
        assert Planner._normalise_date("2026/5/3") == "2026-05-03"

    def test_hyphen_format(self) -> None:
        assert Planner._normalise_date("2024-11-15") == "2024-11-15"

    def test_non_matching_passthrough(self) -> None:
        assert Planner._normalise_date("not-a-date") == "not-a-date"


# ------------------------------------------------------------------ #
# _currencies_in_question                                             #
# ------------------------------------------------------------------ #

class TestCurrenciesInQuestion:
    def test_two_currencies_detected(self) -> None:
        result = Planner._currencies_in_question("Convert revenue from JPY to USD")
        assert result == {"JPY", "USD"}

    def test_no_currencies(self) -> None:
        result = Planner._currencies_in_question("What is Apple's revenue?")
        assert result == set()

    def test_non_currency_three_letter_ignored(self) -> None:
        result = Planner._currencies_in_question("Show the BIG table")
        assert result == set()


# ------------------------------------------------------------------ #
# _question_targets_table                                             #
# ------------------------------------------------------------------ #

class TestQuestionTargetsTable:
    def test_domain_match(self, catalog: Catalog) -> None:
        spec = catalog.get_table("lseg_wc.wc_individuals")
        assert spec is not None
        assert Planner._question_targets_table("List all World-Check entries", spec)

    def test_table_name_match(self, catalog: Catalog) -> None:
        spec = catalog.get_table("lseg_ref.entity_master")
        assert spec is not None
        assert Planner._question_targets_table("Query entity_master for Apple", spec)

    def test_no_match(self, catalog: Catalog) -> None:
        spec = catalog.get_table("lseg_ref.entity_master")
        assert spec is not None
        assert not Planner._question_targets_table("What is the weather?", spec)


# ------------------------------------------------------------------ #
# PIT (point-in-time) detection                                       #
# ------------------------------------------------------------------ #

class TestPITDetection:
    def test_as_of_detected(self, catalog: Catalog, retriever: HybridRetriever) -> None:
        planner = Planner(catalog)
        q = "What was Apple's entity name as-of 2010-06-01?"
        retrieved = retriever.search(q, top_k=8)
        plan = planner.plan(q, retrieved)
        assert plan.as_of_ts is not None
        assert "2010-06-01" in plan.as_of_ts

    def test_as_known_on_detected(self, catalog: Catalog, retriever: HybridRetriever) -> None:
        planner = Planner(catalog)
        q = "Show Apple's revenue as it was known on 2024-11-15"
        retrieved = retriever.search(q, top_k=8)
        plan = planner.plan(q, retrieved)
        assert plan.as_of_ts is not None
        assert "2024-11-15" in plan.as_of_ts

    def test_no_pit(self, catalog: Catalog, retriever: HybridRetriever) -> None:
        planner = Planner(catalog)
        q = "What is Apple's stock price?"
        retrieved = retriever.search(q, top_k=8)
        plan = planner.plan(q, retrieved)
        assert plan.as_of_ts is None


# ------------------------------------------------------------------ #
# SQL intent classification                                           #
# ------------------------------------------------------------------ #

class TestIntentClassification:
    def test_sql_intent_for_data_query(
        self, catalog: Catalog, retriever: HybridRetriever
    ) -> None:
        planner = Planner(catalog)
        q = "List Apple's close price on 2026-05-28"
        retrieved = retriever.search(q, top_k=8)
        plan = planner.plan(q, retrieved)
        assert plan.intent == "sql"

    def test_definitional_intent(
        self, catalog: Catalog, retriever: HybridRetriever
    ) -> None:
        planner = Planner(catalog)
        q = "What is a PermID?"
        retrieved = retriever.search(q, top_k=8)
        plan = planner.plan(q, retrieved)
        assert plan.intent == "definitional"


# ------------------------------------------------------------------ #
# Currency-mix note                                                   #
# ------------------------------------------------------------------ #

class TestCurrencyMixNote:
    def test_mixed_currencies_note_added(
        self, catalog: Catalog, retriever: HybridRetriever
    ) -> None:
        planner = Planner(catalog)
        q = "Compare Apple revenue in JPY and USD"
        retrieved = retriever.search(q, top_k=8)
        plan = planner.plan(q, retrieved)
        assert any("Currency mix" in n for n in plan.notes)
