# LSEG Copilot — System Design

> **Audience:** the engineer (you) who will hand-port this to the GS internal
> repo. Vendor-name placeholder is `LSEG`, but the design also generalises to
> Bloomberg, MSCI, S&P, etc.

## 1. Problem statement (recap)

A new GS engineer or quant onboarding to LSEG data needs to answer questions like:

- "What's the field for trailing 12-month free cash flow and which table?"
- "Give me a survivorship-bias-free universe of European banks active on 2010-01-01."
- "Show me Apple's last 8 quarters of EPS surprise vs consensus."
- "Why is my P/E ratio negative — did I forget to handle the FX leg?"
- "Generate SQL: top 25 ESG-scored Tech names by 5-year revenue CAGR."

The assistant must answer **with cited catalog references**, and where the
answer is SQL, the SQL must execute correctly against the firm's lake.

## 2. Hypothesis (why this architecture)

| Candidate                               | Why rejected / chosen                                                                                |
| --------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Fine-tune a 70B model on LSEG docs      | ❌ Expensive, slow to update, hallucinates field names, no citations.                                |
| Pure prompt + full catalog in context   | ❌ Catalog is >200k tokens; doesn't fit; expensive per call.                                         |
| RAG over catalog + general LLM          | ✅ Citable, cheap, updates within minutes of a doc edit; baseline strong.                            |
| RAG + Text-to-SQL planner + executor    | ✅✅ Adds the "show me, don't tell me" capability. Validates against schema. Catches join errors.    |
| Agentic loop on top                     | ⚠️ Adds capability but cost + latency + audit complexity; use sparingly for multi-step research.    |

**Chosen:** RAG + Text-to-SQL planner + executor + thin agent loop, with
**citation enforcement** and **schema-grounded SQL validation** as
non-negotiable guardrails.

## 3. High-level architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          USER (chat UI / IDE plugin)                    │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ NL query
                          ┌──────────▼──────────┐
                          │  Orchestrator (API) │
                          │  - intent classifier│
                          │  - routing          │
                          └──┬──────┬──────┬────┘
                             │      │      │
              ┌──────────────┘      │      └─────────────────┐
              │                     │                        │
   ┌──────────▼─────────┐  ┌────────▼────────┐    ┌──────────▼──────────┐
   │ Retrieval (RAG)    │  │ Text-to-SQL     │    │ Tool calls           │
   │  Hybrid search:    │  │  Planner +      │    │ - lineage lookup    │
   │  - BM25 over MD    │  │  Schema linker  │    │ - PII / entitlement │
   │  - Vector over MD  │  │  Validator      │    │ - cost estimator    │
   │  - Symbol search   │  │  Executor (RO)  │    └─────────────────────┘
   │    over catalog.json│ │                 │
   └──────────┬─────────┘  └────────┬────────┘
              │                     │
              └──────────┬──────────┘
                         │
                ┌────────▼─────────┐
                │   Reasoner LLM   │
                │  (cited answer)  │
                └────────┬─────────┘
                         │
                ┌────────▼─────────┐
                │ Guardrails       │
                │ - citations req. │
                │ - PII redact     │
                │ - SQL lint       │
                │ - "I don't know" │
                └────────┬─────────┘
                         │ Final answer + citations + (optional) SQL + results
                         ▼
                       USER
