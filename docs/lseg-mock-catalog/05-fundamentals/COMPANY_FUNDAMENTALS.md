# `lseg_wsf.company_fundamentals`

> **Domain:** Fundamentals
> **Physical location:** `lseg_wsf.company_fundamentals`
> **Source product:** Worldscope Fundamentals (DSS feed `WS_Fund_v6`)
> **Update cadence:** Filing-driven (within 24h of SEDAR/EDGAR/national filing)
> **Volume:** ~89M rows (~85k companies × multiple periods × bitemporal versions)
> **Grain:** one row per (`org_perm_id`, `period_end_date`, `fiscal_period_type_code`, `valid_from_ts`)
> **Primary key:** (`org_perm_id`, `period_end_date`, `fiscal_period_type_code`, `valid_from_ts`)
> **Partitioning:** `partition by period_end_year`; cluster by `org_perm_id`

---

## 1. Purpose

Standardised, point-in-time corporate fundamentals (income statement, balance
sheet, cash flow) sourced from filings, normalised by LSEG's Worldscope team
into a comparable cross-jurisdiction schema.

## 2. Bitemporality (read this twice)

Each (company, period, period-type) combination has **multiple versions** as
restatements arrive:

- **`period_end_date`** — *when the data describes* (e.g. FY2024 ends 2024-12-31).
- **`valid_from_ts`** / **`valid_to_ts`** — *when LSEG considered this version
  the truth*. A FY2024 row first published 2025-02-15, restated 2025-08-20,
  produces two rows: `[2025-02-15, 2025-08-20)` and `[2025-08-20, 9999-12-31)`.

For a **point-in-time** ("as known on date X") query, filter:
```sql
WHERE period_end_date <= DATE 'X'
  AND TIMESTAMP 'X 23:59:59' BETWEEN valid_from_ts AND valid_to_ts
```

For an **as-restated** ("best current truth") query, filter:
```sql
WHERE valid_to_ts = TIMESTAMP '9999-12-31 00:00:00'
```

## 3. Schema (income statement subset)

| Column                          | Type            | Null | PK | Description                                                              |
| ------------------------------- | --------------- | ---- | -- | ------------------------------------------------------------------------ |
| `org_perm_id`                   | `BIGINT`        | NO   | ✅ |                                                                          |
| `period_end_date`               | `DATE`          | NO   | ✅ | Last calendar day of the reporting period.                               |
| `fiscal_period_type_code`       | `VARCHAR(8)`    | NO   | ✅ | `FY`, `SA`, `Q1`–`Q4`, `LTM`, `YTD`, `IFY` (interim-fiscal-year).        |
| `valid_from_ts`                 | `TIMESTAMP(6)`  | NO   | ✅ |                                                                          |
| `valid_to_ts`                   | `TIMESTAMP(6)`  | NO   |    |                                                                          |
| `is_current_version`            | `BOOLEAN`       | NO   |    | `valid_to_ts = '9999-12-31'`.                                            |
| `fiscal_year`                   | `SMALLINT`      | NO   |    | Issuer-fiscal-calendar year (a Sep-year-end FY24 has `fiscal_year=2024`).|
| `report_currency_iso`           | `CHAR(3)`       | NO   |    | Currency in which the issuer reports.                                    |
| `report_filing_date`            | `DATE`          | YES  |    | Original filing date.                                                    |
| `report_restatement_flag`       | `BOOLEAN`       | NO   |    | TRUE if this version supersedes a prior one.                             |
| `accounting_standard_code`      | `VARCHAR(8)`    | NO   |    | `IFRS`, `USGAAP`, `JGAAP`, `INDAS`, `CHGAAP`, `OTHER`.                  |
| `audit_status_code`             | `VARCHAR(16)`   | YES  |    | `AUDITED`, `UNAUDITED`, `REVIEWED`, `QUALIFIED`, `ADVERSE`.              |
| `revenue`                       | `DECIMAL(22,2)` | YES  |    | In `report_currency_iso`. Net of rebates/returns per IFRS 15 / ASC 606.  |
| `cost_of_revenue`               | `DECIMAL(22,2)` | YES  |    |                                                                          |
| `gross_profit`                  | `DECIMAL(22,2)` | YES  |    |                                                                          |
| `operating_expenses`            | `DECIMAL(22,2)` | YES  |    | SG&A + R&D + other opex.                                                 |
| `operating_income`              | `DECIMAL(22,2)` | YES  |    |                                                                          |
| `ebitda`                        | `DECIMAL(22,2)` | YES  |    | Computed; not always equal to issuer-reported "Adjusted EBITDA".         |
| `interest_expense`              | `DECIMAL(22,2)` | YES  |    |                                                                          |
| `income_before_tax`             | `DECIMAL(22,2)` | YES  |    |                                                                          |
| `tax_expense`                   | `DECIMAL(22,2)` | YES  |    |                                                                          |
| `net_income`                    | `DECIMAL(22,2)` | YES  |    | After minorities, attributable to common holders.                        |
| `net_income_to_minorities`      | `DECIMAL(22,2)` | YES  |    |                                                                          |
| `eps_basic`                     | `DECIMAL(18,6)` | YES  |    |                                                                          |
| `eps_diluted`                   | `DECIMAL(18,6)` | YES  |    |                                                                          |
| `shares_basic_weighted_avg`     | `BIGINT`        | YES  |    |                                                                          |
| `shares_diluted_weighted_avg`   | `BIGINT`        | YES  |    |                                                                          |
| `revenue_usd`                   | `DECIMAL(22,2)` | YES  |    | Convenience: FX-translated at period-end WMR_LON_4PM. Re-derived nightly.|
| `net_income_usd`                | `DECIMAL(22,2)` | YES  |    | As above.                                                                |
| `balance_sheet_assets_total`    | `DECIMAL(22,2)` | YES  |    |                                                                          |
| `balance_sheet_liab_total`      | `DECIMAL(22,2)` | YES  |    |                                                                          |
| `balance_sheet_equity_total`    | `DECIMAL(22,2)` | YES  |    |                                                                          |
| `cash_and_equivalents`          | `DECIMAL(22,2)` | YES  |    |                                                                          |
| `total_debt`                    | `DECIMAL(22,2)` | YES  |    | Short-term + long-term debt.                                             |
| `cfo`                           | `DECIMAL(22,2)` | YES  |    | Cash from operating activities.                                          |
| `cfi`                           | `DECIMAL(22,2)` | YES  |    | Cash from investing activities.                                          |
| `cff`                           | `DECIMAL(22,2)` | YES  |    | Cash from financing activities.                                          |
| `capex`                         | `DECIMAL(22,2)` | YES  |    | Purchases of PP&E (negative number per IFRS convention).                 |
| `free_cash_flow`                | `DECIMAL(22,2)` | YES  |    | `cfo + capex` (capex is negative).                                       |
| `period_end_year`               | `SMALLINT`      | NO   |    | Partition column = `EXTRACT(YEAR FROM period_end_date)`.                 |
| `loaded_ts`                     | `TIMESTAMP(6)`  | NO   |    |                                                                          |

