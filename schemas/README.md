# LSEG Mock Catalog — Machine-readable schemas

Each YAML file in this directory is the canonical, machine-readable definition
of one physical table documented in `docs/lseg-mock-catalog/`. The AI assistant
uses these for:

1. **Retrieval grounding** — chunked into the vector DB alongside the prose docs.
2. **Schema linking** for Text-to-SQL — the planner sees field names and types
   without having to parse markdown.
3. **Validation** — when the generated SQL references a column, we check the
   schema before sending it for execution.

The `catalog.json` file is the master manifest enumerating every table and
where its YAML lives.

Conventions in the YAML:

- `pii_level` — one of `none`, `restricted`, `confidential`.
- `pk` — list of columns forming the primary key.
- `partitioned_by` / `clustered_by` — physical-layout hints.
- `joins` — declared foreign-key-style join paths the planner can rely on.
- `update_cadence` — free-form, e.g. `daily_06_NYT`, `streaming`, `filing_driven`.
- `temporal_model` — one of `static`, `scd_type_2`, `bitemporal`, `point_in_time`.
