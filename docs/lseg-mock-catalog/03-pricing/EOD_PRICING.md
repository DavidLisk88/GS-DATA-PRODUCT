# `lseg_dss.eod_pricing` (+ `eod_pricing_corrections`)

> **Domain:** Pricing
> **Physical location:** `lseg_dss.eod_pricing`, `lseg_dss.eod_pricing_corrections`
> **Source product:** DataScope Select — EOD Pricing v4 feed
> **Update cadence:** EOD T+0 by region (US 23:30 NYT, EMEA 21:30 LON, APAC 19:30 HKT)
> **Row volume (prod):** ~2.3B rows (~750k securities × ~10y of trading days)
> **Grain:** one row per (`quote_perm_id`, `price_date`)
> **Primary key:** (`quote_perm_id`, `price_date`)
> **Partitioning:** `partition by price_date` (monthly granularity), cluster by `quote_perm_id`

---

## 1. Purpose

Official end-of-day pricing — open, high, low, close (OHLC), volume, VWAP, and
adjusted variants. The canonical pricing table for marking books, valuing
positions, computing returns, and feeding risk models.

Pricing is **listing-level**, not instrument-level — a single security trading
on multiple venues has one row per venue per day.

## 2. Schema

| Column                       | Type            | Null | PK | Description                                                                              |
| ---------------------------- | --------------- | ---- | -- | ---------------------------------------------------------------------------------------- |
| `quote_perm_id`              | `BIGINT`        | NO   | ✅ | Joins to [`quote_master`](../02-reference-data/INSTRUMENT_MASTER.md#b-lseg_refquote_master). |
| `price_date`                 | `DATE`          | NO   | ✅ | Local trading date on the listing's venue (NOT UTC date).                                |
| `ric_as_of`                  | `VARCHAR(20)`   | NO   |    | Snapshot of the RIC string in effect on `price_date`. Provided for convenience.          |
| `mic`                        | `CHAR(4)`       | NO   |    | Venue MIC. Snapshot at `price_date`.                                                     |
| `trading_currency_iso`       | `CHAR(3)`       | NO   |    | Currency the price is expressed in.                                                      |
| `open_price`                 | `DECIMAL(18,6)` | YES  |    | Opening trade price (regular session). NULL if no opening print.                         |
| `high_price`                 | `DECIMAL(18,6)` | YES  |    |                                                                                          |
| `low_price`                  | `DECIMAL(18,6)` | YES  |    |                                                                                          |
| `close_price`                | `DECIMAL(18,6)` | YES  |    | Official closing price per venue rules (auction close where available).                  |
| `last_trade_price`           | `DECIMAL(18,6)` | YES  |    | Last print of the regular session; can differ from `close_price` on auction venues.      |
| `bid_close`                  | `DECIMAL(18,6)` | YES  |    | Closing bid (NBBO or venue-best).                                                        |
| `ask_close`                  | `DECIMAL(18,6)` | YES  |    | Closing ask.                                                                             |
| `mid_close`                  | `DECIMAL(18,6)` | YES  |    | `(bid_close + ask_close) / 2` if both populated, else NULL.                              |
| `vwap`                       | `DECIMAL(18,6)` | YES  |    | Volume-weighted average price for the regular session.                                   |
| `volume`                     | `BIGINT`        | YES  |    | Shares (equity) / contracts (derivatives) / face amount (FI) traded in regular session.  |
| `trade_count`                | `INTEGER`       | YES  |    | Number of regular-session trades.                                                        |
| `turnover`                   | `DECIMAL(22,4)` | YES  |    | Notional traded in `trading_currency_iso`.                                               |
| `close_adj_price`            | `DECIMAL(18,6)` | YES  |    | Close adjusted for splits + dividends + spin-offs. Methodology: see §5.                  |
| `close_adj_split_only`       | `DECIMAL(18,6)` | YES  |    | Close adjusted for splits only (no cash-flow events).                                    |
| `cumulative_adj_factor`      | `DECIMAL(18,10)`| YES  |    | Cumulative back-adjustment multiplier; `close_adj_price = close_price * cumulative_adj_factor`. |
| `settlement_price`           | `DECIMAL(18,6)` | YES  |    | Derivatives only — exchange settlement price.                                            |
| `is_no_trade_day`            | `BOOLEAN`       | NO   |    | TRUE if venue was closed (holiday) OR security halted all day.                           |
| `is_estimated`               | `BOOLEAN`       | NO   |    | TRUE if any field was filled from a model (e.g. closing auction missed).                 |
| `quality_flag_code`          | `VARCHAR(16)`   | NO   |    | `OK`, `STALE`, `WIDE_SPREAD`, `LOW_VOLUME`, `CORRECTED`, `ESTIMATED`.                    |
| `vendor_received_ts`         | `TIMESTAMP(6)`  | NO   |    | When LSEG generated this record.                                                         |
| `loaded_ts`                  | `TIMESTAMP(6)`  | NO   |    | When the row landed in EDL.                                                              |

## 3. Indexes / clustering

| Name                              | Definition                                              |
| --------------------------------- | ------------------------------------------------------- |
| `pk_eod_pricing`                  | `(quote_perm_id, price_date)`                           |
| Partition                         | `RANGE (price_date)` — one partition per calendar month |
| Cluster                           | `(quote_perm_id)` within partition                      |

## 4. `lseg_dss.eod_pricing_corrections` companion table

Restatements arrive up to T+5 (rarely later). They are stored as deltas, **not
applied in place**, so PIT queries that need "what we knew on the night of T"
can ignore them and "as-known-today" queries can left-join them.

| Column                | Type            | Null | Description                                                          |
| --------------------- | --------------- | ---- | -------------------------------------------------------------------- |
| `quote_perm_id`       | `BIGINT`        | NO   | Same key as base table.                                              |
| `price_date`          | `DATE`          | NO   |                                                                      |
| `correction_seq`      | `SMALLINT`      | NO   | 1, 2, … if multiple corrections to the same row.                     |
| `column_name`         | `VARCHAR(64)`   | NO   | Which column was corrected.                                          |
| `prior_value`         | `VARCHAR(64)`   | YES  | Stringified previous value.                                          |
| `corrected_value`     | `VARCHAR(64)`   | YES  | Stringified new value.                                               |
| `correction_reason`   | `VARCHAR(128)`  | NO   |                                                                      |
| `correction_received_ts` | `TIMESTAMP(6)`| NO   |                                                                      |
| `loaded_ts`           | `TIMESTAMP(6)`  | NO   |                                                                      |

Primary key: (`quote_perm_id`, `price_date`, `correction_seq`, `column_name`).

## 5. Adjusted-price methodology

`close_adj_price` is back-adjusted using the standard CRSP-style multiplicative
methodology:

```
close_adj_price(t) = close_price(t) × Π_{e: ex_date(e) > t} factor(e)
```

where `factor(e)` is:

| Corporate action               | Factor                                                |
| ------------------------------ | ----------------------------------------------------- |
| Cash dividend                  | `1 - dividend_amount / close_price(ex_date - 1)`      |
| Stock split (N-for-1)          | `1 / N`                                               |
| Reverse split (1-for-N)        | `N`                                                   |
| Stock dividend (N%)            | `1 / (1 + N/100)`                                     |
| Spin-off                       | `1 - (spinoff_value / close_price(ex_date - 1))`      |
| Rights issue                   | TERP-based factor (see [`CORPORATE_ACTIONS`](../04-corporate-actions/CORPORATE_ACTIONS.md) §4) |

`close_adj_split_only` excludes cash-dividend factors (useful for technical
indicators that should not be polluted by income events).

## 6. Sample queries

### 6.1 Total-return time series for AAPL on primary listing

```sql
SELECT  p.price_date,
        p.close_price,
        p.close_adj_price,
        p.volume
FROM    lseg_dss.eod_pricing  p
JOIN    lseg_ref.quote_master qm
  ON    qm.quote_perm_id = p.quote_perm_id
WHERE   qm.ric                = 'AAPL.OQ'
  AND   qm.is_current         = TRUE
  AND   qm.is_primary_listing = TRUE
  AND   p.price_date BETWEEN DATE '2020-01-01' AND DATE '2025-12-31'
ORDER BY p.price_date;
```

### 6.2 Apply outstanding corrections to a snapshot

```sql
SELECT  p.quote_perm_id,
        p.price_date,
        COALESCE(c.corrected_value::DECIMAL(18,6), p.close_price) AS close_price_corrected
FROM    lseg_dss.eod_pricing                p
LEFT JOIN lseg_dss.eod_pricing_corrections  c
  ON    c.quote_perm_id = p.quote_perm_id
  AND   c.price_date    = p.price_date
  AND   c.column_name   = 'close_price'
  AND   c.correction_seq = (
            SELECT MAX(correction_seq)
            FROM   lseg_dss.eod_pricing_corrections c2
            WHERE  c2.quote_perm_id = p.quote_perm_id
              AND  c2.price_date    = p.price_date
              AND  c2.column_name   = 'close_price'
        )
WHERE   p.price_date = DATE '2026-03-14';
```

## 7. Known quirks

- For US securities the `price_date` of the **regular session** may differ
  from after-hours; this table reflects regular session only.
- `vwap` on low-volume names will sometimes equal `close_price` exactly when
  there was only one trade — not a data error.
- Adjusted prices are **back-adjusted continuously**: if a new corporate
  action lands today, every historical row's `close_adj_price` changes. Do
  not cache adjusted prices across loads without versioning.
- For halted securities, `volume = 0`, `close_price` carries the last good
  print, and `quality_flag_code = 'STALE'`.
