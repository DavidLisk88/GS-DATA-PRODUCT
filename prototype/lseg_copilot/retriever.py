"""Hybrid retriever: BM25 + (optional) FAISS dense, fused with RRF + symbol boost."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from .catalog import Catalog
from .indexer import Chunk, IndexArtifacts, _tokenise

LOGGER = logging.getLogger(__name__)

try:
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover
    np = None  # type: ignore


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float
    why: str  # short explanation of score components


class HybridRetriever:
    def __init__(
        self,
        artifacts: IndexArtifacts,
        catalog: Catalog,
        *,
        bm25_k: int = 20,
        dense_k: int = 20,
        rrf_k: int = 60,
        symbol_boost: float = 0.15,
    ) -> None:
        self.artifacts = artifacts
        self.catalog = catalog
        self.bm25_k = bm25_k
        self.dense_k = dense_k
        self.rrf_k = rrf_k
        self.symbol_boost = symbol_boost

    # ------------------------------------------------------------------ #
    def search(self, query: str, *, top_k: int = 8) -> list[RetrievedChunk]:
        chunks = self.artifacts.chunks
        if not chunks:
            return []

        tokens = _tokenise(query)
        bm25_scores = self.artifacts.bm25.get_scores(tokens)

        bm25_rank = self._rank(bm25_scores, self.bm25_k)
        dense_rank: dict[int, int] = {}
        if self.artifacts.faiss_index is not None and np is not None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                model = SentenceTransformer(self.artifacts.embedding_model_name)
                q_vec = model.encode(
                    [query], convert_to_numpy=True, normalize_embeddings=True
                )
                k = min(self.dense_k, len(chunks))
                _, idxs = self.artifacts.faiss_index.search(q_vec, k)
                for rank, idx in enumerate(idxs[0].tolist()):
                    dense_rank[idx] = rank + 1
            except Exception as exc:  # pragma: no cover
                LOGGER.warning("Dense retrieval failed, falling back to BM25-only: %s", exc)
                dense_rank = {}

        # Find mentioned symbols in the query so we can boost matching chunks.
        boosted_symbols = self._symbols_in_query(query)

        rrf_scores: dict[int, float] = {}
        for idx, rank in bm25_rank.items():
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (self.rrf_k + rank)
        for idx, rank in dense_rank.items():
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (self.rrf_k + rank)

        if boosted_symbols:
            for idx, ch in enumerate(chunks):
                if any(sym in ch.symbols for sym in boosted_symbols):
                    rrf_scores[idx] = rrf_scores.get(idx, 0.0) + self.symbol_boost

        ranked = sorted(rrf_scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        out: list[RetrievedChunk] = []
        for idx, score in ranked:
            ch = chunks[idx]
            why_bits = []
            if idx in bm25_rank:
                why_bits.append(f"bm25@{bm25_rank[idx]}")
            if idx in dense_rank:
                why_bits.append(f"dense@{dense_rank[idx]}")
            if any(sym in ch.symbols for sym in boosted_symbols):
                why_bits.append("symbol_boost")
            out.append(RetrievedChunk(chunk=ch, score=score, why=",".join(why_bits)))
        return out

    # ------------------------------------------------------------------ #
    @staticmethod
    def _rank(scores: Iterable[float], top_k: int) -> dict[int, int]:
        scored = sorted(enumerate(scores), key=lambda kv: kv[1], reverse=True)[:top_k]
        return {idx: rank + 1 for rank, (idx, _) in enumerate(scored)}

    # ------------------------------------------------------------------ #
    def _symbols_in_query(self, query: str) -> list[str]:
        ql = query.lower()
        # Match table names, column names, and FQNs by substring.
        # Use word boundary for short identifiers to avoid spurious matches.
        out: list[str] = []
        for sym in self.catalog.symbol_index:
            if len(sym) >= 4 and re.search(rf"\b{re.escape(sym)}\b", ql):
                out.extend(self.catalog.symbol_index[sym])
        return sorted(set(out))
