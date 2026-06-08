# `lseg_fi.credit_ratings_history`

> **Domain:** Fixed Income — Credit Ratings
> **Physical location:** `lseg_fi.credit_ratings_history`
> **Source product:** Refinitiv Ratings (consolidated from S&P, Moody's, Fitch, DBRS, JCR feeds)
> **Update cadence:** Intraday (push from agency feeds); EOD reconciliation 23:00 NYT
> **Volume:** ~38M rating actions cumulatively
> **Grain:** one row per (`rating_subject_perm_id`, `rating_subject_type`, `agency_code`, `rating_scale_code`, `valid_from_ts`)
> **Primary key:** above five columns
> **Partitioning:** `partition by rating_subject_type` (`ISSUE`, `ISSUER`); cluster by `rating_subject_perm_id`

---

## 1. Purpose

Append-only ledger of every credit-rating action — both issuer and
instrument level — across the major agencies. Also exposes a vendor-computed
**composite rating** (LSEG's median-rounded methodology) for convenience.

## 2. Schema

| Column                       | Type             | Null | PK | Description                                                                              |
| ---------------------------- | ---------------- | ---- | -- | ---------------------------------------------------------------------------------------- |
| `rating_subject_perm_id`     | `BIGINT`         | NO   | ✅ | Either `org_perm_id` (issuer-level) or `instrument_perm_id` (issue-level).               |
| `rating_subject_type`        | `VARCHAR(8)`     | NO   | ✅ | `ISSUER` or `ISSUE`.                                                                     |
| `agency_code`                | `VARCHAR(8)`     | NO   | ✅ | `SP`, `MDY`, `FITCH`, `DBRS`, `JCR`, `RICN`, `EGAN`, `KBRA`, `LSEG_COMP`.                |
| `rating_scale_code`          | `VARCHAR(16)`    | NO   | ✅ | `LT_FC`, `LT_LC`, `ST_FC`, `ST_LC`, `LT_DEP`, `ST_DEP`, `IFS`. (FC=foreign ccy, LC=local ccy.) |
| `valid_from_ts`              | `TIMESTAMP(6)`   | NO   | ✅ |                                                                                          |
| `valid_to_ts`                | `TIMESTAMP(6)`   | NO   |    |                                                                                          |
| `is_current`                 | `BOOLEAN`        | NO   |    |                                                                                          |
| `rating_code`                | `VARCHAR(8)`     | NO   |    | Native agency code, e.g. `AA-`, `Baa3`, `BB+`, `Caa1`.                                   |
| `rating_outlook_code`        | `VARCHAR(8)`     | YES  |    | `POS`, `NEG`, `STABLE`, `DEVELOPING`, `RWN`, `RWP`, `RWU`.                               |
| `rating_action_code`         | `VARCHAR(16)`    | NO   |    | `NEW`, `UPGRADE`, `DOWNGRADE`, `AFFIRM`, `WITHDRAWN`, `OUTLOOK_CHANGE`, `WATCH_ADD`, `WATCH_REMOVE`. |
| `notch_change`               | `SMALLINT`       | YES  |    | Signed integer (positive = upgrade) since the prior action by same agency.               |
| `composite_rating_code`      | `VARCHAR(8)`     | YES  |    | LSEG composite — populated only when `agency_code = 'LSEG_COMP'`.                        |
| `numeric_rating_value`       | `SMALLINT`       | NO   |    | Mapped to a uniform 0–22 scale (`AAA=22`, …, `D=1`, `NR=0`). See §3.                     |
| `is_investment_grade`        | `BOOLEAN`        | NO   |    | Derived: `numeric_rating_value >= 13` (BBB-).                                            |
| `is_split_rated`             | `BOOLEAN`        | YES  |    | TRUE on `LSEG_COMP` rows where the three majors disagreed on IG/HY classification.       |
| `rating_announce_ts`         | `TIMESTAMP(6)`   | NO   |    | The agency's published timestamp.                                                        |
| `rating_press_release_url`   | `VARCHAR(512)`   | YES  |    | URL to the agency PR if available.                                                       |
| `loaded_ts`                  | `TIMESTAMP(6)`   | NO   |    |                                                                                          |

## 3. Numeric rating map

A standard 22-step scale used by LSEG to make agencies comparable.

| `numeric_rating_value` | S&P / Fitch | Moody's | Notes |
| ---------------------- | ----------- | ------- | ----- |
| 22 | AAA | Aaa | |
| 21 | AA+ | Aa1 | |
| 20 | AA  | Aa2 | |
| 19 | AA- | Aa3 | |
| 18 | A+  | A1  | |
| 17 | A   | A2  | |
| 16 | A-  | A3  | |
| 15 | BBB+ | Baa1 | |
| 14 | BBB  | Baa2 | |
| 13 | BBB- | Baa3 | **Investment-grade cutoff.** |
| 12 | BB+  | Ba1  | |
| 11 | BB   | Ba2  | |
| 10 | BB-  | Ba3  | |
|  9 | B+   | B1   | |
|  8 | B    | B2   | |
|  7 | B-   | B3   | |
|  6 | CCC+ | Caa1 | |
|  5 | CCC  | Caa2 | |
|  4 | CCC- | Caa3 | |
|  3 | CC   | Ca   | |
|  2 | C    | C    | |
|  1 | D / SD | (no equiv) | Default. |
|  0 | NR   | WR   | Not rated / withdrawn. |

## 4. Indexes

| Name                                       | Definition                                                                |
| ------------------------------------------ | ------------------------------------------------------------------------- |
| `pk_credit_ratings_history`                | See PK definition.                                                        |
| `ix_crh_subject_current`                   | `(rating_subject_perm_id, rating_subject_type)` WHERE `is_current = TRUE` |
| `ix_crh_announce_ts`                       | `(rating_announce_ts)` for news-driven analytics                          |

## 5. Sample queries

### 5.1 Current LSEG composite issuer rating

```sql
SELECT  em.entity_common_name,
        r.rating_code        AS lseg_composite,
        r.rating_outlook_code,
        r.numeric_rating_value,
        r.is_investment_grade
FROM    lseg_fi.credit_ratings_history r
JOIN    lseg_ref.entity_master         em ON em.org_perm_id = r.rating_subject_perm_id AND em.is_current = TRUE
WHERE   r.rating_subject_type = 'ISSUER'
  AND   r.agency_code         = 'LSEG_COMP'
  AND   r.rating_scale_code   = 'LT_FC'
  AND   r.is_current          = TRUE
  AND   r.rating_subject_perm_id IN (:org_perm_id_list);
```

### 5.2 Migration matrix (1y) by sector

```sql
WITH paired AS (
    SELECT  r_start.rating_subject_perm_id          AS org_perm_id,
            r_start.numeric_rating_value            AS from_rating,
            r_end.numeric_rating_value              AS to_rating
    FROM    lseg_fi.credit_ratings_history r_start
    JOIN    lseg_fi.credit_ratings_history r_end
      ON    r_end.rating_subject_perm_id = r_start.rating_subject_perm_id
      AND   r_end.rating_subject_type    = r_start.rating_subject_type
      AND   r_end.agency_code            = r_start.agency_code
      AND   r_end.rating_scale_code      = r_start.rating_scale_code
    WHERE   r_start.agency_code         = 'LSEG_COMP'
      AND   r_start.rating_subject_type = 'ISSUER'
      AND   TIMESTAMP '2025-01-01 00:00:00' BETWEEN r_start.valid_from_ts AND r_start.valid_to_ts
      AND   TIMESTAMP '2026-01-01 00:00:00' BETWEEN r_end.valid_from_ts   AND r_end.valid_to_ts
)
SELECT  sc.trbc_econ_sector_name,
        from_rating, to_rating,
        COUNT(*) AS n
FROM    paired p
JOIN    lseg_ref.entity_master         em ON em.org_perm_id = p.org_perm_id AND em.is_current = TRUE
JOIN    lseg_ref.sector_classification sc ON sc.trbc_industry_code = em.trbc_industry_code AND sc.is_current = TRUE
GROUP BY sc.trbc_econ_sector_name, from_rating, to_rating;
```

## 6. Known quirks

- A simultaneous outlook+rating change appears as **two rows** (one
  `OUTLOOK_CHANGE`, one rating action) with identical `rating_announce_ts`.
- `LSEG_COMP` is recomputed nightly from the major-three (S&P/Moody's/Fitch);
  the row's `valid_from_ts` reflects the announce ts of the latest agency
  input, not the recomputation time.
- Withdrawals (`agency_code` action `WITHDRAWN`) do **not** purge prior rows;
  filter on `is_current` only when you want today's active rating set.
- Some structured-finance tranches are rated only by one agency; do not
  expect a `LSEG_COMP` row for every instrument.
