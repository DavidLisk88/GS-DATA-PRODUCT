# `lseg_fx.fx_rates_eod` and `lseg_fx.fx_rates_intraday`

> **Domain:** Pricing — FX
> **Source product:** WM/Refinitiv FX Benchmarks + Refinitiv Spot FX
> **Update cadence:** EOD: WM/R 4pm London fix daily. Intraday: streaming.
> **Volume:** EOD ~160 currency pairs × ~daily; intraday ~50M rows/day
> **Grain (EOD):** one row per (`base_ccy`, `quote_ccy`, `fix_date`, `fix_code`)
> **Grain (intraday):** one row per market event per pair

---

## A) `lseg_fx.fx_rates_eod`

### A.1 Schema

| Column                 | Type            | Null | PK | Description                                                              |
| ---------------------- | --------------- | ---- | -- | ------------------------------------------------------------------------ |
| `base_ccy`             | `CHAR(3)`       | NO   | ✅ | ISO 4217 base currency.                                                  |
| `quote_ccy`            | `CHAR(3)`       | NO   | ✅ | ISO 4217 quote currency.                                                 |
| `fix_date`             | `DATE`          | NO   | ✅ | Local date of the fixing.                                                |
| `fix_code`             | `VARCHAR(16)`   | NO   | ✅ | One of `WMR_LON_4PM`, `WMR_LON_1130`, `WMR_NY_10AM`, `WMR_TOK_10AM`, `ECB_REF`. |
| `mid_rate`             | `DECIMAL(20,10)`| NO   |    | Mid-market rate; price of 1 `base_ccy` in `quote_ccy`.                   |
| `bid_rate`             | `DECIMAL(20,10)`| YES  |    | Available for WM/R fixings only.                                         |
| `ask_rate`             | `DECIMAL(20,10)`| YES  |    |                                                                          |
| `is_cross_rate`        | `BOOLEAN`       | NO   |    | TRUE if computed via USD triangulation rather than directly observed.    |
| `quality_flag_code`    | `VARCHAR(16)`   | NO   |    | `OK`, `THIN_LIQUIDITY`, `RESTRICTED`, `INFERRED`.                        |
| `vendor_received_ts`   | `TIMESTAMP(6)`  | NO   |    |                                                                          |
| `loaded_ts`            | `TIMESTAMP(6)`  | NO   |    |                                                                          |

## B) `lseg_fx.fx_rates_intraday`

| Column                 | Type            | Null | PK | Description                                                              |
| ---------------------- | --------------- | ---- | -- | ------------------------------------------------------------------------ |
| `base_ccy`             | `CHAR(3)`       | NO   | ✅ |                                                                          |
| `quote_ccy`            | `CHAR(3)`       | NO   | ✅ |                                                                          |
| `event_ts`             | `TIMESTAMP(9)`  | NO   | ✅ |                                                                          |
| `bid_rate`             | `DECIMAL(20,10)`| YES  |    |                                                                          |
| `ask_rate`             | `DECIMAL(20,10)`| YES  |    |                                                                          |
| `mid_rate`             | `DECIMAL(20,10)`| NO   |    | `(bid+ask)/2` or last good mid if one side missing.                      |
| `liquidity_provider`   | `VARCHAR(32)`   | YES  |    | Anonymised LP tag where available.                                       |
| `vendor_received_ts`   | `TIMESTAMP(9)`  | NO   |    |                                                                          |

## C) Sample queries

### C.1 Convert a USD revenue to EUR at the date's WM/R 4pm fix

```sql
SELECT  cf.org_perm_id,
        cf.period_end_date,
        cf.revenue_usd,
        cf.revenue_usd / fx.mid_rate AS revenue_eur
FROM    lseg_wsf.company_fundamentals cf
JOIN    lseg_fx.fx_rates_eod          fx
  ON    fx.base_ccy = 'EUR'
  AND   fx.quote_ccy = 'USD'
  AND   fx.fix_date  = cf.period_end_date
  AND   fx.fix_code  = 'WMR_LON_4PM'
WHERE   cf.fiscal_period_type_code = 'FY'
  AND   cf.period_end_date = DATE '2025-12-31';
```

### C.2 Cross-rate computation (when direct pair is unavailable)

```sql
-- Compute TRY/MXN by triangulation via USD
SELECT  a.fix_date,
        (a.mid_rate / b.mid_rate) AS try_mxn_mid
FROM    lseg_fx.fx_rates_eod a
JOIN    lseg_fx.fx_rates_eod b
  ON    a.fix_date = b.fix_date
  AND   a.fix_code = b.fix_code
WHERE   a.base_ccy = 'USD' AND a.quote_ccy = 'MXN'
  AND   b.base_ccy = 'USD' AND b.quote_ccy = 'TRY'
  AND   a.fix_code = 'WMR_LON_4PM'
  AND   a.fix_date BETWEEN DATE '2026-01-01' AND DATE '2026-05-31';
```

## D) Known quirks

- Some restricted (capital-controlled) currencies — VES, ARS, IRR — have
  `quality_flag_code = 'RESTRICTED'` and the rate is the official rather
  than parallel market.
- Direct pairs are observed only for the ~70 most liquid combinations; all
  others are flagged `is_cross_rate = TRUE` and triangulated via USD.
- On half-day sessions, the WM/R 4pm fix may not exist; expect `NULL` and
  fall back to `WMR_LON_1130`.
