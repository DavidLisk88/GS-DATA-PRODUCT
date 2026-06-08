# `lseg_fi.bond_terms`

> **Domain:** Fixed Income — Bond Reference Terms
> **Physical location:** `lseg_fi.bond_terms`
> **Source product:** Refinitiv Fixed Income Reference (RDP `bonds/terms` + DSS feed `FIRef_v2`)
> **Update cadence:** Intraday for new issues + amendments; daily reconciliation 04:00 NYT
> **Volume:** ~7.8M live + matured instruments
> **Grain:** one row per (`instrument_perm_id`, `valid_from_ts`) — SCD-2
> **Primary key:** (`instrument_perm_id`, `valid_from_ts`)
> **Partitioning:** `partition by issue_country_iso`, cluster by `instrument_perm_id`

---

## 1. Purpose

The authoritative reference for fixed-income terms: coupon schedule, day-count,
call/put features, covenants, ranking, optionality. **Inherits** from
`lseg_ref.instrument_master` — every `instrument_perm_id` here has a matching
parent row in `instrument_master` with `asset_class_code IN ('BOND','CONV','MTN','SUKUK')`.

## 2. Schema

| Column                          | Type             | Null | PK | Description                                                                              |
| ------------------------------- | ---------------- | ---- | -- | ---------------------------------------------------------------------------------------- |
| `instrument_perm_id`            | `BIGINT`         | NO   | ✅ | Joins to `instrument_master`.                                                            |
| `valid_from_ts`                 | `TIMESTAMP(6)`   | NO   | ✅ | SCD-2 effective.                                                                         |
| `valid_to_ts`                   | `TIMESTAMP(6)`   | NO   |    |                                                                                          |
| `is_current`                    | `BOOLEAN`        | NO   |    |                                                                                          |
| `bond_type_code`                | `VARCHAR(16)`    | NO   |    | `GOVT`, `CORP`, `AGCY`, `MUNI`, `SUPRA`, `MBS`, `ABS`, `CB`, `COVERED`, `LOAN`.          |
| `seniority_code`                | `VARCHAR(16)`    | YES  |    | `SR_SECURED`, `SR_UNSECURED`, `SUB`, `JR_SUB`, `MEZZ`, `EQUITY`.                         |
| `coupon_type_code`              | `VARCHAR(16)`    | NO   |    | `FIXED`, `FLOATING`, `STEP_UP`, `ZERO`, `INFLATION_LINKED`, `PIK`, `VAR`.                |
| `coupon_rate_pct`               | `DECIMAL(9,6)`   | YES  |    | Initial / fixed rate, annualised %.                                                      |
| `coupon_spread_bps`             | `INTEGER`        | YES  |    | Floating bonds: spread over reference rate in bps.                                       |
| `coupon_reference_rate_code`    | `VARCHAR(16)`    | YES  |    | `SOFR_3M`, `EURIBOR_3M`, `SONIA_3M`, `TONA_3M`, etc.                                     |
| `coupon_frequency_code`         | `VARCHAR(8)`     | NO   |    | `ANNUAL`, `SEMI`, `QTR`, `MTHLY`, `ZERO`, `IRREG`.                                       |
| `day_count_convention_code`     | `VARCHAR(16)`    | NO   |    | `30/360`, `ACT/360`, `ACT/365`, `ACT/ACT_ICMA`, `ACT/ACT_ISDA`, `BUS/252`.               |
| `business_day_convention_code`  | `VARCHAR(16)`    | NO   |    | `FOLLOWING`, `MOD_FOLLOWING`, `PRECEDING`, `NONE`.                                       |
| `first_coupon_date`             | `DATE`           | YES  |    |                                                                                          |
| `next_coupon_date`              | `DATE`           | YES  |    | Refreshed daily; for valuation use the cashflow schedule (§5).                           |
| `maturity_date`                 | `DATE`           | YES  |    | NULL for perpetuals.                                                                     |
| `is_perpetual`                  | `BOOLEAN`        | NO   |    | TRUE for perps (AT1 etc.).                                                               |
| `face_value`                    | `DECIMAL(18,4)`  | NO   |    | Par per unit; usually 1000 or 100.                                                       |
| `minimum_denomination`          | `DECIMAL(18,4)`  | YES  |    | Smallest tradeable unit (e.g. 200,000 EUR for institutional EUR HY).                     |
| `issue_amount`                  | `DECIMAL(22,4)`  | YES  |    | Original issued notional.                                                                |
| `amount_outstanding`            | `DECIMAL(22,4)`  | YES  |    | Current notional outstanding (post buybacks/tap issues).                                 |
| `is_callable`                   | `BOOLEAN`        | NO   |    | TRUE if any call schedule row exists.                                                    |
| `is_puttable`                   | `BOOLEAN`        | NO   |    |                                                                                          |
| `is_sinkable`                   | `BOOLEAN`        | NO   |    | TRUE if structured with a sinking fund.                                                  |
| `is_convertible`                | `BOOLEAN`        | NO   |    | TRUE for convertible bonds (`asset_class_code = 'CONV'`).                                |
| `conversion_ratio`              | `DECIMAL(18,8)`  | YES  |    | Shares per bond face (convertibles only).                                                |
| `conversion_underlying_instrument_perm_id` | `BIGINT` | YES  |    | The equity into which it converts.                                                       |
| `is_inflation_linked`           | `BOOLEAN`        | NO   |    |                                                                                          |
| `inflation_index_code`          | `VARCHAR(16)`    | YES  |    | `US_CPI_U`, `UK_RPI`, `EUR_HICPxT`, `JP_CPI`.                                            |
| `base_index_value`              | `DECIMAL(18,6)`  | YES  |    | Index reference at issue (for linkers).                                                  |
| `currency_iso`                  | `CHAR(3)`        | NO   |    | Denomination.                                                                            |
| `issue_country_iso`             | `CHAR(2)`        | NO   |    |                                                                                          |
| `governing_law_country_iso`     | `CHAR(2)`        | YES  |    | Often differs from issue country (e.g. NY law on EM bonds).                              |
| `issue_date`                    | `DATE`           | NO   |    |                                                                                          |
| `is_144a`                       | `BOOLEAN`        | NO   |    | US Rule 144A flag (QIB-only).                                                            |
| `is_reg_s`                      | `BOOLEAN`        | NO   |    | Regulation S flag.                                                                       |
| `is_green_bond`                 | `BOOLEAN`        | NO   |    | Self-labelled or ICMA-aligned.                                                           |
| `is_social_bond`                | `BOOLEAN`        | NO   |    |                                                                                          |
| `is_sustainability_linked`      | `BOOLEAN`        | NO   |    |                                                                                          |
| `lead_manager_org_perm_ids`     | `ARRAY<BIGINT>`  | YES  |    | Underwriter syndicate at issue.                                                          |
| `loaded_ts`                     | `TIMESTAMP(6)`   | NO   |    |                                                                                          |