> **Note:** Only a subset of Worldscope's ~3,000 standardised line items is
> shown here. Full coverage including segment-, region-, and product-line
> breakdowns is documented in [SEGMENT_DATA](SEGMENT_DATA.md) and the
> full data dictionary.

## 4. Indexes

| Name                                      | Definition                                                          |
| ----------------------------------------- | ------------------------------------------------------------------- |
| `pk_company_fundamentals`                 | `(org_perm_id, period_end_date, fiscal_period_type_code, valid_from_ts)` |
| `ix_cf_org_period_current`                | `(org_perm_id, period_end_date)` WHERE `is_current_version = TRUE`  |
| `ix_cf_period_end`                        | `(period_end_date, fiscal_period_type_code)` WHERE `is_current_version = TRUE` |

## 5. Sample queries

### 5.1 Latest restated FY2024 P&L for a peer set

```sql
SELECT  em.entity_common_name,
        cf.period_end_date,
        cf.revenue_usd / 1e9         AS revenue_bn,
        cf.net_income_usd / 1e9      AS net_income_bn,
        cf.eps_diluted
FROM    lseg_wsf.company_fundamentals cf
JOIN    lseg_ref.entity_master        em
  ON    em.org_perm_id = cf.org_perm_id
  AND   em.is_current = TRUE
WHERE   cf.org_perm_id IN (4295905573, 4295902158, 4295902963)       -- AAPL, MSFT, GOOG
  AND   cf.period_end_date = DATE '2024-12-31'                       -- yes, MSFT/AAPL non-CY end
  AND   cf.fiscal_period_type_code = 'FY'
  AND   cf.is_current_version = TRUE;
```

### 5.2 Point-in-time view: what was known on 2025-04-30

```sql
SELECT  cf.org_perm_id,
        cf.period_end_date,
        cf.revenue,
        cf.report_currency_iso
FROM    lseg_wsf.company_fundamentals cf
WHERE   cf.org_perm_id = 4295905573
  AND   cf.fiscal_period_type_code = 'FY'
  AND   cf.period_end_date <= DATE '2025-04-30'
  AND   TIMESTAMP '2025-04-30 23:59:59' BETWEEN cf.valid_from_ts AND cf.valid_to_ts
ORDER BY cf.period_end_date DESC
LIMIT 3;
```

## 6. Known quirks

- `revenue_usd` is **always** translated at the period-end fix, even for
  income-statement items that arguably should use the period-average rate.
  Quant teams typically re-derive USD figures using average rates.
- Some early-emerging-market filings publish numbers in millions of local
  currency without flagging it; Worldscope normalises to units. If a value
  looks 1,000,000× off, suspect a unit mis-flag and file a vendor ticket.
- `audit_status_code = 'QUALIFIED'` or `'ADVERSE'` is the auditor's opinion,
  not a data-quality flag — never silently filter these out.
