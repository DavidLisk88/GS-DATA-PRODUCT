"""Shared pipeline bootstrap: single place to wire up the Catalog, Indexer,
Retriever, Planner, and (optionally) the DuckDB warehouse.

Every entry-point that needs the full stack (CLI commands, Streamlit UI, tests)
should call ``bootstrap()`` instead of duplicating the wiring inline.
"""
from __future__ import annotations

from dataclasses import dataclass

import duckdb

from .catalog import Catalog
from .data_loader import load_sample_data, open_warehouse
from .indexer import IndexArtifacts, build_index
from .planner import Planner
from .retriever import HybridRetriever


@dataclass
class CopilotPipeline:
    catalog: Catalog
    artifacts: IndexArtifacts
    retriever: HybridRetriever
    planner: Planner
    warehouse: duckdb.DuckDBPyConnection | None = None


def bootstrap(
    *,
    embed: bool = False,
    load_warehouse: bool = False,
) -> CopilotPipeline:
    """Build the full Copilot pipeline with a single call.

    Parameters
    ----------
    embed:
        If *True* and the embedding stack is installed, build a FAISS dense
        index alongside BM25.  Defaults to *False* (cheap lexical-only path).
    load_warehouse:
        If *True*, open an in-memory DuckDB, load all sample CSVs, and attach
        the connection to the returned pipeline.
    """
    catalog = Catalog.load()
    artifacts = build_index(catalog=catalog, embed=embed)
    retriever = HybridRetriever(artifacts, catalog)
    planner = Planner(catalog)

    warehouse: duckdb.DuckDBPyConnection | None = None
    if load_warehouse:
        warehouse = open_warehouse()
        load_sample_data(warehouse, catalog=catalog)

    return CopilotPipeline(
        catalog=catalog,
        artifacts=artifacts,
        retriever=retriever,
        planner=planner,
        warehouse=warehouse,
    )
