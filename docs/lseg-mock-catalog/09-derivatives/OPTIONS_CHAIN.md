# `lseg_drv.options_chain` and `lseg_drv.options_eod_iv`

> **Domain:** Derivatives — Equity / Index / ETF Options
> **Physical location:** `lseg_drv.options_chain`, `lseg_drv.options_eod_iv`
> **Source product:** Refinitiv Options (OPRA in US; equivalent feeds elsewhere)
> **Update cadence:** Daily reference + EOD greeks at 17:30 NYT
> **Volume:** `options_chain` ~120M live contracts; `options_eod_iv` ~85M rows/day
> **Grain (chain):** one row per `(instrument_perm_id, valid_from_ts)` SCD-2
> **Grain (eod_iv):** one row per `(instrument_perm_id, price_date)`

---

## 1. `lseg_drv.options_chain`

Reference for each individual option contract. Inherits from
`instrument_master` (`asset_class_code = 'OPT'`).

### 1.1 Schema

| Column                       | Type             | Null | PK | Description                                                                              |
| ---------------------------- | ---------------- | ---- | -- | ---------------------------------------------------------------------------------------- |
| `instrument_perm_id`         | `BIGINT`         | NO   | ✅ |                                                                                          |
| `valid_from_ts`              | `TIMESTAMP(6)`   | NO   | ✅ |                                                                                          |
| `valid_to_ts`                | `TIMESTAMP(6)`   | NO   |    |                                                                                          |
| `is_current`                 | `BOOLEAN`        | NO   |    |                                                                                          |
| `underlying_instrument_perm_id` | `BIGINT`      | NO   |    | The deliverable / referenced equity/ETF/index.                                           |
| `option_type_code`           | `CHAR(1)`        | NO   |    | `C` (call) or `P` (put).                                                                 |
| `exercise_style_code`        | `VARCHAR(8)`     | NO   |    | `AMER`, `EURO`, `BERM`.                                                                  |
| `settlement_type_code`       | `VARCHAR(8)`     | NO   |    | `PHYSICAL` (most equities), `CASH` (most index options).                                 |
| `strike_price`               | `DECIMAL(18,6)`  | NO   |    | In `currency_iso`.                                                                       |
| `expiration_date`            | `DATE`           | NO   |    |                                                                                          |
| `expiration_style_code`      | `VARCHAR(16)`    | NO   |    | `STANDARD` (3rd Fri), `WEEKLY`, `EOM`, `QUARTERLY`, `LEAPS`, `MINI`, `MICRO`.            |
| `contract_size`              | `INTEGER`        | NO   |    | Underlying units per contract (US equities default = 100; adjustments can change this).  |
| `currency_iso`               | `CHAR(3)`        | NO   |    |                                                                                          |
| `mic`                        | `CHAR(4)`        | NO   |    | Primary listing venue.                                                                   |
| `osi_symbol`                 | `VARCHAR(21)`    | NO   |    | OCC OSI standard symbol (US options); free-form for non-US.                              |
| `is_adjusted`                | `BOOLEAN`        | NO   |    | TRUE if contract size / strike modified by a CA (split, special div).                    |
| `is_active`                  | `BOOLEAN`        | NO   |    | FALSE after expiration.                                                                  |
| `loaded_ts`                  | `TIMESTAMP(6)`   | NO   |    |                                                                                          |

## 2. `lseg_drv.options_eod_iv`

EOD greeks + implied vol. Pre-computed by LSEG using Black-Scholes-Merton
with the listing's risk-free curve and the underlying's borrow rate.

### 2.1 Schema

| Column                  | Type             | Null | PK | Description                                                              |
| ----------------------- | ---------------- | ---- | -- | ------------------------------------------------------------------------ |
| `instrument_perm_id`    | `BIGINT`         | NO   | ✅ |                                                                          |
| `price_date`            | `DATE`           | NO   | ✅ |                                                                          |
| `underlying_close`      | `DECIMAL(18,6)`  | YES  |    | Reference underlying close used.                                         |
| `option_close`          | `DECIMAL(18,6)`  | YES  |    |                                                                          |
| `bid_close`             | `DECIMAL(18,6)`  | YES  |    |                                                                          |
| `ask_close`             | `DECIMAL(18,6)`  | YES  |    |                                                                          |
| `volume`                | `BIGINT`         | YES  |    | Contracts.                                                               |
| `open_interest`         | `BIGINT`         | YES  |    | Reported by venue T+1.                                                   |
| `implied_vol_pct`       | `DECIMAL(9,6)`   | YES  |    | Annualised IV (%).                                                       |
| `delta`                 | `DECIMAL(9,6)`  | YES  |    |                                                                          |
| `gamma`                 | `DECIMAL(12,8)` | YES  |    |                                                                          |
| `vega`                  | `DECIMAL(12,8)` | YES  |    |                                                                          |
| `theta`                 | `DECIMAL(12,8)` | YES  |    |                                                                          |
| `rho`                   | `DECIMAL(12,8)` | YES  |    |                                                                          |
| `risk_free_rate_pct`    | `DECIMAL(9,6)`  | YES  |    | Curve used (`USD_SOFR_OIS` at tenor matched to expiration).              |
| `borrow_rate_pct`       | `DECIMAL(9,6)`  | YES  |    | For equity options.                                                      |
| `dividend_yield_pct`    | `DECIMAL(9,6)`  | YES  |    | Forward dividend yield assumption.                                       |
| `pricing_model_code`    | `VARCHAR(16)`   | NO   |    | `BSM`, `BS`, `BAW` (Barone-Adesi-Whaley for American calls on divs).     |
| `quality_flag_code`     | `VARCHAR(16)`   | NO   |    | `OK`, `NO_QUOTE`, `WIDE_SPREAD`, `MODELLED`.                             |
| `loaded_ts`             | `TIMESTAMP(6)`  | NO   |    |                                                                          |

## 3. Sample queries

### 3.1 Build the AAPL call IV smile for the nearest expiration

```sql
WITH nearest_expiry AS (
    SELECT MIN(expiration_date) AS exp_date
    FROM   lseg_drv.options_chain
    WHERE  underlying_instrument_perm_id = 8590932301        -- AAPL common
      AND  is_current = TRUE
      AND  expiration_date >= CURRENT_DATE
      AND  expiration_style_code = 'STANDARD'
)
SELECT  oc.strike_price,
        oiv.implied_vol_pct,
        oiv.delta,
        oiv.open_interest
FROM    lseg_drv.options_chain         oc
JOIN    lseg_drv.options_eod_iv        oiv USING (instrument_perm_id)
JOIN    nearest_expiry                 ne  ON oc.expiration_date = ne.exp_date
WHERE   oc.underlying_instrument_perm_id = 8590932301
  AND   oc.option_type_code = 'C'
  AND   oc.is_current = TRUE
  AND   oiv.price_date = DATE '2026-05-28'
ORDER BY oc.strike_price;
```

## 4. Known quirks

- Adjusted contracts (`is_adjusted = TRUE`) often have non-standard
  `contract_size` (e.g. 110 after a 10% stock dividend); never assume 100.
- Weekly options have very thin volume on most names; `open_interest` from
  the OPRA feed lags by one trading day.
- Index options (SPX, NDX) are European/cash-settled even though their
  underlying is observed every minute; do not use early-exercise models.
