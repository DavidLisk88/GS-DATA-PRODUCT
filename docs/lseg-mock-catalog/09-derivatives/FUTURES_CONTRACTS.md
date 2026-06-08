# `lseg_drv.futures_contracts`

> **Domain:** Derivatives — Futures
> **Physical location:** `lseg_drv.futures_contracts`, `lseg_drv.futures_series_chain`
> **Source product:** Refinitiv Derivatives Reference (RDP `derivatives/futures`)
> **Update cadence:** Daily delta 06:00 NYT (new listings / expirations)
> **Volume:** `futures_contracts` ~1.2M (incl. expired); `futures_series_chain` ~2,400 active series
> **Grain:** one row per (`instrument_perm_id`, `valid_from_ts`) — SCD-2

---

## 1. Two-table model

```
┌─────────────────────────────┐
│  futures_series_chain       │  Series = the "ZN" 10-year T-Note future "concept"
│  futures_series_code  (PK)  │
└──────────────┬──────────────┘
               │ 1 : N
┌──────────────▼──────────────┐
│  futures_contracts          │  Contract = the specific Mar-2026 (ZNH6) listing
│  instrument_perm_id  (PK)   │
└─────────────────────────────┘
```

Each tradeable contract is a distinct `instrument_perm_id` (so it gets its
own pricing / corp actions / etc.) but inherits non-time-varying metadata
from its **series**.

## 2. `lseg_drv.futures_series_chain`

### 2.1 Schema

| Column                       | Type             | Null | PK | Description                                                              |
| ---------------------------- | ---------------- | ---- | -- | ------------------------------------------------------------------------ |
| `futures_series_code`        | `VARCHAR(16)`    | NO   | ✅ | LSEG mnemonic, e.g. `ZN`, `ES`, `BR`, `GC`, `CL`.                        |
| `valid_from_ts`              | `TIMESTAMP(6)`   | NO   | ✅ | SCD-2.                                                                   |
| `valid_to_ts`                | `TIMESTAMP(6)`   | NO   |    |                                                                          |
| `is_current`                 | `BOOLEAN`        | NO   |    |                                                                          |
| `series_name`                | `VARCHAR(128)`   | NO   |    | "CBOT 10-Year US Treasury Note Future".                                  |
| `mic`                        | `CHAR(4)`        | NO   |    | Listing venue.                                                           |
| `underlying_type_code`       | `VARCHAR(16)`    | NO   |    | `EQUITY`, `INDEX`, `RATE`, `FX`, `COMMODITY`, `BOND`, `CRYPTO`.          |
| `underlying_perm_id`         | `BIGINT`         | YES  |    | When underlying is a single name/index in LSEG ID-space.                 |
| `underlying_descriptor`      | `VARCHAR(128)`   | YES  |    | Free-form when no LSEG ID (e.g. "WTI Crude Oil").                        |
| `currency_iso`               | `CHAR(3)`        | NO   |    |                                                                          |
| `contract_multiplier`        | `DECIMAL(18,8)`  | NO   |    | Notional per 1.00 price move (e.g. ES = $50, ZN = $1000 per 1pt).        |
| `min_price_increment`        | `DECIMAL(18,8)`  | NO   |    | Tick size (e.g. ZN = 1/64 of 1% = 0.015625).                             |
| `tick_value`                 | `DECIMAL(18,8)`  | NO   |    | Cash value of a single tick.                                             |
| `settlement_type_code`       | `VARCHAR(16)`    | NO   |    | `PHYSICAL`, `CASH`, `CASH_PHYSICAL`.                                     |
| `trading_session_code`       | `VARCHAR(16)`    | NO   |    | `RTH`, `ETH`, `GLOBEX`, `T_PLUS_1`.                                      |
| `is_active_series`           | `BOOLEAN`        | NO   |    | FALSE if series delisted (e.g. legacy Eurodollar after cessation).       |
| `loaded_ts`                  | `TIMESTAMP(6)`   | NO   |    |                                                                          |

## 3. `lseg_drv.futures_contracts`

### 3.1 Schema

