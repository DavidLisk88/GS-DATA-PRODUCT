"""Unit tests for lseg_copilot.data_loader — targets the uncovered helpers:
_normalize_type, _create_empty_table_from_spec, summarise_warehouse,
and the sandbox-CSV fallback path."""
from __future__ import annotations

import textwrap
from pathlib import Path

import duckdb
import pytest

from lseg_copilot.catalog import Catalog, ColumnSpec, TableSpec
from lseg_copilot.data_loader import (
    _create_empty_table_from_spec,
    _normalize_type,
    load_sample_data,
    open_warehouse,
    summarise_warehouse,
)


# ------------------------------------------------------------------ #
# _normalize_type                                                     #
# ------------------------------------------------------------------ #

class TestNormalizeType:
    def test_array_type_mapped_to_varchar_array(self) -> None:
        assert _normalize_type("ARRAY<VARCHAR>") == "VARCHAR[]"

    def test_array_type_case_insensitive(self) -> None:
        assert _normalize_type("array<int>") == "VARCHAR[]"

    def test_timestamp_with_precision_mapped(self) -> None:
        assert _normalize_type("TIMESTAMP(6)") == "TIMESTAMP"

    def test_timestamp_lower(self) -> None:
        assert _normalize_type("timestamp(3)") == "TIMESTAMP"

    def test_plain_varchar_passthrough(self) -> None:
        assert _normalize_type("VARCHAR") == "VARCHAR"

    def test_integer_passthrough(self) -> None:
        assert _normalize_type("INTEGER") == "INTEGER"

    def test_whitespace_stripped(self) -> None:
        assert _normalize_type("  DATE  ") == "DATE"


# ------------------------------------------------------------------ #
# _create_empty_table_from_spec                                       #
# ------------------------------------------------------------------ #

class TestCreateEmptyTableFromSpec:
    def test_creates_table_with_columns(self) -> None:
        spec = TableSpec(
            fqn="test_schema.test_table",
            domain="test",
            columns=[
                ColumnSpec(name="id", type="INTEGER", nullable=False, pk=True),
                ColumnSpec(name="name", type="VARCHAR"),
            ],
        )
        con = duckdb.connect(":memory:")
        _create_empty_table_from_spec(con, spec)
        row = con.execute(
            "SELECT COUNT(*) FROM test_schema.test_table"
        ).fetchone()
        assert row is not None
        assert row[0] == 0

    def test_skips_table_with_no_columns(self) -> None:
        spec = TableSpec(fqn="empty_schema.empty_table", domain="test", columns=[])
        con = duckdb.connect(":memory:")
        _create_empty_table_from_spec(con, spec)
        # Table should NOT exist because there were no columns.
        with pytest.raises(duckdb.Error):
            con.execute("SELECT * FROM empty_schema.empty_table")


# ------------------------------------------------------------------ #
# summarise_warehouse                                                 #
# ------------------------------------------------------------------ #

class TestSummariseWarehouse:
    def test_returns_schema_table_counts(self) -> None:
        con = duckdb.connect(":memory:")
        con.execute('CREATE SCHEMA "s1"')
        con.execute('CREATE TABLE "s1"."t1" (id INTEGER)')
        con.execute('INSERT INTO "s1"."t1" VALUES (1), (2)')
        result = summarise_warehouse(con)
        assert "s1" in result
        assert "t1" in result["s1"]
        assert result["s1"]["t1"] == 2

    def test_empty_warehouse_returns_empty(self) -> None:
        con = duckdb.connect(":memory:")
        result = summarise_warehouse(con)
        assert result == {}


# ------------------------------------------------------------------ #
# load_sample_data: sandbox CSV fallback                              #
# ------------------------------------------------------------------ #

class TestLoadSampleDataSandbox:
    def test_unknown_csv_loaded_into_sandbox(self, tmp_path: Path) -> None:
        """A CSV whose stem isn't in CSV_TO_FQN should land in sandbox.*."""
        # Create a minimal workspace layout that load_sample_data expects.
        csv_dir = tmp_path / "sample_data"
        csv_dir.mkdir()
        (csv_dir / "unknown_widget.csv").write_text("col_a,col_b\n1,hello\n2,world\n")

        # We need catalog.json + schemas dir for workspace_paths to find the root.
        schemas_dir = tmp_path / "schemas"
        schemas_dir.mkdir()
        (schemas_dir / "catalog.json").write_text(
            '{"catalog_version":"0.1","vendor":"test","license_tier":"mock",'
            '"generated_at":"2024-01-01","domains":[],"tables":[]}'
        )

        # Monkey-patch workspace_paths to point at tmp_path.
        import lseg_copilot.data_loader as dl_mod
        orig = dl_mod.workspace_paths

        def patched():
            return {
                "root": tmp_path,
                "sample_data_dir": csv_dir,
                "schemas_dir": schemas_dir,
            }

        dl_mod.workspace_paths = patched  # type: ignore[assignment]
        try:
            con = duckdb.connect(":memory:")
            loaded = load_sample_data(con, catalog=None)
            assert "sandbox.unknown_widget" in loaded
            assert loaded["sandbox.unknown_widget"] == 2
        finally:
            dl_mod.workspace_paths = orig  # type: ignore[assignment]
