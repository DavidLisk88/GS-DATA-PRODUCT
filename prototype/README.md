# Prototype — `lseg_copilot`

A runnable, **end-to-end** prototype of the LSEG Data Copilot. It reads the
mock catalog under `../docs/lseg-mock-catalog`, the schemas under
`../schemas/`, and the sample CSVs under `../sample_data/`, and exposes:

- a CLI (`python -m lseg_copilot ...`)
- a Streamlit chat UI (`streamlit run lseg_copilot/ui_streamlit.py`)
- a smoke `pytest` suite that runs without any LLM key

The prototype is intentionally *embedding-optional*. By default it runs
**lexical-only** (BM25 + symbol-boost) so it works with no network access.
Install the `embeddings` extra to enable the dense FAISS index.

## Quickstart

```powershell
cd prototype
python -m pip install -e .

# Optional extras
python -m pip install -e .[embeddings]   # FAISS + sentence-transformers
python -m pip install -e .[llm]          # OpenAI client
python -m pip install -e .[ui]           # Streamlit
python -m pip install -e .[dev]          # pytest

# Sanity check
python -m lseg_copilot describe
python -m lseg_copilot load-data
python -m lseg_copilot index --no-embed
python -m lseg_copilot ask "List Apple's open, close and volume on 2026-05-28."

# Smoke tests
pytest -q

# Run a subset of the SQL goldset
python -m lseg_copilot eval --kind sql --max 5
```

## Architecture (matches `../docs/architecture/`)

```
┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────┐  ┌──────────┐
│  Catalog   │→│  Indexer   │→│ Retriever  │→│   Planner    │→│ Reasoner │
│ (YAML+JSON)│   │ BM25+FAISS │   │ RRF+symbol │   │ ID/PIT/ents  │   │ Stub/LLM │
└────────────┘  └────────────┘  └────────────┘  └──────────────┘  └────┬─────┘
                                                                       │
                                                            ┌──────────▼─────────┐
                                                            │ SQL Validator       │
                                                            │ (sqlglot + checks)  │
                                                            └──────────┬─────────┘
                                                                       │
                                                                  ┌────▼────┐
                                                                  │ DuckDB  │
                                                                  └─────────┘
```

## Module map

| Module                       | Purpose                                                                 |
| ---------------------------- | ----------------------------------------------------------------------- |
| `paths.py`                   | Locate the workspace root regardless of CWD.                            |
| `catalog.py`                 | Pydantic models + `Catalog.load()` (reads `catalog.json` + YAMLs).      |
| `data_loader.py`             | Mount `sample_data/*.csv` into DuckDB under the right `schema.table`.   |
| `indexer.py`                 | Chunk markdown + YAML, build BM25 (always) + FAISS (if extras).         |
| `retriever.py`               | Hybrid RRF fusion + symbol boost from catalog.                          |
| `planner.py`                 | ID resolution + PIT clauses + entitlement refusal + currency check.     |
| `sql_validator.py`           | `sqlglot` parse, table/column existence, row-cap injection.             |
| `reasoner.py`                | Stub canned SQL for goldset IDs, plus optional OpenAI-compatible LLM.   |
| `cli.py` / `__main__.py`     | `describe`, `load-data`, `index`, `ask`, `eval`.                        |
| `ui_streamlit.py`            | Optional chat UI.                                                       |
| `tests/test_smoke.py`        | Pytest smoke tests (no LLM, no network).                                |

## Why two reasoners?

- `StubReasoner` makes the prototype demo-able *without an API key*. It
  uses pre-baked SQL for the goldset IDs and returns citation summaries
  for free-form questions. Good enough for a hand-off demo.
- `LLMReasoner` calls any OpenAI-compatible chat endpoint. It is forced
  to respond as a JSON object with `{answer, citations, sql}` and is
  pinned to a citation-only system prompt to keep it honest.

## Hand-off to the GS workspace

When you port this internally you'll need to swap:

- `data_loader.py` → connect to Trino/Snowflake/Spark and target your real
  schemas (the `CSV_TO_FQN` map maps cleanly to real `schema.table`).
- `reasoner.py` → point `OpenAIChatClient` at the firm's hosted endpoint
  (or implement a new `LLMClient` for whatever gateway you have).
- `paths.py` → optional: replace the workspace-root sniff with a config var.
- Add an entitlement provider that returns the user's groups from the
  internal IAM service instead of CLI flags.

