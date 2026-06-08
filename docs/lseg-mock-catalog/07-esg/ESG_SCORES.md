# `lseg_esg.esg_scores`

> **Domain:** ESG
> **Source product:** Refinitiv ESG (formerly Asset4)
> **Update cadence:** Monthly refresh on the 5th business day; corrections continuous
> **Volume:** ~13,000 companies × ~20 years × monthly = ~3M rows
> **Grain:** one row per (`org_perm_id`, `score_period_end_date`, `valid_from_ts`) — bitemporal
> **Primary key:** (`org_perm_id`, `score_period_end_date`, `valid_from_ts`)

---

## 1. Purpose

LSEG/Refinitiv's standardised ESG scoring — three pillars (Environmental,
Social, Governance) plus a combined ESG and ESG Controversy-adjusted score,
on a 0–100 scale.

## 2. Schema

| Column                         | Type            | Null | PK | Description                                                              |
| ------------------------------ | --------------- | ---- | -- | ------------------------------------------------------------------------ |
| `org_perm_id`                  | `BIGINT`        | NO   | ✅ |                                                                          |
| `score_period_end_date`        | `DATE`          | NO   | ✅ | End of the period the score reflects (usually fiscal year end).         |
| `valid_from_ts`                | `TIMESTAMP(6)`  | NO   | ✅ |                                                                          |
| `valid_to_ts`                  | `TIMESTAMP(6)`  | NO   |    |                                                                          |
| `is_current_version`           | `BOOLEAN`       | NO   |    |                                                                          |
| `esg_score`                    | `DECIMAL(6,2)`  | YES  |    | 0–100 combined ESG score (percentile-based).                             |
| `esg_combined_score`           | `DECIMAL(6,2)`  | YES  |    | ESG score adjusted for ESG controversies overlay.                        |
| `environmental_pillar_score`   | `DECIMAL(6,2)`  | YES  |    |                                                                          |
| `social_pillar_score`          | `DECIMAL(6,2)`  | YES  |    |                                                                          |
| `governance_pillar_score`      | `DECIMAL(6,2)`  | YES  |    |                                                                          |
| `controversy_score`            | `DECIMAL(6,2)`  | YES  |    | 100 = no controversies; lower = more.                                    |
| `esg_grade_letter`             | `VARCHAR(3)`    | YES  |    | A+, A, A-, B+, ..., D-.                                                  |
| `scope_1_emissions_tco2e`      | `DECIMAL(22,2)` | YES  |    | Direct emissions, tonnes CO2-equivalent.                                 |
| `scope_2_emissions_tco2e`      | `DECIMAL(22,2)` | YES  |    | Indirect — purchased electricity.                                        |
| `scope_3_emissions_tco2e`      | `DECIMAL(22,2)` | YES  |    | Value-chain emissions.                                                   |
| `emissions_disclosure_score`   | `DECIMAL(6,2)`  | YES  |    |                                                                          |
| `independent_directors_pct`    | `DECIMAL(5,2)`  | YES  |    | % of board that is independent.                                          |
| `women_on_board_pct`           | `DECIMAL(5,2)`  | YES  |    |                                                                          |
| `ceo_pay_ratio`                | `DECIMAL(10,2)` | YES  |    | CEO total comp / median employee comp.                                   |
| `source_disclosure_year`       | `SMALLINT`      | NO   |    | The reporting year the score was derived from.                           |
| `methodology_version`          | `VARCHAR(8)`    | NO   |    | LSEG ESG methodology revision (e.g. `v2024.1`). Important for time-series consistency. |
| `loaded_ts`                    | `TIMESTAMP(6)`  | NO   |    |                                                                          |

## 3. Indexes

| Name                                   | Definition                                                                |
| -------------------------------------- | ------------------------------------------------------------------------- |
| `pk_esg_scores`                        | `(org_perm_id, score_period_end_date, valid_from_ts)`                     |
| `ix_esg_org_current`                   | `(org_perm_id)` WHERE `is_current_version = TRUE`                         |
| `ix_esg_period`                        | `(score_period_end_date)` WHERE `is_current_version = TRUE`               |

## 4. Sample query

```sql
SELECT  em.entity_common_name,
        es.score_period_end_date,
        es.esg_score,
        es.environmental_pillar_score,
        es.scope_1_emissions_tco2e + es.scope_2_emissions_tco2e
            AS scope_1_2_tco2e
FROM    lseg_esg.esg_scores      es
JOIN    lseg_ref.entity_master   em USING (org_perm_id)
WHERE   em.is_current = TRUE
  AND   es.is_current_version = TRUE
  AND   es.score_period_end_date = DATE '2024-12-31'
  AND   em.trbc_industry_code IN (
            SELECT trbc_industry_code FROM lseg_ref.sector_classification
            WHERE trbc_econ_sector_code = '50'         -- Technology
              AND is_current = TRUE)
ORDER BY es.esg_score DESC NULLS LAST
LIMIT 25;
```

## 5. Known quirks

- ESG methodology revisions cause apparent step-changes; pin `methodology_version`
  when building time series.
- Scope 3 is sparsely populated pre-2018; do not impute zeros.
- `controversy_score` is sentiment-derived from news; spikes recover slowly.
