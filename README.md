# GS-DATA-PRODUCT — LSEG Knowledge Assistant (Idea Workspace)

> **Personal / ideation workspace only.** All vendor names, schemas, and data herein are
> mock representations modeled on publicly known LSEG / Refinitiv product shapes.
> No proprietary firm code, tokens, or production data is used here. The intent is to
> prototype design patterns that will be hand-ported into the internal Goldman Sachs
> repository.

## What this is

A self-contained playground for designing an enterprise AI assistant ("LSEG Copilot")
that answers data-engineering and analyst questions about the firm's licensed LSEG
datasets, generates SQL/Python against them, and cites the catalog page that backed
each answer.

## Why (the problem)

Inside the bank, ~hundreds of LSEG-sourced tables span Reference Data, Pricing,
Corporate Actions, Fundamentals, I/B/E/S Estimates, ESG, and Tick History. A new
engineer or quant typically loses days to:

1. Finding which table holds the field they need (PermID? RIC? ISIN?).
2. Working out which key joins what (entity PermID vs. instrument PermID vs. quote PermID).
3. Understanding update cadence, point-in-time correctness, and survivorship bias.
4. Writing the SQL without hitting deprecated columns or expired SCD-2 rows.

## Scientific method applied

| Step          | Applied here                                                                                                  |
| ------------- | ------------------------------------------------------------------------------------------------------------- |
| Question      | Can an LLM-backed assistant cut LSEG onboarding time from days to minutes without hallucinating field names?  |
| Background    | LSEG schemas are large but well-structured around PermID. RAG over catalog + Text-to-SQL is industry-proven.  |
| Hypothesis    | RAG-grounded retrieval + constrained SQL generation + citation enforcement > fine-tuned LLM, and is cheaper.  |
| Experiment    | Build the mock catalog (this repo) → index it → measure retrieval P@5 and SQL execution accuracy on a goldset.|
| Analysis      | Track hallucination rate, citation rate, latency, and unanswerable-question detection.                        |
| Conclusion    | Iterate on chunking strategy, schema linking, and dialect adapters.                                           |

## Layout

```
GS-DATA-PRODUCT/
├── README.md                  ← you are here
├── docs/
│   ├── lseg-mock-catalog/     ← realistic mock LSEG documentation
│   │   ├── 02-reference-data/   entity / instrument / quote / exchange / sector
│   │   ├── 03-pricing/          EOD pricing, intraday tick, FX rates
│   │   ├── 04-corporate-actions/
│   │   ├── 05-fundamentals/     Worldscope
│   │   ├── 06-estimates-ibes/   I/B/E/S consensus + detail
│   │   ├── 07-esg/              LSEG ESG (Asset4 lineage)
│   │   ├── 08-fixed-income/     bond terms, credit ratings, yield curves
│   │   ├── 09-derivatives/      futures + options chains
│   │   ├── 10-lipper/           Lipper funds + share classes
│   │   ├── 11-world-check/      KYC/AML (RESTRICTED)
│   │   ├── 99-join-cookbook.md  cross-domain join recipes
│   │   └── 99-data-dictionary.md
│   └── architecture/          ← AI tool design (RAG + Text-to-SQL + eval)
├── schemas/
│   ├── catalog.json           ← manifest: domains + tables + cadences
│   └── *.yaml                 ← per-table column-level schema
├── sample_data/               ← small, internally-consistent CSVs
├── tests/
│   ├── goldset/qa.yaml        ← open-ended Q&A goldset (20 questions)
│   ├── goldset/sql.yaml       ← Text-to-SQL goldset (15 questions)
│   └── fixtures/              ← canonical result-set CSVs per SQL question
└── prototype/                 ← runnable RAG + Text-to-SQL prototype
    └── lseg_copilot/          ← Python package: catalog → indexer → retriever
                                  → planner → reasoner → SQL validator → DuckDB
```

## Where to read next

1. [docs/lseg-mock-catalog/00-overview.md](docs/lseg-mock-catalog/00-overview.md) — vendor product map.
2. [docs/lseg-mock-catalog/01-identifiers-and-entity-model.md](docs/lseg-mock-catalog/01-identifiers-and-entity-model.md) — the PermID hierarchy that everything joins on.
3. [docs/lseg-mock-catalog/99-join-cookbook.md](docs/lseg-mock-catalog/99-join-cookbook.md) — the patterns the AI must memorize.
4. [docs/architecture/01-system-design.md](docs/architecture/01-system-design.md) — how the assistant is built.
5. [tests/goldset/README.md](tests/goldset/README.md) — the frozen eval contract.
6. [prototype/README.md](prototype/README.md) — runnable prototype quickstart.

## Running the prototype

```powershell
cd prototype
python -m pip install -e .[dev]            # install package + pytest
python -m lseg_copilot describe            # catalog summary
python -m lseg_copilot load-data           # sample CSVs → DuckDB
python -m lseg_copilot ask "List Apple's open, close and volume on 2026-05-28."
pytest -q                                  # smoke tests (no LLM key needed)
python -m lseg_copilot eval --kind sql     # SQL goldset against fixtures
```

Optional extras: `pip install -e .[embeddings]` for FAISS + sentence-transformers,
`pip install -e .[llm]` for the OpenAI-compatible client, `pip install -e .[ui]` for
the Streamlit chat UI (`streamlit run lseg_copilot/ui_streamlit.py`).
