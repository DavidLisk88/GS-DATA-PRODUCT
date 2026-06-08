# `lseg_lipper.fund_master` + companion tables

> **Domain:** Lipper Fund Data
> **Physical location:** `lseg_lipper.fund_master`, `lseg_lipper.fund_nav_history`, `lseg_lipper.fund_performance_monthly`, `lseg_lipper.fund_holdings_quarterly`
> **Source product:** Refinitiv Lipper Fund Data
> **Update cadence:** NAV daily (T+1 by region); performance monthly (3rd bd); holdings quarterly with reporting lag
> **Volume:** `fund_master` ~410k funds (live + dead); `fund_nav_history` ~1.8B rows; `fund_holdings_quarterly` ~62M position rows
> **Anchor:** `lipper_id` (Lipper's own unique fund identifier)

---

## 1. Identifier model

Lipper's data anchors on its own `lipper_id` (8-digit integer). Mappings:

```
lipper_id (Lipper ID)
  ├─→ instrument_perm_id   (the fund SHARE CLASS — e.g. "Class A USD Accum")
  │     ├─→ org_perm_id    (the asset manager firm — BlackRock, Vanguard, …)
  │     └─→ isin           (per share class)
  └─→ lipper_parent_id     (the FUND, abstracting over share classes)
```

A "fund" in marketing terms (e.g. "Fidelity Magellan") rolls up multiple
share classes; each share class has its own `lipper_id` AND `instrument_perm_id`.

---

## 2. `lseg_lipper.fund_master`

### 2.1 Schema

| Column                          | Type             | Null | PK | Description                                                              |
| ------------------------------- | ---------------- | ---- | -- | ------------------------------------------------------------------------ |
| `lipper_id`                     | `BIGINT`         | NO   | ✅ | Lipper's identifier; share-class-level.                                  |
| `valid_from_ts`                 | `TIMESTAMP(6)`   | NO   | ✅ | SCD-2.                                                                   |
| `valid_to_ts`                   | `TIMESTAMP(6)`   | NO   |    |                                                                          |
| `is_current`                    | `BOOLEAN`        | NO   |    |                                                                          |
| `lipper_parent_id`              | `BIGINT`         | NO   |    | The fund-level rollup.                                                   |
| `instrument_perm_id`            | `BIGINT`         | YES  |    | Cross-ref to `instrument_master` (`asset_class_code = 'FUND'`).          |
| `isin`                          | `CHAR(12)`       | YES  |    |                                                                          |
| `fund_name`                     | `VARCHAR(256)`   | NO   |    |                                                                          |
| `share_class_name`              | `VARCHAR(128)`   | YES  |    | "Class A", "Inst USD Acc", "Y EUR Hedged".                               |
| `asset_manager_org_perm_id`     | `BIGINT`         | NO   |    | Joins to `entity_master`.                                                |
| `domicile_country_iso`          | `CHAR(2)`        | NO   |    | Fund's domicile (e.g. `IE`, `LU` for many UCITS).                        |
| `currency_iso`                  | `CHAR(3)`        | NO   |    | Share-class denomination.                                                |
| `lipper_global_classification`  | `VARCHAR(64)`    | NO   |    | E.g. "Equity US", "Equity Global", "Bond USD Government".                |
| `lipper_objective_code`         | `VARCHAR(16)`    | NO   |    | Finer-grained objective code.                                            |
| `is_ucits`                      | `BOOLEAN`        | NO   |    |                                                                          |
| `is_etf`                        | `BOOLEAN`        | NO   |    |                                                                          |
| `is_index_tracking`             | `BOOLEAN`        | NO   |    |                                                                          |
| `benchmark_description`         | `VARCHAR(256)`   | YES  |    |                                                                          |
| `inception_date`                | `DATE`           | YES  |    |                                                                          |
| `liquidation_date`              | `DATE`           | YES  |    | NULL if fund still active.                                               |
| `fund_status_code`              | `VARCHAR(16)`    | NO   |    | `ACTIVE`, `MERGED`, `LIQUIDATED`, `CLOSED`.                              |
| `merger_successor_lipper_id`    | `BIGINT`         | YES  |    |                                                                          |
| `total_expense_ratio_pct`       | `DECIMAL(7,4)`   | YES  |    | Most recent TER %.                                                       |
| `minimum_investment`            | `DECIMAL(22,2)`  | YES  |    | In `currency_iso`.                                                       |
| `is_distribution_share`         | `BOOLEAN`        | NO   |    | TRUE = distributing; FALSE = accumulating.                               |
| `loaded_ts`                     | `TIMESTAMP(6)`   | NO   |    |                                                                          |

## 3. `lseg_lipper.fund_nav_history`

| Column            | Type             | Null | PK | Description                                                              |
| ----------------- | ---------------- | ---- | -- | ------------------------------------------------------------------------ |
| `lipper_id`       | `BIGINT`         | NO   | ✅ |                                                                          |
| `nav_date`        | `DATE`           | NO   | ✅ |                                                                          |
| `nav_price`       | `DECIMAL(18,8)`  | NO   |    | NAV per share in `currency_iso`.                                         |
| `nav_total_assets`| `DECIMAL(22,2)`  | YES  |    | AUM at this NAV date.                                                    |
| `is_swing_priced` | `BOOLEAN`        | NO   |    | TRUE if swing-pricing adjustment applied this day.                       |
| `quality_flag_code`| `VARCHAR(16)`   | NO   |    | `OK`, `ESTIMATED`, `STALE`.                                              |
| `loaded_ts`       | `TIMESTAMP(6)`   | NO   |    |                                                                          |

## 4. `lseg_lipper.fund_performance_monthly`

Pre-computed total returns + risk metrics.

| Column                       | Type             | Null | PK | Description                                                              |
| ---------------------------- | ---------------- | ---- | -- | ------------------------------------------------------------------------ |
| `lipper_id`                  | `BIGINT`         | NO   | ✅ |                                                                          |
| `period_end_date`            | `DATE`           | NO   | ✅ | Last calendar day of the month.                                          |
| `currency_iso`               | `CHAR(3)`        | NO   |    | Currency in which returns are computed (typically same as share class).  |
| `return_1m_pct`              | `DECIMAL(9,6)`   | YES  |    |                                                                          |
| `return_3m_pct`              | `DECIMAL(9,6)`   | YES  |    |                                                                          |
| `return_ytd_pct`             | `DECIMAL(9,6)`   | YES  |    |                                                                          |
| `return_1y_pct`              | `DECIMAL(9,6)`   | YES  |    |                                                                          |
| `return_3y_ann_pct`          | `DECIMAL(9,6)`   | YES  |    | Annualised.                                                              |
| `return_5y_ann_pct`          | `DECIMAL(9,6)`   | YES  |    |                                                                          |
| `return_10y_ann_pct`         | `DECIMAL(9,6)`   | YES  |    |                                                                          |
| `volatility_3y_ann_pct`      | `DECIMAL(9,6)`   | YES  |    |                                                                          |
| `sharpe_3y`                  | `DECIMAL(9,6)`   | YES  |    | Risk-free rate is the local 1M T-bill / equivalent.                     |
| `max_drawdown_3y_pct`        | `DECIMAL(9,6)`   | YES  |    |                                                                          |
| `lipper_leader_score_total`  | `SMALLINT`       | YES  |    | 1–5 (5 best) — Total Return.                                             |
| `lipper_leader_score_consist`| `SMALLINT`       | YES  |    | 1–5 — Consistent Return.                                                 |
| `lipper_leader_score_preserve`| `SMALLINT`      | YES  |    | 1–5 — Preservation.                                                      |
| `lipper_leader_score_taxeff` | `SMALLINT`       | YES  |    | 1–5 — Tax Efficiency (US funds only).                                    |
| `lipper_leader_score_expense`| `SMALLINT`       | YES  |    | 1–5 — Expense.                                                           |
| `peer_group_universe_size`   | `INTEGER`        | YES  |    | # funds in the Leader-score peer group.                                  |
| `loaded_ts`                  | `TIMESTAMP(6)`   | NO   |    |                                                                          |

## 5. `lseg_lipper.fund_holdings_quarterly`

| Column                       | Type             | Null | PK | Description                                                              |
| ---------------------------- | ---------------- | ---- | -- | ------------------------------------------------------------------------ |
| `lipper_id`                  | `BIGINT`         | NO   | ✅ | Fund share class.                                                        |
| `as_of_date`                 | `DATE`           | NO   | ✅ | Holdings-as-of date (NOT filing date).                                   |
| `holding_seq`                | `INTEGER`        | NO   | ✅ |                                                                          |
| `holding_instrument_perm_id` | `BIGINT`         | YES  |    | When the position is in an LSEG-identified security.                     |
| `holding_isin`               | `CHAR(12)`       | YES  |    |                                                                          |
| `holding_descriptor`         | `VARCHAR(256)`   | YES  |    | Free-form for cash, FX forwards, derivatives, etc.                       |
| `asset_class_code`           | `VARCHAR(8)`     | NO   |    | `EQTY`, `BOND`, `CASH`, `FUT`, `OPT`, `FX`, `OTH`.                       |
| `position_market_value`      | `DECIMAL(22,2)`  | YES  |    | In fund `currency_iso`.                                                  |
| `position_weight_pct`        | `DECIMAL(9,6)`   | YES  |    | % of fund NAV.                                                           |
| `position_quantity`          | `DECIMAL(22,4)`  | YES  |    | Shares / face / contracts.                                               |
| `position_currency_iso`      | `CHAR(3)`        | NO   |    |                                                                          |
| `is_long`                    | `BOOLEAN`        | NO   |    | FALSE for short positions.                                               |
| `country_iso`                | `CHAR(2)`        | YES  |    | Position country (issuer's country for securities).                      |
| `sector_code`                | `VARCHAR(10)`    | YES  |    | TRBC code where mappable.                                                |
| `filing_date`                | `DATE`           | NO   |    |                                                                          |
| `disclosure_lag_days`        | `SMALLINT`       | NO   |    | `filing_date - as_of_date`.                                              |
| `loaded_ts`                  | `TIMESTAMP(6)`   | NO   |    |                                                                          |

## 6. Sample queries

### 6.1 Top performing US Equity funds over 3y, with risk filter

```sql
SELECT  fm.fund_name,
        fm.share_class_name,
        fp.return_3y_ann_pct,
        fp.volatility_3y_ann_pct,
        fp.sharpe_3y,
        fp.lipper_leader_score_total
FROM    lseg_lipper.fund_performance_monthly fp
JOIN    lseg_lipper.fund_master              fm USING (lipper_id)
WHERE   fm.is_current               = TRUE
  AND   fm.lipper_global_classification = 'Equity US'
  AND   fm.fund_status_code         = 'ACTIVE'
  AND   fp.period_end_date          = DATE '2026-04-30'
  AND   fp.volatility_3y_ann_pct   <= 18.0
ORDER BY fp.return_3y_ann_pct DESC
LIMIT 25;
```

### 6.2 Funds holding a specific equity (latest disclosed quarter)

```sql
WITH latest_quarter AS (
    SELECT MAX(as_of_date) AS as_of_date
    FROM   lseg_lipper.fund_holdings_quarterly
    WHERE  holding_instrument_perm_id = 8590932301         -- AAPL common
)
SELECT  fm.fund_name,
        fm.share_class_name,
        h.position_market_value,
        h.position_weight_pct
FROM    lseg_lipper.fund_holdings_quarterly h
JOIN    lseg_lipper.fund_master            fm USING (lipper_id)
JOIN    latest_quarter                     lq ON h.as_of_date = lq.as_of_date
WHERE   h.holding_instrument_perm_id = 8590932301
  AND   fm.is_current = TRUE
ORDER BY h.position_weight_pct DESC
LIMIT 50;
```

## 7. Known quirks

- Holdings reporting lag varies by jurisdiction: US '40-Act funds typically
  60 days; UCITS often quarterly with 90-day lag; some private funds 180+ days.
  Always join through `disclosure_lag_days`, not the assumption that
  "Q1 holdings are available in early April".
- Swing-priced days can produce apparent NAV jumps — use `is_swing_priced`
  to flag and exclude from volatility calculations if needed.
- Liquidated funds remain in `fund_master` with status; their final NAV row
  is in `fund_nav_history`. Backtests of fund picks must include them.
