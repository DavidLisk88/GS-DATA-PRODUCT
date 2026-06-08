# `lseg_tick.tick_trades` and `lseg_tick.tick_quotes`

> **Domain:** Pricing — Intraday
> **Physical location:** `lseg_tick.tick_trades`, `lseg_tick.tick_quotes`
> **Source product:** Refinitiv Tick History (RTH)
> **Update cadence:** Streaming intraday (<250ms p99), EOD reconciliation 23:00 UTC
> **Row volume (prod):** `tick_trades` ~38B rows/year, `tick_quotes` ~410B rows/year
> **Grain:** one row per market event
> **Partitioning:** `partition by event_date` (daily); sub-cluster by `quote_perm_id`

> ⚠ Tick data is enormous. Always filter on `event_date` AND `quote_perm_id`
> before any other predicate. Unfiltered scans will be killed by query
> governance.

---

## A) `lseg_tick.tick_trades`

### A.1 Schema

| Column                  | Type            | Null | PK | Description                                                              |
| ----------------------- | --------------- | ---- | -- | ------------------------------------------------------------------------ |
| `quote_perm_id`         | `BIGINT`        | NO   | ✅ |                                                                          |
| `event_date`            | `DATE`          | NO   | ✅ | UTC date of `event_ts`. Partition key.                                   |
| `event_ts`              | `TIMESTAMP(9)`  | NO   | ✅ | Exchange timestamp (nanosecond precision where source supports it).      |
| `event_seq`             | `BIGINT`        | NO   | ✅ | Monotonic per-(`quote_perm_id`, `event_date`) sequence; resolves ties.   |
| `mic`                   | `CHAR(4)`       | NO   |    | Reporting venue MIC (may differ from `quote_master.mic` for inter-venue trades). |
| `trade_price`           | `DECIMAL(18,6)` | NO   |    |                                                                          |
| `trade_size`            | `BIGINT`        | NO   |    | Shares / contracts / face.                                               |
| `trade_currency_iso`    | `CHAR(3)`       | NO   |    |                                                                          |
| `trade_condition_codes` | `ARRAY<VARCHAR(8)>` | YES |    | Venue-specific condition codes (e.g. NASDAQ `'@'`, NYSE `'F'`).          |
| `is_off_book`           | `BOOLEAN`       | NO   |    | TRUE for OTC / SI / dark / cross trades.                                 |
| `is_late_print`         | `BOOLEAN`       | NO   |    | TRUE if reported out-of-sequence vs `event_ts`.                          |
| `vendor_received_ts`    | `TIMESTAMP(9)`  | NO   |    | When LSEG ingested.                                                      |
| `loaded_ts`             | `TIMESTAMP(6)`  | NO   |    |                                                                          |

### A.2 Primary key & indexes

| Name                    | Definition                                                       |
| ----------------------- | ---------------------------------------------------------------- |
| `pk_tick_trades`        | `(quote_perm_id, event_date, event_ts, event_seq)`               |
| Partition               | `RANGE (event_date)` — daily                                     |
| Z-order / cluster       | `(quote_perm_id, event_ts)`                                      |

---

## B) `lseg_tick.tick_quotes`

### B.1 Schema

| Column                 | Type            | Null | PK | Description                                                              |
| ---------------------- | --------------- | ---- | -- | ------------------------------------------------------------------------ |
| `quote_perm_id`        | `BIGINT`        | NO   | ✅ |                                                                          |
| `event_date`           | `DATE`          | NO   | ✅ |                                                                          |
| `event_ts`             | `TIMESTAMP(9)`  | NO   | ✅ |                                                                          |
| `event_seq`            | `BIGINT`        | NO   | ✅ |                                                                          |
| `mic`                  | `CHAR(4)`       | NO   |    |                                                                          |
| `bid_price`            | `DECIMAL(18,6)` | YES  |    |                                                                          |
| `bid_size`             | `BIGINT`        | YES  |    |                                                                          |
| `ask_price`            | `DECIMAL(18,6)` | YES  |    |                                                                          |
| `ask_size`             | `BIGINT`        | YES  |    |                                                                          |
| `quote_condition_code` | `VARCHAR(8)`    | YES  |    |                                                                          |
| `is_nbbo`              | `BOOLEAN`       | NO   |    | TRUE if this quote contributed to the prevailing NBBO at `event_ts`.     |
| `book_level`           | `SMALLINT`      | NO   |    | 1 = top of book. Entries with `book_level > 1` only present where L2 is licensed. |
| `vendor_received_ts`   | `TIMESTAMP(9)`  | NO   |    |                                                                          |
| `loaded_ts`            | `TIMESTAMP(6)`  | NO   |    |                                                                          |

## C) Sample queries

### C.1 First 100 trades of a session

```sql
SELECT  event_ts, trade_price, trade_size
FROM    lseg_tick.tick_trades
WHERE   quote_perm_id = 55839165994       -- AAPL.OQ
  AND   event_date    = DATE '2026-05-15'
ORDER BY event_ts, event_seq
LIMIT 100;
```

### C.2 1-minute OHLCV bars from ticks

```sql
SELECT  quote_perm_id,
        date_trunc('minute', event_ts)        AS bar_ts,
        MIN(trade_price)                      AS bar_low,
        MAX(trade_price)                      AS bar_high,
        FIRST_VALUE(trade_price) OVER w_first AS bar_open,
        LAST_VALUE(trade_price)  OVER w_last  AS bar_close,
        SUM(trade_size)                       AS bar_volume
FROM    lseg_tick.tick_trades
WHERE   quote_perm_id = 55839165994
  AND   event_date    = DATE '2026-05-15'
  AND   is_off_book   = FALSE
WINDOW  w_first AS (PARTITION BY date_trunc('minute', event_ts) ORDER BY event_ts, event_seq
                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING),
        w_last  AS (PARTITION BY date_trunc('minute', event_ts) ORDER BY event_ts, event_seq
                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING);
```

## D) Known quirks

- Some venues stamp trades to the millisecond, others to the nanosecond.
  Do not assume `event_ts` precision; use `event_seq` to break ties.
- For US equities, `mic` on `tick_trades` is the reporting venue (TRF for
  off-exchange), which is not the same as the listing venue. Join carefully.
- Cancelled / busted trades are removed from the table within T+1; if you
  cached intraday, reconcile against the EOD-loaded snapshot.
- L2 (`book_level > 1`) entitlement is enforced at the row level via the
  `LSEG_RTH_L2_VIEWER` IAM role; unauthorized queries see L1 only.
