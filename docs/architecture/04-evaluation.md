# Evaluation — How we'll know it works

Scientific method, applied:

| Step          | Evaluation analogue                                                              |
| ------------- | --------------------------------------------------------------------------------- |
| Hypothesis    | RAG + Text-to-SQL hybrid achieves > 85% answer accuracy with > 95% citation rate. |
| Experiment    | Hand-curated goldset of 250+ realistic GS analyst/engineer questions.             |
| Measurement   | Multi-dimensional rubric below.                                                   |
| Analysis      | Per-domain breakdown; failure clustering; regression on every release.            |
| Iterate       | Adjust chunking / retrieval weights / planner prompts; never the schemas to fit.  |

## 1. The goldset (build before launch)

Two flavours:

### 1.1 Open-ended Q&A (retrieval + reasoner)

Each row:
```yaml
- id: Q-0001
  question: "What's the difference between is_primary_security and is_primary_listing?"
  expected_tables: [lseg_ref.instrument_master, lseg_ref.quote_master]
  expected_citation_anchors:
    - docs/lseg-mock-catalog/02-reference-data/INSTRUMENT_MASTER.md#e-known-quirks
  answer_must_mention: ["different editorial teams", "primary_security is instrument-level"]
  intent: explain_concept
```

### 1.2 Text-to-SQL (execution-correct)

Each row:
```yaml
- id: SQ-0001
  question: "Give me Apple's closing price on 2026-05-28 in USD."
  expected_tables: [lseg_ref.entity_master, lseg_ref.instrument_master, lseg_ref.quote_master, lseg_dss.eod_pricing]
  expected_result_csv: tests/fixtures/SQ-0001.csv
  acceptance: result_equivalent  # row sets equal modulo ordering
```

Goldset must include adversarial cases:

- Historical RIC strings (e.g. `FB.OQ`) that require `ric_history`.
- Restated fundamentals (PIT vs as-restated).
- Currency mismatch traps (JPY revenue, USD prices).
- Survivorship-bias-prone questions ("Tech names in 2010").
- Voluntary corporate action elections.

## 2. Metrics

### 2.1 Retrieval

| Metric               | Definition                                                       | Target  |
| -------------------- | ---------------------------------------------------------------- | ------- |
| Recall@10            | Fraction of goldset questions where ≥1 expected chunk in top 10. | > 95%   |
| Precision@5          | Avg fraction of top-5 chunks that are relevant.                  | > 60%   |
| MRR                  | Mean reciprocal rank of first expected chunk.                    | > 0.7   |
| Coverage (no-answer) | Refusal rate on out-of-catalog questions.                        | > 90%   |

### 2.2 Reasoner

| Metric                      | Definition                                                  | Target |
| --------------------------- | ----------------------------------------------------------- | ------ |
| Answer correctness (LLM-as-judge) | Rubric-scored 0-3 against expected answer.            | > 2.5  |
| Citation rate               | % of fact-claiming sentences with ≥1 citation.              | > 95%  |
| Hallucinated-symbol rate    | % responses mentioning columns absent from `catalog.json`.  | < 0.5% |
| Refusal-on-out-of-scope     | % of OOS questions correctly refused.                       | > 90%  |

### 2.3 Text-to-SQL

| Metric                       | Definition                                                  | Target |
| ---------------------------- | ----------------------------------------------------------- | ------ |
| Static validity              | % generated SQL that parses + column-checks.                | > 99%  |
| Execution accuracy           | % whose result set equals the expected fixture.             | > 85%  |
| PIT-correctness              | % that uses correct temporal predicates per question.       | > 90%  |
| Currency-safety              | % that pass the currency-consistency check.                 | 100%   |
| Cost compliance              | % staying under the bytes-scanned cap.                      | > 99%  |

### 2.4 End-to-end UX

- p95 latency (chat-style answer): < 5 s.
- p95 latency (with SQL execution): < 15 s.
- Thumbs-up rate from beta users: > 70%.

## 3. Continuous evaluation

CI on every PR to this repo:

```
pre-merge → run goldset → fail PR if any tier-1 metric regresses > 2 pp.
```

Production:

- Daily sample of 1% of live queries scored by LLM-judge + human-spot-check.
- Weekly failure-cluster review (we look at the bottom-decile interactions).
- Quarterly "red team" exercise: an internal team writes questions specifically
  designed to break the assistant; failures become goldset additions.

## 4. Anti-goals (things we explicitly do NOT optimise for)

- **Conversation length** — we'd rather refuse than guess. Shorter, cited
  refusals beat eloquent hallucinations.
- **Generative creativity** — no jokes, no analogies in production answers.
- **Catalog-extension via LLM** — the LLM never proposes "maybe there's a
  table called X"; only humans add catalog rows.
