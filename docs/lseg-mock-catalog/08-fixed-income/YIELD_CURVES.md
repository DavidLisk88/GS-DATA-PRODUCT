# `lseg_fi.yield_curves_eod`

> **Domain:** Fixed Income — Yield Curves
> **Physical location:** `lseg_fi.yield_curves_eod`
> **Source product:** Refinitiv Yield Curves (RDP `curves/yield`)
> **Update cadence:** EOD per region (US 17:30 NYT, EMEA 17:30 LON, APAC 17:30 HKT) + intraday snapshots
> **Volume:** ~480 curves × ~daily × ~30 tenors → ~5M rows/yr
> **Grain:** one row per (`curve_code`, `curve_date`, `snapshot_code`, `tenor_code`)
> **Primary key:** above four columns
> **Partitioning:** `partition by curve_date_month`

---

## 1. Purpose

Standard discount + zero + par-yield curves for sovereigns, swaps,
inflation, and credit (CDS). Used for pricing, risk (DV01/KRD), and curve
construction tooling.

## 2. Schema

| Column                       | Type             | Null | PK | Description                                                                              |
| ---------------------------- | ---------------- | ---- | -- | ---------------------------------------------------------------------------------------- |
| `curve_code`                 | `VARCHAR(32)`    | NO   | ✅ | LSEG curve mnemonic, e.g. `USD_TSY`, `EUR_BUND`, `USD_SOFR_OIS`, `GBP_SONIA_OIS`, `EUR_CDS_IG_5Y`. See §3 (registry). |
| `curve_date`                 | `DATE`           | NO   | ✅ | Local valuation date of the curve.                                                       |
| `snapshot_code`              | `VARCHAR(16)`    | NO   | ✅ | `EOD`, `NY_3PM`, `LON_4PM`, `TOK_3PM`, `INTRA_HH` (half-hour intraday).                  |
| `tenor_code`                 | `VARCHAR(8)`     | NO   | ✅ | `1D`, `1W`, `1M`, `3M`, `6M`, `1Y`, `2Y`, …, `30Y`, `50Y`. (See §4 for full set.)        |
| `tenor_years`                | `DECIMAL(9,6)`   | NO   |    | Numeric representation of the tenor in years (e.g. `3M` → 0.25).                          |
| `currency_iso`               | `CHAR(3)`        | NO   |    |                                                                                          |
| `curve_type_code`            | `VARCHAR(16)`    | NO   |    | `SOVEREIGN`, `SWAP`, `OIS`, `INFLATION`, `CDS_SPREAD`, `MUNI`, `MMK_RATE`.               |
| `zero_rate_pct`              | `DECIMAL(12,8)`  | YES  |    | Continuously-compounded zero rate (%).                                                   |
| `par_yield_pct`              | `DECIMAL(12,8)`  | YES  |    | Par-yield (%).                                                                           |
| `discount_factor`            | `DECIMAL(20,12)` | YES  |    | Discount factor (P(0,T)).                                                                |
| `forward_rate_3m_pct`        | `DECIMAL(12,8)`  | YES  |    | Implied 3-month forward starting at `tenor_years`.                                       |
| `day_count_convention_code`  | `VARCHAR(16)`    | NO   |    | Curve convention.                                                                        |
| `interpolation_method_code`  | `VARCHAR(16)`    | NO   |    | `LINEAR_ZERO`, `LOGLIN_DF`, `CUBIC_SPLINE_ZERO`, `MONOTONIC_HERMITE`.                    |
| `is_bootstrapped`            | `BOOLEAN`        | NO   |    | TRUE if derived; FALSE if directly observed (e.g. fixings).                              |
| `vendor_received_ts`         | `TIMESTAMP(6)`   | NO   |    |                                                                                          |
| `loaded_ts`                  | `TIMESTAMP(6)`   | NO   |    |                                                                                          |

## 3. `curve_code` partial registry

| Curve code                  | Description                                  | Currency | Type        |
| --------------------------- | -------------------------------------------- | -------- | ----------- |
| `USD_TSY_OTR`               | US Treasury on-the-run sovereign curve       | USD      | SOVEREIGN   |
| `USD_TSY_PAR`               | US Treasury par-yield curve (CMT-style)      | USD      | SOVEREIGN   |
| `USD_TIPS`                  | US Treasury Inflation-Protected Securities   | USD      | INFLATION   |
| `USD_SOFR_OIS`              | USD SOFR OIS curve                           | USD      | OIS         |
| `USD_FED_FUNDS`             | Fed Funds curve                              | USD      | MMK_RATE    |
| `EUR_BUND`                  | German Bund sovereign curve                  | EUR      | SOVEREIGN   |
| `EUR_ESTR_OIS`              | €STR OIS curve                               | EUR      | OIS         |
| `EUR_HICPXT_LINKER`         | Euro HICP-ex-Tobacco inflation curve         | EUR      | INFLATION   |
| `GBP_GILT`                  | UK Gilt sovereign curve                      | GBP      | SOVEREIGN   |
| `GBP_SONIA_OIS`             | SONIA OIS curve                              | GBP      | OIS         |
| `JPY_JGB`                   | JGB sovereign curve                          | JPY      | SOVEREIGN   |
| `JPY_TONA_OIS`              | TONA OIS curve                               | JPY      | OIS         |
| `USD_CDX_IG_5Y`             | CDX IG 5Y index spread                       | USD      | CDS_SPREAD  |
| `EUR_ITRAXX_MAIN_5Y`        | iTraxx Main 5Y index spread                  | EUR      | CDS_SPREAD  |

## 4. Indexes

| Name                              | Definition                                                       |
| --------------------------------- | ---------------------------------------------------------------- |
| `pk_yield_curves_eod`             | `(curve_code, curve_date, snapshot_code, tenor_code)`            |
| `ix_yc_curve_date`                | `(curve_code, curve_date)`                                       |
| Partition                         | `RANGE (curve_date_month)`                                       |

## 5. Sample query

### 5.1 Pull the USD Treasury par-yield curve as of a date

```sql
SELECT  tenor_code, tenor_years, par_yield_pct
FROM    lseg_fi.yield_curves_eod
WHERE   curve_code    = 'USD_TSY_PAR'
  AND   curve_date    = DATE '2026-05-28'
  AND   snapshot_code = 'EOD'
ORDER BY tenor_years;
```

## 6. Known quirks

- For inactive curves (e.g. `USD_LIBOR_3M`), historical rows are retained but
  no new rows are added after cessation date — code in surveys that loop
  forward must tolerate missing recent dates.
- Negative rates DO occur (EUR/JPY through 2022); `DECIMAL` types preserve sign.
- The 3M forward field (`forward_rate_3m_pct`) at `tenor_code = '30Y'` is the
  forward starting at 30Y; the curve does not extrapolate beyond the longest
  observable tenor.
