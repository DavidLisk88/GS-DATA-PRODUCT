# RAG Pipeline — Detail

## 1. Why hybrid (BM25 + vector) and not just vector

Vector retrieval shines on conceptual queries ("how do I avoid survivorship
bias?") but loses to BM25 on exact-string queries ("what table has
`close_adj_price`?"). For a domain as field-name-heavy as ours, missing
exact-string matches is a deal-breaker. We always run both and fuse.

We add a third retriever — a **symbol index** over column names extracted from
`schemas/*.yaml`. When the user types a token that exactly matches a known
column, that chunk gets a hard boost (not just a soft rerank).

## 2. Chunking policy

| Chunk type      | Strategy                                                       | Rationale                                            |
| --------------- | -------------------------------------------------------------- | ---------------------------------------------------- |
| Prose section   | Split on `##` headings; keep ~400 tokens with 60 overlap.      | Preserves heading context for citation anchors.      |
| Schema table    | Each schema column-row group of ~10 columns becomes one chunk. | Field-name retrieval finds the right group.          |
| Sample query    | Each SQL block + the paragraph above it = one indivisible chunk. | Don't split code from its explanation.             |
| Enum / glossary | Each enumeration table is one chunk.                           | Status codes resolve cleanly.                        |
| Join recipe     | Each numbered recipe in the cookbook = one chunk.              | Recipes are independently useful.                    |

Metadata on every chunk (see [system design §4.1](01-system-design.md#41-knowledge-corpus-input-to-indexing)).

## 3. Embedding choice & re-indexing

- **Prototype embedder:** `text-embedding-3-large` (3072 dims). Good general
  semantic quality; consistent with downstream LLMs.
- **Production embedder:** in-firm hosted model behind the firm's gateway
  (typically a fine-tuned BGE-large or in-house). Same dimensionality so we
  can swap without re-indexing if needed.
- **Re-index trigger:** any commit to `docs/lseg-mock-catalog/**` or
  `schemas/**` triggers a partial re-index of the affected chunks within 5 min.
- **Full re-index:** weekly, off-hours, to catch metadata drift.

## 4. Re-ranking

After fusion of BM25 + vector + symbol:

1. Take top 50.
2. Cross-encoder rerank against the query (prototype: `bge-reranker-v2-m3`;
   prod: in-firm equivalent).
3. Truncate to top 10 (or fewer if score gap is large).
4. Diversify by `table_fqn` so a single huge doc can't dominate the answer.

## 5. Query understanding (preprocessing)

Before retrieval, an LLM-light classifier ($/k tokens) does:

| Output                    | Used for                                                             |
| ------------------------- | -------------------------------------------------------------------- |
| `intent`                  | `lookup_field` / `generate_sql` / `explain_concept` / `debug_query`. |
| `mentioned_identifiers`   | RIC, ISIN, CUSIP, ticker, company-name candidates.                   |
| `mentioned_domains`       | pricing / fundamentals / etc.                                        |
| `requires_pit`            | true if query references a historical date.                          |
| `needs_cross_domain`      | true if query mentions ≥2 domains; promotes join-cookbook chunks.    |

Outputs are passed to the orchestrator as routing hints.

## 6. Negative examples / hard negatives

To make the cross-encoder discriminating, we build a training set of
**look-alike-but-wrong** pairs from our own catalog:

- Query: "where's free cash flow"
  Positive: `company_fundamentals.free_cash_flow` chunk.
  Hard negative: `eod_pricing.close_price` (totally unrelated but mentions
  "free float" elsewhere on the same page).

This is generated automatically from `catalog.json` and is rerun weekly.

## 7. Citation extraction

Every retrieved chunk emits a citation handle:

```
[<table_fqn> §<section>](<doc_path>#<doc_anchor>)
```

The reasoner LLM is forced (via JSON-mode + post-validation) to attach at
least one citation handle to every paragraph that makes a claim about LSEG
data. If it cannot, the response is rejected and regenerated with a more
explicit "must cite" instruction.

## 8. Evaluation hooks

Each retrieval call logs:

- `query_id`, `query_text`, `intent`
- top-k chunk IDs, scores, fusion weights
- which chunks the LLM ultimately cited
- whether the user thumbs-upped / corrected the answer

This becomes the goldset (see [04-evaluation.md](04-evaluation.md)).
