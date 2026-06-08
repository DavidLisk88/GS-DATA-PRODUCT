# Evaluation goldset

This directory holds the **frozen evaluation set** for the LSEG Data Copilot.
It is the contract between the AI tool and the data team: any model change,
prompt change, retriever change, or schema change must be measured against
this set before promotion to production.

## Files

| File | Purpose | Scored by |
| --- | --- | --- |
| [`qa.yaml`](qa.yaml) | Open-ended questions answered from catalog markdown + LLM. | Citation recall, must-mention coverage, must-NOT-mention guard, refusal correctness. |
| [`sql.yaml`](sql.yaml) | Text-to-SQL questions whose answers come from executing SQL. | Schema linking F1, identifier-resolution accuracy, result-set equality against fixtures, PIT correctness, currency consistency. |
| [`../fixtures/`](../fixtures/) | Canonical CSV result-sets that `sql.yaml` rows reference. | Compared row-by-row (set semantics where ordering not stated). |

## Question types (mirrors `docs/architecture/04-evaluation.md`)

1. **Definitional / catalog lookup** — e.g. "What is `quote_perm_id`?". Pure RAG; checks citation discipline.
2. **Schema linking** — "Which table holds dividend amounts in their declared currency?"; checks that the planner picks `lseg_ca.corporate_action_terms`, not `dividend` columns elsewhere.
3. **Identifier resolution** — historical RIC ("FB.OQ on 2021-06-30") must roll forward to `META.OQ`.
4. **Bitemporal / PIT** — "Apple Q1-FY2023 revenue *as known on 2023-02-10*" must respect `valid_to_ts` cut-off and not return the later restatement.
5. **Currency consistency** — "JPY revenue × USD price" question must be refused or auto-converted via FX, never silently multiplied.
6. **Survivorship-bias** — historical universe construction must include now-delisted entities.
7. **Corporate-action chain** — split + name change + delisting on the same instrument.
8. **Entitlement refusal** — World-Check question without `LSEG_WC_VIEWER` must refuse, *not* hallucinate.
9. **Cross-domain join** — bond rating change vs. equity option IV move (FI + DRV) for the same issuer.
10. **Out-of-catalog** — "What was Apple's Q3 sell-through in Vietnam?" — must refuse: not in this catalog.

## Scoring

```text
overall_score = 0.35 * citation_recall
              + 0.20 * must_mention_coverage
              + 0.15 * (1 - must_not_mention_violation_rate)
              + 0.20 * sql_execution_correctness
              + 0.10 * refusal_correctness
```

Target floor for any release: **0.85**. Any individual category below 0.70
blocks promotion regardless of overall score.

## Adding to the goldset

- Every PR that adds a new table or column must add at least one Q (in
  `qa.yaml` or `sql.yaml`) that exercises it.
- Every production miscall (user-reported wrong answer) becomes a regression
  question, tagged `regression: true` with the date and the broken behaviour.
- Never delete a question; mark it `deprecated: true` with a reason.
