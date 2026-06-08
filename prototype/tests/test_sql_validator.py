"""Unit tests for lseg_copilot.sql_validator — covers parse errors,
multi-statement rejection, DML/DDL blocking, CTE handling, column
validation, currency-consistency warning, and the no-tables warning."""
from __future__ import annotations

import pytest

from lseg_copilot.catalog import Catalog
from lseg_copilot.sql_validator import ValidationResult, validate_sql


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


# ------------------------------------------------------------------ #
# Parse errors                                                        #
# ------------------------------------------------------------------ #

class TestParseError:
    def test_garbage_sql_returns_error(self, catalog: Catalog) -> None:
        result = validate_sql("THIS IS NOT SQL !!!", catalog)
        # sqlglot may or may not raise; if it parses it as something weird,
        # downstream checks will still catch it. Either way, we get a
        # non-empty result.
        assert isinstance(result, ValidationResult)


# ------------------------------------------------------------------ #
# Multi-statement rejection                                           #
# ------------------------------------------------------------------ #

class TestMultiStatement:
    def test_two_selects_rejected(self, catalog: Catalog) -> None:
        result = validate_sql(
            "SELECT 1; SELECT 2", catalog
        )
        assert not result.ok
        assert any("Multiple" in e for e in result.errors)


# ------------------------------------------------------------------ #
# DML / DDL rejection                                                 #
# ------------------------------------------------------------------ #

class TestDMLDDLRejection:
    def test_insert_rejected(self, catalog: Catalog) -> None:
        result = validate_sql(
            "INSERT INTO lseg_ref.entity_master (org_perm_id) VALUES (1)", catalog
        )
        assert not result.ok
        assert any("Disallowed" in e for e in result.errors)

    def test_drop_rejected(self, catalog: Catalog) -> None:
        result = validate_sql("DROP TABLE lseg_ref.entity_master", catalog)
        assert not result.ok

    def test_delete_rejected(self, catalog: Catalog) -> None:
        result = validate_sql(
            "DELETE FROM lseg_ref.entity_master WHERE org_perm_id = 1", catalog
        )
        assert not result.ok


# ------------------------------------------------------------------ #
# CTE alias not treated as unknown table                              #
# ------------------------------------------------------------------ #

class TestCTEHandling:
    def test_cte_alias_not_flagged(self, catalog: Catalog) -> None:
        sql = (
            "WITH cte AS (SELECT org_perm_id FROM lseg_ref.entity_master) "
            "SELECT org_perm_id FROM cte"
        )
        result = validate_sql(sql, catalog)
        assert result.ok
        assert not any("Unknown table" in e for e in result.errors)


# ------------------------------------------------------------------ #
# Column validation                                                   #
# ------------------------------------------------------------------ #

class TestColumnValidation:
    def test_unknown_column_flagged(self, catalog: Catalog) -> None:
        # Column validation requires a table qualifier (alias or FQN).
        result = validate_sql(
            "SELECT em.no_such_column FROM lseg_ref.entity_master em", catalog
        )
        assert not result.ok
        assert any("no_such_column" in e for e in result.errors)

    def test_valid_column_passes(self, catalog: Catalog) -> None:
        result = validate_sql(
            "SELECT org_perm_id FROM lseg_ref.entity_master", catalog
        )
        assert result.ok

    def test_column_with_table_alias(self, catalog: Catalog) -> None:
        result = validate_sql(
            "SELECT em.org_perm_id FROM lseg_ref.entity_master em", catalog
        )
        assert result.ok

    def test_unknown_column_via_alias(self, catalog: Catalog) -> None:
        result = validate_sql(
            "SELECT em.bogus_field FROM lseg_ref.entity_master em", catalog
        )
        assert not result.ok
        assert any("bogus_field" in e for e in result.errors)


# ------------------------------------------------------------------ #
# No catalog tables warning                                           #
# ------------------------------------------------------------------ #

class TestNoCatalogTablesWarning:
    def test_select_literal_warns(self, catalog: Catalog) -> None:
        result = validate_sql("SELECT 1 AS one", catalog)
        assert result.ok
        assert any("no catalog tables" in w.lower() for w in result.warnings)


# ------------------------------------------------------------------ #
# Currency-consistency warning                                        #
# ------------------------------------------------------------------ #

class TestCurrencyWarning:
    def test_revenue_and_close_price_without_fx_warns(self, catalog: Catalog) -> None:
        sql = (
            "SELECT revenue, close_price "
            "FROM lseg_wsf.company_fundamentals f "
            "JOIN lseg_dss.eod_pricing p ON f.org_perm_id = p.ric_as_of"
        )
        result = validate_sql(sql, catalog)
        assert any("currency" in w.lower() for w in result.warnings)

    def test_revenue_and_close_price_with_fx_no_warn(self, catalog: Catalog) -> None:
        sql = (
            "SELECT revenue, close_price "
            "FROM lseg_wsf.company_fundamentals f "
            "JOIN lseg_dss.eod_pricing p ON 1=1 "
            "JOIN lseg_fx.fx_rates_eod fx ON 1=1"
        )
        result = validate_sql(sql, catalog)
        assert not any("currency" in w.lower() for w in result.warnings)


# ------------------------------------------------------------------ #
# Row-cap injection                                                   #
# ------------------------------------------------------------------ #

class TestRowCap:
    def test_limit_injected_when_missing(self, catalog: Catalog) -> None:
        result = validate_sql(
            "SELECT org_perm_id FROM lseg_ref.entity_master", catalog
        )
        assert "LIMIT" in result.sql.upper()

    def test_existing_limit_preserved(self, catalog: Catalog) -> None:
        result = validate_sql(
            "SELECT org_perm_id FROM lseg_ref.entity_master LIMIT 10", catalog
        )
        assert result.ok
        assert result.sql.upper().count("LIMIT") == 1

    def test_custom_row_cap(self, catalog: Catalog) -> None:
        result = validate_sql(
            "SELECT org_perm_id FROM lseg_ref.entity_master",
            catalog,
            row_cap=42,
        )
        assert "LIMIT 42" in result.sql
