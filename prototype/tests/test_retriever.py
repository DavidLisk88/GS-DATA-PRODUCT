"""Unit tests for lseg_copilot.retriever — covers empty-chunks edge case,
_rank helper, _symbols_in_query, and symbol-boost scoring."""
from __future__ import annotations

import pytest

from lseg_copilot.catalog import Catalog
from lseg_copilot.indexer import Chunk, IndexArtifacts, _tokenise, build_index
from lseg_copilot.retriever import HybridRetriever

from rank_bm25 import BM25Okapi


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


@pytest.fixture(scope="module")
def retriever(catalog: Catalog) -> HybridRetriever:
    artifacts = build_index(catalog=catalog, embed=False)
    return HybridRetriever(artifacts, catalog)


# ------------------------------------------------------------------ #
# Empty chunks                                                        #
# ------------------------------------------------------------------ #

class TestEmptyChunks:
    def test_search_returns_empty_for_no_chunks(self, catalog: Catalog) -> None:
        empty_artifacts = IndexArtifacts(
            chunks=[],
            bm25_tokens=[],
            bm25=BM25Okapi([["placeholder"]]),  # BM25 needs at least one doc
        )
        ret = HybridRetriever(empty_artifacts, catalog)
        results = ret.search("anything")
        assert results == []


# ------------------------------------------------------------------ #
# _rank                                                               #
# ------------------------------------------------------------------ #

class TestRank:
    def test_top_k_ordering(self) -> None:
        scores = [0.1, 0.9, 0.5, 0.3]
        ranked = HybridRetriever._rank(scores, top_k=2)
        # Top-2 by score: index 1 (0.9) → rank 1, index 2 (0.5) → rank 2.
        assert ranked[1] == 1
        assert ranked[2] == 2
        assert len(ranked) == 2

    def test_top_k_larger_than_list(self) -> None:
        scores = [0.5, 0.1]
        ranked = HybridRetriever._rank(scores, top_k=10)
        assert len(ranked) == 2


# ------------------------------------------------------------------ #
# _symbols_in_query                                                   #
# ------------------------------------------------------------------ #

class TestSymbolsInQuery:
    def test_finds_table_name(self, retriever: HybridRetriever) -> None:
        symbols = retriever._symbols_in_query("Show me the entity_master table")
        assert any("entity_master" in s for s in symbols)

    def test_short_tokens_ignored(self, retriever: HybridRetriever) -> None:
        # Symbols shorter than 4 chars should be skipped.
        symbols = retriever._symbols_in_query("id pk fqn")
        assert symbols == []

    def test_no_match_returns_empty(self, retriever: HybridRetriever) -> None:
        symbols = retriever._symbols_in_query("completely unrelated gibberish xyzzy")
        assert symbols == []


# ------------------------------------------------------------------ #
# Symbol boost affects ranking                                        #
# ------------------------------------------------------------------ #

class TestSymbolBoost:
    def test_symbol_boost_appears_in_why(self, retriever: HybridRetriever) -> None:
        results = retriever.search("entity_master org_perm_id", top_k=10)
        # At least one result should mention symbol_boost in its why field.
        assert any("symbol_boost" in r.why for r in results)

    def test_search_returns_scored_results(self, retriever: HybridRetriever) -> None:
        results = retriever.search("Apple close price 2026-05-28", top_k=5)
        assert len(results) > 0
        # Scores should be positive and descending.
        scores = [r.score for r in results]
        assert all(s > 0 for s in scores)
        assert scores == sorted(scores, reverse=True)
