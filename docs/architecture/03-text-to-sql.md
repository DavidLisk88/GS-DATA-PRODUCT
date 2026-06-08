# Text-to-SQL — Detail

The single highest-risk part of the assistant. A wrong fact in a chat reply
is recoverable; a wrong SQL silently produces bad data for a trading desk.
We treat SQL generation as a **constrained, validated, dialect-aware
compilation problem**, not just an LLM prompt.

## 1. Pipeline (deterministic where possible)

```
NL question
    │
    ▼
Schema linker (LLM) ── { tables, columns, joins }
    │                                  │
    │                                  ▼
    │                         Schema validator (deterministic)
    │                          - tables exist in catalog.json?
    │                          - columns exist in YAML?
    │                          - joins on declared keys?
    │                          - cardinality consistent?
    ▼
Identifier resolver (deterministic + small LLM)
    - "Apple" / "AAPL" / "AAPL.OQ" / ISIN → org_perm_id, instrument_perm_id, quote_perm_id
    │
    ▼
Temporal-model resolver (deterministic)
    - For each table touched, pick PIT mode based on user intent:
        current-snapshot | as-of-date | full-history
    - Inject the corresponding predicates
    │
    ▼
SQL generator (LLM, dialect-aware)
    - Receives: linked plan + resolved IDs + PIT directives + sample queries
    - Output: a single SELECT (no DML, no DDL)
    │
    ▼
Static validation (deterministic)
    - sqlglot parse
    - column-existence recheck
    - join-key recheck
    - currency-consistency check (don't divide JPY by USD)
    - cost estimator (lookup partition pruning)
    │
    ▼
Optional execute (read-only, capped)
    - row limit (default 10_000)
    - bytes-scanned cap
    - timeout
    - PII-aware: rewrite SELECT * to skip [RESTRICTED] cols if user unentitled
    │
    ▼
Result preview + cited explanation
```

## 2. The schema-linker prompt (sketch)

```
SYSTEM: You are a schema linker for the LSEG catalog. You receive
        a user question and a list of candidate tables. Output JSON:
        {
          "tables": [<fqn>, ...],
          "columns_by_table": { "<fqn>": [<col>, ...] },
          "joins": [{"left":"<fqn>","right":"<fqn>","on":"..."}, ...],
          "pit_mode": "current"|"as_of"|"history",
          "as_of_date": "<ISO>"|null,
          "currency_target_iso": "<ISO>"|null
        }
        Never invent columns. If a column would be needed but doesn't exist,
        emit it under "missing_columns" instead.

USER:   <question>
CONTEXT:
        <top-k retrieved chunks, schema YAML excerpts>
```

## 3. Identifier resolution rules (deterministic where possible)

```
input: a free-form token from the user
  if token matches r'^[A-Z]{1,5}\.[A-Z]{1,4}$'   → treat as RIC, resolve via quote_master
  elif r'^[A-Z]{2}[A-Z0-9]{9}\d$'                 → ISIN, resolve via instrument_master
  elif r'^[A-Z0-9]{8}\d$'                         → CUSIP, resolve via instrument_master
  elif r'^[A-Z0-9]{18}\d{2}$'                     → LEI, resolve via entity_master
  elif r'^\d{10}$'                                → assume PermID, look up which type
  else                                            → fuzzy company-name match against entity_master
```

Resolution table tied directly into `catalog.json` joins.

## 4. PIT mode selection heuristic

| User phrasing                                | `pit_mode`        | Predicate injected                                                          |
| -------------------------------------------- | ----------------- | --------------------------------------------------------------------------- |
| "today" / "current" / "now" / no date hint   | `current`         | `is_current = TRUE` (or `is_current_version = TRUE` for bitemporal).        |
| "as of YYYY-MM-DD"                           | `as_of`           | `:as_of_ts BETWEEN valid_from_ts AND valid_to_ts` everywhere.               |
| "over time" / "history" / range              | `history`         | No PIT filter; let the data flow with band joins.                           |
| "earnings surprise" / "what we knew on …"    | `as_of`           | Additional `valid_to_ts > :as_of_ts` for the fundamentals/estimates side.   |

## 5. Currency-consistency check

A class of silent bugs: dividing a `JPY`-denominated revenue by a
`USD`-denominated share price. The static validator walks every arithmetic
expression in the parse tree and, where a column is paired with a
`*_currency_iso` or `trading_currency_iso` column in its schema, verifies
that both sides of the operator share a currency tag. If not, abort with a
helpful error.

## 6. Dialect adapters

`sqlglot` provides round-trip transpilation across Trino, Spark SQL,
Snowflake, DuckDB. We generate canonical Trino, then transpile to the user's
selected dialect at the end. Adapter quirks:

| Concern              | Trino                              | Spark SQL              | Snowflake              |
| -------------------- | ---------------------------------- | ---------------------- | ---------------------- |
| Window QUALIFY       | Yes                                | Workaround via subquery | Yes                   |
| TIMESTAMP precision  | `TIMESTAMP(6)`                     | microseconds default   | `TIMESTAMP_NTZ(6)`     |
| String aggregation   | `array_agg`                        | `collect_list`         | `array_agg`            |
| Date arithmetic      | `INTERVAL '1' DAY`                 | `INTERVAL 1 DAYS`      | `DATEADD(DAY, 1, ...)` |

## 7. What we DON'T let the LLM do

| Banned                                | Reason                                  |
| ------------------------------------- | --------------------------------------- |
| `INSERT`, `UPDATE`, `DELETE`, `MERGE` | RO assistant only.                      |
| `CREATE`, `DROP`, `ALTER`             | RO assistant only.                      |
| `SELECT *` on tick tables             | Would scan TB.                          |
| Cross-database joins outside `lseg_*` | Out of catalog scope; refuse.           |
| User-supplied raw SQL injection       | Sanitise before storing in audit log.   |
| Calls to vendor APIs                  | Different licensing surface; out of scope. |
