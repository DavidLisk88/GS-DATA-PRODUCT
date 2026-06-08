"""Load the sample CSVs into a DuckDB warehouse, mounting each CSV under its
fully-qualified ``schema.table`` name from the catalog manifest."""
from __future__ import annotations

from pathlib import Path

import duckdb

from .catalog import Catalog, TableSpec
from .paths import workspace_paths


# Maps the CSV filename (sans .csv) to the canonical FQN it should be loaded as.
# Where the CSV name doesn't match the YAML `table:` field, we map manually.
CSV_TO_FQN: dict[str, str] = {
    "entity_master": "lseg_ref.entity_master",
    "instrument_master": "lseg_ref.instrument_master",
    "quote_master": "lseg_ref.quote_master",
    "eod_pricing": "lseg_dss.eod_pricing",
    "fx_rates_eod": "lseg_fx.fx_rates_eod",
    "corporate_actions": "lseg_ref.corporate_actions",
    "corporate_action_terms": "lseg_ref.corporate_action_terms",
    "company_fundamentals": "lseg_wsf.company_fundamentals",
    "ibes_ticker_xref": "lseg_ibes.ibes_ticker_xref",
    "estimate_consensus": "lseg_ibes.estimate_consensus",
    "bond_terms": "lseg_fi.bond_terms",
    "credit_ratings_history": "lseg_fi.credit_ratings_history",
    "yield_curves_eod": "lseg_fi.yield_curves_eod",
    "futures_series_chain": "lseg_drv.futures_series_chain",
    "futures_contracts": "lseg_drv.futures_contracts",
    "options_chain": "lseg_drv.options_chain",
    "options_eod_iv": "lseg_drv.options_eod_iv",
    "fund_master": "lseg_lipper.fund_master",
    "wc_individuals": "lseg_wc.wc_individuals",
    "wc_sanctions_listings": "lseg_wc.wc_sanctions_listings",
}


def open_warehouse(db_path: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path))
    return con


def load_sample_data(
    con: duckdb.DuckDBPyConnection,
    catalog: Catalog | None = None,
) -> dict[str, int]:
    """Create one DuckDB schema per LSEG schema and load matching CSVs.

    Returns a {fqn: row_count} mapping for the tables actually loaded.
    Tables whose CSV is missing are silently skipped.
    """
    paths = workspace_paths()
    sample_dir = paths["sample_data_dir"]
    loaded: dict[str, int] = {}

    schemas_seen: set[str] = set()

    for csv_path in sorted(sample_dir.glob("*.csv")):
        stem = csv_path.stem
        fqn = CSV_TO_FQN.get(stem)
        if not fqn:
            # Unknown CSV — load it into a sandbox schema instead of dropping it.
            fqn = f"sandbox.{stem}"
        schema, table = fqn.split(".", 1)
        if schema not in schemas_seen:
            con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            schemas_seen.add(schema)
        con.execute(
            f'CREATE OR REPLACE TABLE "{schema}"."{table}" AS '
            f"SELECT * FROM read_csv_auto('{csv_path.as_posix()}', header=True, sample_size=-1)"
        )
        row_count = con.execute(
            f'SELECT COUNT(*) FROM "{schema}"."{table}"'
        ).fetchone()[0]
        loaded[fqn] = int(row_count)

    # Catalog tables that have no CSV: create an empty view so downstream
    # planner doesn't trip on "table not found" when schema is correct.
    if catalog is not None:
        for table_spec in catalog.tables:
            if table_spec.fqn in loaded:
                continue
            _create_empty_table_from_spec(con, table_spec)

    return loaded


def _create_empty_table_from_spec(
    con: duckdb.DuckDBPyConnection, spec: TableSpec
) -> None:
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{spec.schema_name}"')
    if not spec.columns:
        # No column info — skip.
        return
    col_defs = ", ".join(
        f'"{c.name}" {_normalize_type(c.type)}' for c in spec.columns
    )
    con.execute(
        f'CREATE TABLE IF NOT EXISTS "{spec.schema_name}"."{spec.table_name}" ({col_defs})'
    )


def _normalize_type(raw: str) -> str:
    """Map YAML types -> DuckDB types. ARRAY<...> becomes VARCHAR[]."""
    cleaned = raw.strip()
    upper = cleaned.upper()
    if upper.startswith("ARRAY<"):
        return "VARCHAR[]"
    # DuckDB doesn't support TIMESTAMP(6) directly; map to TIMESTAMP.
    if upper.startswith("TIMESTAMP("):
        return "TIMESTAMP"
    return cleaned


def summarise_warehouse(con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, int]]:
    """Return {schema: {table: row_count}} for everything in the warehouse."""
    rows = con.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'main')
        ORDER BY table_schema, table_name
        """
    ).fetchall()
    result: dict[str, dict[str, int]] = {}
    for schema, table in rows:
        try:
            count = con.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"').fetchone()[0]
        except duckdb.Error:
            count = 0
        result.setdefault(schema, {})[table] = int(count)
    return result
