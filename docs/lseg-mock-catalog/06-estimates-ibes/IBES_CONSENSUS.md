# I/B/E/S Estimates — `lseg_ibes.*`

> **Domain:** Analyst Estimates
> **Source product:** LSEG I/B/E/S (Institutional Brokers' Estimate System)
> **Update cadence:** Nightly batch (02:00 NYT) + intraday corrections feed
> **Volume:** ~18M consensus rows, ~410M detail rows
> **Grain:** see each table

I/B/E/S is the canonical historical sell-side estimates dataset. It uses its
own ticker convention (`ibes_ticker`) — never assume it equals the exchange
ticker.

---

## A) `lseg_ibes.ibes_ticker_xref`

The Rosetta-Stone between `ibes_ticker` and `org_perm_id`.

### A.1 Schema

| Column                 | Type           | Null | PK | Description                                                              |
| ---------------------- | -------------- | ---- | -- | ------------------------------------------------------------------------ |
| `ibes_ticker`          | `VARCHAR(8)`   | NO   | ✅ | I/B/E/S ticker, per region.                                              |
| `ibes_region_code`     | `CHAR(3)`      | NO   | ✅ | `USA`, `EUR`, `JPN`, `EMA`, `ROW`. I/B/E/S maintains separate per-region tickers. |
| `valid_from_ts`        | `TIMESTAMP(6)` | NO   | ✅ |                                                                          |
| `valid_to_ts`          | `TIMESTAMP(6)` | NO   |    |                                                                          |
| `is_current`           | `BOOLEAN`      | NO   |    |                                                                          |
| `org_perm_id`          | `BIGINT`       | NO   |    | Joins to `entity_master`.                                                |
| `primary_isin`         | `CHAR(12)`     | YES  |    | The ISIN I/B/E/S considers the analyst-covered security.                 |
| `primary_currency_iso` | `CHAR(3)`      | NO   |    | Currency of estimates for this region.                                   |
| `loaded_ts`            | `TIMESTAMP(6)` | NO   |    |                                                                          |

---

## B) `lseg_ibes.estimate_consensus`

### B.1 Purpose

Pre-aggregated consensus (mean, median, dispersion, count) for each
(company, region, measure, period) at a daily-snapshot grain.

### B.2 Grain & key

- **Grain:** one row per (`ibes_ticker`, `ibes_region_code`, `measure_code`, `period_end_date`, `consensus_date`).
- **Primary key:** all five above.

### B.3 Schema

| Column                       | Type            | Null | PK | Description                                                              |
| ---------------------------- | --------------- | ---- | -- | ------------------------------------------------------------------------ |
| `ibes_ticker`                | `VARCHAR(8)`    | NO   | ✅ |                                                                          |
| `ibes_region_code`           | `CHAR(3)`       | NO   | ✅ |                                                                          |
| `measure_code`               | `VARCHAR(8)`    | NO   | ✅ | See §C.                                                                  |
| `period_end_date`            | `DATE`          | NO   | ✅ | Forecast period end.                                                     |
| `consensus_date`             | `DATE`          | NO   | ✅ | The date for which this consensus snapshot is true (~ "as-of" date).     |
| `period_type_code`           | `VARCHAR(8)`    | NO   |    | `FY1`,`FY2`,`FY3`,`Q1`,...,`LTM`. Redundant with `period_end_date` but convenient. |
| `currency_iso`               | `CHAR(3)`       | NO   |    |                                                                          |
| `mean_value`                 | `DECIMAL(22,6)` | YES  |    | Consensus mean.                                                          |
| `median_value`               | `DECIMAL(22,6)` | YES  |    |                                                                          |
| `stddev_value`               | `DECIMAL(22,6)` | YES  |    | Dispersion across analysts.                                              |
| `high_value`                 | `DECIMAL(22,6)` | YES  |    |                                                                          |
| `low_value`                  | `DECIMAL(22,6)` | YES  |    |                                                                          |
| `num_estimates`              | `SMALLINT`      | NO   |    | Estimator count contributing to this consensus.                          |
| `num_up_revisions_30d`       | `SMALLINT`      | YES  |    | Upward revisions in trailing 30 days.                                    |
| `num_down_revisions_30d`     | `SMALLINT`      | YES  |    |                                                                          |
| `loaded_ts`                  | `TIMESTAMP(6)`  | NO   |    |                                                                          |

## C) `measure_code` enumeration (subset)

| Code   | Description                                | Unit                |
| ------ | ------------------------------------------ | ------------------- |
| `EPS`  | Earnings per share                         | Currency/share      |
| `REV`  | Revenue                                    | Currency (units)    |
| `EBI`  | EBIT                                       | Currency            |
| `EBT`  | EBITDA                                     | Currency            |
| `NET`  | Net income                                 | Currency            |
| `CPS`  | Cash flow per share                        | Currency/share      |
| `BPS`  | Book value per share                       | Currency/share      |
| `DPS`  | Dividend per share                         | Currency/share      |
| `CAP`  | CapEx                                      | Currency            |
| `FFO`  | Funds from operations (REIT)               | Currency            |
| `TGT`  | Price target                               | Currency            |
| `REC`  | Recommendation (numeric 1=Strong Buy..5=Sell) | unitless         |

---

## D) `lseg_ibes.estimate_detail` (analyst-level)

### D.1 Schema (key columns only)

| Column                     | Type            | Null | PK | Description                                                              |
| -------------------------- | --------------- | ---- | -- | ------------------------------------------------------------------------ |
| `ibes_ticker`              | `VARCHAR(8)`    | NO   | ✅ |                                                                          |
| `ibes_region_code`         | `CHAR(3)`       | NO   | ✅ |                                                                          |
| `analyst_id`               | `BIGINT`        | NO   | ✅ | Anonymised analyst ID (real analyst name requires `LSEG_IBES_ANALYST_NAME_VIEWER`). |
| `broker_id`                | `BIGINT`        | NO   | ✅ | Anonymised broker ID.                                                    |
| `measure_code`             | `VARCHAR(8)`    | NO   | ✅ |                                                                          |
| `period_end_date`          | `DATE`          | NO   | ✅ |                                                                          |
| `estimate_date`            | `DATE`          | NO   | ✅ | Date the analyst published this estimate.                                |
| `estimate_value`           | `DECIMAL(22,6)` | YES  |    |                                                                          |
| `currency_iso`             | `CHAR(3)`       | NO   |    |                                                                          |
| `is_active`                | `BOOLEAN`       | NO   |    | FALSE if superseded by a later estimate from the same analyst.           |
| `superseded_by_estimate_date` | `DATE`       | YES  |    |                                                                          |
| `revision_direction_code`  | `VARCHAR(8)`    | YES  |    | `UP`, `DOWN`, `NEW`, `REITER`, `DROPPED`.                                |
| `analyst_name`             | `VARCHAR(128)`  | YES  |    | **[RESTRICTED]** — requires entitlement.                                 |
| `broker_name`              | `VARCHAR(128)`  | YES  |    | **[RESTRICTED]** — requires entitlement.                                 |
| `loaded_ts`                | `TIMESTAMP(6)`  | NO   |    |                                                                          |

---

## E) Sample queries

### E.1 Current FY1 EPS consensus for a name

```sql
SELECT  ic.consensus_date,
        ic.period_end_date,
        ic.mean_value     AS eps_mean,
        ic.median_value   AS eps_median,
        ic.num_estimates,
        ic.num_up_revisions_30d,
        ic.num_down_revisions_30d
FROM    lseg_ibes.ibes_ticker_xref  xr
JOIN    lseg_ibes.estimate_consensus ic
  ON    ic.ibes_ticker      = xr.ibes_ticker
  AND   ic.ibes_region_code = xr.ibes_region_code
WHERE   xr.org_perm_id     = 4295905573         -- Apple
  AND   xr.ibes_region_code = 'USA'
  AND   xr.is_current      = TRUE
  AND   ic.measure_code    = 'EPS'
  AND   ic.period_type_code = 'FY1'
  AND   ic.consensus_date  = DATE '2026-05-30'
ORDER BY ic.period_end_date;
```

### E.2 EPS surprise — actual vs prior consensus

```sql
WITH consensus_at_prev_close AS (
    SELECT  ibes_ticker, ibes_region_code, period_end_date, mean_value AS consensus_eps
    FROM    lseg_ibes.estimate_consensus
    WHERE   measure_code   = 'EPS'
      AND   period_type_code = 'FQ1'
      AND   consensus_date = DATE '2026-04-30'         -- the day before Apple reports
)
SELECT  cf.org_perm_id,
        cf.period_end_date,
        cf.eps_diluted               AS actual_eps,
        c.consensus_eps              AS prior_consensus_eps,
        (cf.eps_diluted - c.consensus_eps)
            / NULLIF(ABS(c.consensus_eps),0) * 100  AS surprise_pct
FROM    lseg_wsf.company_fundamentals    cf
JOIN    lseg_ibes.ibes_ticker_xref       xr ON xr.org_perm_id = cf.org_perm_id AND xr.ibes_region_code = 'USA' AND xr.is_current
JOIN    consensus_at_prev_close          c  ON c.ibes_ticker = xr.ibes_ticker AND c.ibes_region_code = xr.ibes_region_code
WHERE   cf.org_perm_id = 4295905573
  AND   cf.period_end_date = DATE '2026-03-28'
  AND   cf.fiscal_period_type_code = 'Q2'
  AND   cf.is_current_version = TRUE
  AND   c.period_end_date = cf.period_end_date;
```

## F) Known quirks

- A single company can have **estimates in multiple regions** if it is
  cross-covered (e.g. Samsung — KR + USA ADR). Always filter on
  `ibes_region_code` for apples-to-apples comparisons.
- `measure_code` units depend on the region's convention; e.g. Japanese EPS is
  in JPY/share, with no decimal adjustments for ADRs.
- Mean consensus is **active-only** (excludes stale/withdrawn estimates).
  For "all-analyst" academic studies use the detail table.
- The detail table's anonymised IDs are stable across time and across the
  consensus table — you can join them safely without the names.
