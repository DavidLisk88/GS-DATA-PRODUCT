"""Shared SQL validate-and-execute utility.

Consolidates the repeated pattern of validating generated SQL against the
catalog, then executing it in DuckDB, that previously appeared in the CLI
``ask`` command, the ``eval`` command, and the Streamlit UI.
"""
from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd

from .catalog import Catalog
from .sql_validator import ValidationResult, validate_sql


@dataclass
class SQLExecutionResult:
    """Outcome of a validate-then-execute cycle."""

    validation: ValidationResult
    dataframe: pd.DataFrame | None = None
    error: str | None = None

    @property
    def executed(self) -> bool:
        return self.dataframe is not None

    @property
    def ok(self) -> bool:
        return self.validation.ok and self.executed and self.error is None


def execute_validated_sql(
    sql: str,
    catalog: Catalog,
    con: duckdb.DuckDBPyConnection,
    *,
    row_cap: int = 1000,
) -> SQLExecutionResult:
    """Validate *sql* against the catalog, then execute it in *con*.

    Returns a :class:`SQLExecutionResult` regardless of whether validation
    or execution fails, so callers never need bare ``try / except`` around
    this path.
    """
    validation = validate_sql(sql, catalog, row_cap=row_cap)
    if not validation.ok:
        return SQLExecutionResult(validation=validation)
    try:
        df = con.execute(validation.sql).fetchdf()
        return SQLExecutionResult(validation=validation, dataframe=df)
    except Exception as exc:
        return SQLExecutionResult(validation=validation, error=str(exc))