```

## 4. Components

### 4.1 Knowledge corpus (input to indexing)

What we index:

1. **Catalog markdown** — `docs/lseg-mock-catalog/**/*.md` (this repo).
2. **Machine-readable schemas** — `schemas/*.yaml` and `schemas/catalog.json`.
3. **Internal runbooks** (in prod: SRE pages, FAQ tickets, post-mortems).
4. **Selected sample queries** — every "Sample queries" section becomes its
   own retrieval document.

Each chunk carries metadata:
```yaml
chunk_metadata:
  table_fqn:          lseg_dss.eod_pricing
  domain:             pricing
  section:            "5. Adjusted-price methodology"
  doc_path:           docs/lseg-mock-catalog/03-pricing/EOD_PRICING.md
  doc_anchor:         "#5-adjusted-price-methodology"
  chunk_type:         prose | schema | join_pattern | sample_query
  catalog_version:    "2026.05.r2"
  last_updated:       2026-05-28
```

### 4.2 Indexing pipeline

| Step                          | Tool / method (prototype → prod)                                          |
| ----------------------------- | ------------------------------------------------------------------------- |
| Markdown ingestion            | Python parser → split on headings, keep code blocks intact.               |
| Chunking                      | ~400-token target with 60-token overlap; never split a sample query.     |
| Embeddings                    | `text-embedding-3-large` (prototype) → in-firm embedding service (prod).  |
| Vector store                  | FAISS local (prototype) → Pinecone / pgvector / OpenSearch k-NN (prod).   |
| Keyword index                 | OpenSearch BM25 over the same chunks (hybrid retrieval).                  |
| Symbol index                  | Trigram / token index over column names from `catalog.json` for exact-match field lookup. |

### 4.3 Retrieval

Hybrid retrieval, then re-rank:

1. Run BM25 + vector search in parallel; combine via reciprocal rank fusion.
2. **Boost** any chunk whose `table_fqn` matches a column name explicitly
   mentioned in the user query.
3. **Boost** the join cookbook + data dictionary if the query implies
   cross-table semantics (synonym list).
4. Re-rank top 50 → top 10 with a cross-encoder.

### 4.4 Text-to-SQL planner

Pipeline (each step is a separate LLM call or deterministic function):

1. **Schema linker** — given the user question and retrieved chunks, identify
   the candidate tables and columns. Output a constrained `{tables, columns, joins}` plan.
2. **Identifier resolution** — if the user mentions a RIC/ISIN/ticker/company
   name, resolve to the right PermID using the rules in
   [01-identifiers-and-entity-model.md](../lseg-mock-catalog/01-identifiers-and-entity-model.md).
3. **PIT decision** — bitemporal vs SCD-2 vs static; insert the right
   predicates (`is_current = TRUE` only when explicitly "current"; PIT band otherwise).
4. **SQL generation** — write the SQL in the lake's dialect (Trino / Spark
   SQL / Snowflake — selectable).
5. **Static validation** — parse with `sqlglot`, check every column exists in
   the YAML schema, every join key is on the declared `joins` list.
6. **Dry-run** — `EXPLAIN` against the lake to catch partition-pruning issues.
7. **(optional) Execute** with a strict read-only role; row caps + cost caps
   enforced.

### 4.5 Reasoner / responder LLM

- Receives: user question, top-k chunks, optional SQL result preview, lineage info.
- Produces: a Markdown answer with **inline citations** of the form
  `[ENTITY_MASTER §3](docs/lseg-mock-catalog/02-reference-data/ENTITY_MASTER.md#3-entity_status_code-enumeration)`.
- System prompt enforces: "Every factual claim about LSEG data MUST cite at
  least one catalog chunk. If you cannot, reply with the explicit `UNKNOWN`
  tag and request more context."

### 4.6 Guardrails

| Guardrail            | Mechanism                                                                   |
| -------------------- | --------------------------------------------------------------------------- |
| Citation enforcement | Post-process the response; reject if any sentence with a column / table reference lacks a citation. |
| PII / entitlement    | Strip `[RESTRICTED]` columns from results for users without entitlement.    |
| Cost cap             | Estimator predicts scanned bytes; abort if > threshold; require user confirm. |
| Hallucination check  | Every column / table mentioned in the response must appear in `catalog.json`. |
| Out-of-scope         | If retrieval top score < threshold, refuse with "I don't have catalog coverage for that." |
| Prompt injection     | Strip any "ignore previous instructions" patterns from retrieved chunks; defensive system prompt. |

## 5. Data flow for the three canonical query types

### 5.1 "Where is field X?"

```
NL → retrieve (boost on field-name symbol index) → answer with table + section + citation.
No SQL generated.
```

### 5.2 "Generate SQL: …"

```
NL → retrieve (top 8 chunks across reference + target domain)
   → schema link
   → resolve identifiers
   → choose PIT mode
   → generate SQL
   → static-validate
   → optionally execute (with cost cap)
   → respond with explanation + cited tables + SQL fenced block + (optional) result preview.
```

### 5.3 "Explain why my query is wrong"

```
NL + user's SQL → parse with sqlglot
                → diff against schema (unknown col? wrong type? join key wrong?)
                → retrieve relevant section of join cookbook
                → respond with annotated correction.
```

## 6. UX surfaces

- **Chat panel** in the firm's internal Copilot UI.
- **VS Code extension** that lights up on `.sql` files; gives schema/IntelliSense + “explain my query”.
- **Slack bot** in `#mde-help` for one-off Q&A; uses a shared context per thread.

## 7. Open questions (to address before porting)

1. Which lake dialect(s) must Text-to-SQL generate? (likely Trino + Spark SQL.)
2. Are catalog updates push or pull? Index rebuild SLA?
3. Is there an existing internal entitlement service to call, or do we need to model row-level security ourselves?
4. Do we need conversational memory across sessions, or per-thread only? (Privacy implications.)
5. What's the on-call rotation if the assistant gives a wrong SQL that lands a bad trade signal? (Audit log + answer-pinning is essential.)