| Column                       | Type             | Null | PK | Description                                                                             |
| ---------------------------- | ---------------- | ---- | -- | --------------------------------------------------------------------------------------- |
| `instrument_perm_id`         | `BIGINT`         | NO   | ✅ | Inherits from `instrument_master` (`asset_class_code = 'FUT'`).                         |
| `valid_from_ts`              | `TIMESTAMP(6)`   | NO   | ✅ |                                                                                         |
| `valid_to_ts`                | `TIMESTAMP(6)`   | NO   |    |                                                                                         |
| `is_current`                 | `BOOLEAN`        | NO   |    |                                                                                         |
| `futures_series_code`        | `VARCHAR(16)`    | NO   |    | FK to `futures_series_chain`.                                                           |
| `contract_month_year`        | `CHAR(5)`        | NO   |    | `MMMYY` style, e.g. `MAR26`, `JUN26`. Stored as string to allow non-standard cycles.    |
| `contract_letter_code`       | `CHAR(1)`        | NO   |    | F/G/H/J/K/M/N/Q/U/V/X/Z (CME month codes).                                              |
| `contract_year`              | `SMALLINT`       | NO   |    | 4-digit year.                                                                            |
| `first_trade_date`           | `DATE`           | YES  |    |                                                                                          |
| `last_trade_date`            | `DATE`           | NO   |    | Last day this contract is tradeable.                                                     |
| `expiration_date`            | `DATE`           | NO   |    | Settlement / delivery date (may differ from `last_trade_date`).                          |
| `first_notice_date`          | `DATE`           | YES  |    | Physical-settled commodities — first day longs can be assigned delivery.                 |
| `delivery_window_start`      | `DATE`           | YES  |    | Physical delivery start.                                                                 |
| `delivery_window_end`        | `DATE`           | YES  |    | Physical delivery end.                                                                   |
| `is_front_month`             | `BOOLEAN`        | NO   |    | TRUE for the current front-month contract in the chain.                                  |
| `is_active`                  | `BOOLEAN`        | NO   |    | FALSE after `expiration_date`.                                                           |
| `loaded_ts`                  | `TIMESTAMP(6)`   | NO   |    |                                                                                          |

## 4. Sample queries

### 4.1 Current front-month for the major series

```sql
SELECT  fs.futures_series_code,
        fs.series_name,
        im.instrument_name,
        fc.contract_month_year,
        fc.last_trade_date
FROM    lseg_drv.futures_contracts        fc
JOIN    lseg_drv.futures_series_chain     fs USING (futures_series_code)
JOIN    lseg_ref.instrument_master        im USING (instrument_perm_id)
WHERE   fc.is_front_month = TRUE
  AND   fc.is_current     = TRUE
  AND   fs.is_current     = TRUE
  AND   im.is_current     = TRUE;
```

### 4.2 Build a continuous front-month price series (roll on `last_trade_date`)

```sql
WITH front_month_history AS (
    SELECT  fc.futures_series_code,
            qm.quote_perm_id,
            fc.last_trade_date,
            LAG(fc.last_trade_date) OVER (PARTITION BY fc.futures_series_code ORDER BY fc.last_trade_date) AS prev_last_trade
    FROM    lseg_drv.futures_contracts fc
    JOIN    lseg_ref.quote_master      qm
      ON    qm.instrument_perm_id = fc.instrument_perm_id
      AND   qm.is_primary_listing = TRUE
      AND   qm.is_current = TRUE
    WHERE   fc.futures_series_code = 'ES'
      AND   fc.is_current = TRUE
)
SELECT  p.price_date,
        h.futures_series_code,
        p.close_price
FROM    front_month_history h
JOIN    lseg_dss.eod_pricing p
  ON    p.quote_perm_id = h.quote_perm_id
  AND   p.price_date BETWEEN COALESCE(h.prev_last_trade, DATE '1900-01-01') + INTERVAL '1' DAY
                         AND h.last_trade_date
ORDER BY p.price_date;
```

## 5. Known quirks

- Some exchanges (e.g. ICE) use non-standard month codes; the `contract_letter_code`
  is the de-facto CME convention LSEG normalises everyone to.
- The "front month" can switch mid-day on roll dates; `is_front_month` is set
  at EOD so intraday consumers should compute their own rolling logic.
- Physical-settled grain futures often have a delivery window spanning the
  whole month; `last_trade_date` is the right field for backtests.