## 3. Indexes

| Name                              | Columns                                              |
| --------------------------------- | ---------------------------------------------------- |
| `pk_bond_terms`                   | `(instrument_perm_id, valid_from_ts)`                |
| `ix_bond_terms_maturity`          | `(maturity_date)` WHERE `is_current = TRUE`          |
| `ix_bond_terms_type_country`      | `(bond_type_code, issue_country_iso)`                |
| `ix_bond_terms_callable`          | `(is_callable)` WHERE `is_current = TRUE`            |

## 4. Companion tables

### 4.1 `lseg_fi.bond_call_schedule`

| Column                   | Type             | Null | PK | Description                                                              |
| ------------------------ | ---------------- | ---- | -- | ------------------------------------------------------------------------ |
| `instrument_perm_id`     | `BIGINT`         | NO   | ✅ |                                                                          |
| `call_seq`               | `SMALLINT`       | NO   | ✅ |                                                                          |
| `call_date`              | `DATE`           | NO   |    | First date callable at the listed price (American: any date after).      |
| `call_type_code`         | `VARCHAR(16)`    | NO   |    | `AMERICAN`, `EUROPEAN`, `BERMUDAN`, `MAKE_WHOLE`, `PAR_CALL`, `TAX_CALL`.|
| `call_price_pct_of_par`  | `DECIMAL(9,6)`   | YES  |    |                                                                          |
| `make_whole_spread_bps`  | `INTEGER`        | YES  |    | For `MAKE_WHOLE` calls.                                                  |
| `notice_min_days`        | `SMALLINT`       | YES  |    |                                                                          |
| `notice_max_days`        | `SMALLINT`       | YES  |    |                                                                          |
| `loaded_ts`              | `TIMESTAMP(6)`   | NO   |    |                                                                          |

### 4.2 `lseg_fi.bond_cashflow_schedule`

The expanded coupon + principal schedule (deterministic for fixed, projected
for floating).

