"""Static SQL validator. Uses sqlglot to:
  1. Parse to AST (DuckDB dialect).
  2. Verify every referenced table.column exists in the catalog.
  3. Refuse DML/DDL (only SELECT / WITH).
  4. Inject a row-cap (LIMIT) if missing.
  5. Heuristic currency-consistency check.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from .catalog import Catalog


@dataclass
class ValidationResult:
    sql: str  # possibly rewritten
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_DEFAULT_ROW_CAP = 1000


def validate_sql(
    sql: str,
    catalog: Catalog,
    *,
    row_cap: int = _DEFAULT_ROW_CAP,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except Exception as exc:  # sqlglot.errors.ParseError typically
        return ValidationResult(sql=sql, ok=False, errors=[f"Parse error: {exc}"])

    if len(statements) != 1:
        return ValidationResult(
            sql=sql, ok=False, errors=["Multiple statements not allowed."]
        )
    tree = statements[0]

    # Allow only SELECT / CTE / DESCRIBE / SHOW. UNION is blocked to prevent
    # bypassing entitlement checks by appending "UNION SELECT * FROM restricted".
    if not isinstance(tree, (exp.Select, exp.With, exp.Describe, exp.Show)):
        return ValidationResult(
            sql=sql,
            ok=False,
            errors=[f"Disallowed statement type: {type(tree).__name__}"],
        )

    # ----- Validate tables -----
    table_aliases: dict[str, str] = {}  # alias -> fqn
    catalog_tables = {t.fqn.lower(): t for t in catalog.tables}
    cte_aliases = {cte.alias for cte in tree.find_all(exp.CTE) if cte.alias}
    for table_expr in tree.find_all(exp.Table):
        db = (table_expr.args.get("db") or exp.to_identifier("")).name
        name = table_expr.name
        if not db and name in cte_aliases:
            continue
        fqn = f"{db}.{name}" if db else name
        alias = table_expr.alias_or_name
        spec = catalog_tables.get(fqn.lower())
        if not spec:
            errors.append(f"Unknown table referenced: `{fqn}`")
            continue
        table_aliases[alias] = spec.fqn

    if not table_aliases and not errors:
        warnings.append("Query references no catalog tables — review carefully.")

    # ----- Validate columns -----
    all_columns_in_query = list(tree.find_all(exp.Column))
    for col in all_columns_in_query:
        col_name = col.name
        table_ref = col.table
        if table_ref:
            fqn = table_aliases.get(table_ref)
            if not fqn:
                # Maybe the user wrote a real db.table prefix.
                fqn = next(
                    (a for a in table_aliases.values() if a.endswith(f".{table_ref}")),
                    None,
                )
            if fqn:
                spec = catalog.get_table(fqn)
                if spec and col_name not in {"*"} and col_name not in spec.column_names:
                    errors.append(
                        f"Column `{col_name}` not in `{fqn}` "
                        f"(known: {', '.join(spec.column_names[:8])}...)"
                    )

    # ----- Currency consistency check -----
    text_lower = sql.lower()
    if "revenue" in text_lower and "close_price" in text_lower and "fx_rates_eod" not in text_lower:
        warnings.append(
            "Possible currency mix: revenue and close_price referenced without an FX join."
        )

    # ----- Row-cap injection -----
    rewritten_sql = sql.strip().rstrip(";")
    if isinstance(tree, exp.Select) and not tree.args.get("limit"):
        rewritten_sql = f"{rewritten_sql}\nLIMIT {row_cap}"

    ok = not errors
    return ValidationResult(sql=rewritten_sql, ok=ok, errors=errors, warnings=warnings)