| Column                    | Type             | Null | PK | Description                                                              |
| ------------------------- | ---------------- | ---- | -- | ------------------------------------------------------------------------ |
| `instrument_perm_id`      | `BIGINT`         | NO   | ✅ |                                                                          |
| `cashflow_seq`            | `INTEGER`        | NO   | ✅ |                                                                          |
| `cashflow_type_code`      | `VARCHAR(16)`    | NO   |    | `COUPON`, `PRINCIPAL`, `PRINCIPAL_PARTIAL`, `SINK`.                      |
| `accrual_start_date`      | `DATE`           | YES  |    | NULL for principal only.                                                 |
| `accrual_end_date`        | `DATE`           | YES  |    |                                                                          |
| `payment_date`            | `DATE`           | NO   |    | Post-business-day adjustment.                                            |
| `coupon_rate_pct`         | `DECIMAL(9,6)`   | YES  |    | Rate applicable to this period (fixed bonds: equals header rate).        |
| `cashflow_per_100_face`   | `DECIMAL(18,8)`  | NO   |    | Cashflow amount per 100 face.                                            |
| `is_projected`            | `BOOLEAN`        | NO   |    | TRUE if floating/inflation projected; FALSE if fixed/deterministic.      |
| `loaded_ts`               | `TIMESTAMP(6)`   | NO   |    |                                                                          |

---

## 5. Relationships

| Joins to                                       | On                                                              | Cardinality |
| ---------------------------------------------- | --------------------------------------------------------------- | ----------- |
| `lseg_ref.instrument_master`                   | `bond_terms.instrument_perm_id = instrument_master.instrument_perm_id` | 1 : 1 (parent) |
| `lseg_ref.corporate_actions`                   | `bond_terms.instrument_perm_id = corporate_actions.instrument_perm_id` | 1 : N (calls, coupons, redemptions appear as CAs too) |
| `lseg_fi.bond_call_schedule`                   | `(instrument_perm_id)`                                          | 1 : N       |
| `lseg_fi.bond_cashflow_schedule`               | `(instrument_perm_id)`                                          | 1 : N       |
| `lseg_fi.credit_ratings_history`               | `(instrument_perm_id)` (instrument-level) OR via `org_perm_id` (issuer-level) | 1 : N |

## 6. Sample queries

### 6.1 All callable USD investment-grade corporates maturing in 2030

```sql
SELECT  im.isin,
        im.instrument_name,
        bt.coupon_rate_pct,
        bt.maturity_date,
        bt.amount_outstanding,
        em.entity_common_name
FROM    lseg_fi.bond_terms          bt
JOIN    lseg_ref.instrument_master  im  USING (instrument_perm_id)
JOIN    lseg_ref.entity_master      em  ON em.org_perm_id = im.org_perm_id AND em.is_current = TRUE
WHERE   bt.is_current = TRUE
  AND   im.is_current = TRUE
  AND   bt.bond_type_code      = 'CORP'
  AND   bt.currency_iso        = 'USD'
  AND   bt.is_callable         = TRUE
  AND   bt.maturity_date BETWEEN DATE '2030-01-01' AND DATE '2030-12-31'
  AND   EXISTS (
            SELECT 1
            FROM   lseg_fi.credit_ratings_history r
            WHERE  r.instrument_perm_id = bt.instrument_perm_id
              AND  r.is_current = TRUE
              AND  r.composite_rating_code IN ('AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-')
        );
```

### 6.2 Project next 12 months of cashflows for a bond

```sql
SELECT  cashflow_type_code,
        payment_date,
        cashflow_per_100_face,
        cashflow_per_100_face * (bt.amount_outstanding / 100.0)  AS expected_cashflow
FROM    lseg_fi.bond_cashflow_schedule cs
JOIN    lseg_fi.bond_terms             bt  USING (instrument_perm_id)
WHERE   cs.instrument_perm_id = :instrument_perm_id
  AND   cs.payment_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '12' MONTH
  AND   bt.is_current = TRUE
ORDER BY cs.payment_date;
```

## 7. Known quirks

- For floating-rate notes the `coupon_rate_pct` on the header reflects only
  the **initial** rate; always use `bond_cashflow_schedule` for valuation.
- A make-whole call is "callable in name only" — modelling teams usually
  treat MW-only bonds as non-callable for OAS purposes.
- Tap issues update `amount_outstanding` but **do not** create a new
  `instrument_perm_id`; track tap history via `corporate_actions`
  (`ca_type_code = 'TAP_ISSUE'`).
- Convertibles' `conversion_ratio` can adjust after equity splits — the SCD-2
  row will refresh, but downstream caches must invalidate on split events.
