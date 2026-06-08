# `lseg_ref.instrument_master` (+ `quote_master`, `ric_history`)

> **Domain:** Reference Data
> **Physical location:** `lseg_ref.instrument_master`, `lseg_ref.quote_master`, `lseg_ref.ric_history`
> **Source product:** Refinitiv Reference Data (DSS feed `RefDataPro_Instrument_v3`)
> **Update cadence:** Daily delta 06:00 NYT; full snapshot Saturday 22:00 NYT
> **Row volume (prod):** `instrument_master` ~14.2M rows; `quote_master` ~41.6M rows; `ric_history` ~63M rows
> **Grain:** see each table below
> **Partitioning:** `instrument_master` partitioned by `asset_class_code`; `quote_master` partitioned by `mic`

---

## A) `lseg_ref.instrument_master`

### A.1 Purpose

One row per **issued security per validity period** (SCD-2). Holds the
cross-references to ISIN, CUSIP, SEDOL, FIGI, plus asset-class metadata.
This is the bridge from instrument-level data (corporate actions, fixed-income
terms) to entity-level data (fundamentals, ESG).

### A.2 Grain & key

- **Grain:** one row per (`instrument_perm_id`, `valid_from_ts`).
- **Primary key:** (`instrument_perm_id`, `valid_from_ts`).

### A.3 Schema

| Column                       | Type           | Null | PK | Description                                                                                  |
| ---------------------------- | -------------- | ---- | -- | -------------------------------------------------------------------------------------------- |
| `instrument_perm_id`         | `BIGINT`       | NO   | ✅ | LSEG Instrument PermID. Immutable for the life of the security.                              |
| `valid_from_ts`              | `TIMESTAMP(6)` | NO   | ✅ | Inclusive UTC effective timestamp.                                                           |
| `valid_to_ts`                | `TIMESTAMP(6)` | NO   |    | Exclusive UTC superseded timestamp; sentinel `9999-12-31` if current.                        |
| `is_current`                 | `BOOLEAN`      | NO   |    | Convenience flag.                                                                            |
| `org_perm_id`                | `BIGINT`       | NO   |    | Issuer's `org_perm_id`. Joins to [`entity_master`](ENTITY_MASTER.md).                        |
| `asset_class_code`           | `VARCHAR(8)`   | NO   |    | One of `EQTY`, `PREF`, `BOND`, `CONV`, `WARRANT`, `ETF`, `FUND`, `FUT`, `OPT`, `IDX`, `FX`.  |
| `instrument_subtype_code`    | `VARCHAR(16)`  | YES  |    | E.g. `COMMON`, `ADR`, `GDR`, `CLASS_A`, `CLASS_C`, `MTN`, `SUKUK`, `ETF_PHYSICAL`, `ETF_SYNTH`. |
| `instrument_name`            | `VARCHAR(256)` | NO   |    | Display name, e.g. "Apple Inc - Common Stock".                                               |
| `currency_iso`               | `CHAR(3)`      | NO   |    | Denomination currency (ISO 4217). Joins to `lseg_ref.currency_ref`.                          |
| `country_of_issue_iso`       | `CHAR(2)`      | NO   |    | ISO 3166-1 alpha-2 of issuance jurisdiction.                                                 |
| `isin`                       | `CHAR(12)`     | YES  |    | International Securities Identification Number.                                              |
| `cusip`                      | `CHAR(9)`      | YES  |    | CUSIP — US/CA only.                                                                          |
| `composite_figi`             | `CHAR(12)`     | YES  |    | OpenFIGI composite (instrument-level FIGI).                                                  |
| `share_class_figi`           | `CHAR(12)`     | YES  |    | OpenFIGI share-class FIGI (above composite, for multi-share-class equity).                   |
| `issue_date`                 | `DATE`         | YES  |    | First issuance / IPO date.                                                                   |
| `maturity_date`              | `DATE`         | YES  |    | For fixed-income; NULL for equity/perpetual.                                                 |
| `coupon_rate_pct`            | `DECIMAL(9,6)` | YES  |    | For fixed-income; annualised %.                                                              |
| `coupon_frequency_code`      | `VARCHAR(8)`   | YES  |    | `ANNUAL`, `SEMI`, `QTR`, `MTHLY`, `ZERO`, `IRREG`.                                           |
| `face_value`                 | `DECIMAL(18,4)`| YES  |    | Par value per unit (fixed-income).                                                           |
| `shares_outstanding`         | `BIGINT`       | YES  |    | Latest reported. Equity only. Refreshed daily; use `lseg_dss.shares_outstanding_history` for PIT. |
| `instrument_status_code`     | `VARCHAR(16)`  | NO   |    | `ACTIVE`, `MATURED`, `CALLED`, `DEFAULTED`, `SUSPENDED`, `WITHDRAWN`.                        |
| `is_primary_security`        | `BOOLEAN`      | NO   |    | TRUE for the issuer's main equity line (used as default for company-level analytics).        |
| `cfi_code`                   | `CHAR(6)`      | YES  |    | ISO 10962 Classification of Financial Instruments code.                                      |
| `source_change_reason_code`  | `VARCHAR(32)`  | NO   |    | See `entity_master` §4 (same enumeration).                                                   |
| `loaded_ts`                  | `TIMESTAMP(6)` | NO   |    | EDL landing timestamp.                                                                       |

### A.4 Indexes

| Name                              | Columns                                              | Purpose                       |
| --------------------------------- | ---------------------------------------------------- | ----------------------------- |
| `pk_instrument_master`            | `(instrument_perm_id, valid_from_ts)`                | Primary key.                  |
| `ix_instrument_master_isin`       | `(isin)` WHERE `isin IS NOT NULL`                    | Lookup by ISIN.               |
| `ix_instrument_master_cusip`      | `(cusip)` WHERE `cusip IS NOT NULL`                  | Lookup by CUSIP.              |
| `ix_instrument_master_org_active` | `(org_perm_id)` WHERE `is_current = TRUE AND is_primary_security = TRUE` | Hot path. |
| `ix_instrument_master_figi`       | `(composite_figi)`                                   | FIGI cross-reference.         |

---

## B) `lseg_ref.quote_master`

### B.1 Purpose

One row per **listing of an instrument on a venue, per validity period** (SCD-2).
This is where pricing data joins back to reference.

### B.2 Grain & key

- **Grain:** one row per (`quote_perm_id`, `valid_from_ts`).
- **Primary key:** (`quote_perm_id`, `valid_from_ts`).

### B.3 Schema

| Column                  | Type           | Null | PK | Description                                                                                  |
| ----------------------- | -------------- | ---- | -- | -------------------------------------------------------------------------------------------- |
| `quote_perm_id`         | `BIGINT`       | NO   | ✅ | LSEG Quote PermID. Identifies the instrument-on-venue combination.                           |
| `valid_from_ts`         | `TIMESTAMP(6)` | NO   | ✅ | SCD-2 effective.                                                                             |
| `valid_to_ts`           | `TIMESTAMP(6)` | NO   |    | SCD-2 superseded.                                                                            |
| `is_current`            | `BOOLEAN`      | NO   |    |                                                                                              |
| `instrument_perm_id`    | `BIGINT`       | NO   |    | Joins to `instrument_master`.                                                                |
| `ric`                   | `VARCHAR(20)`  | NO   |    | Current Reuters Instrument Code. History in `ric_history`.                                   |
| `mic`                   | `CHAR(4)`      | NO   |    | ISO 10383 Market Identifier Code. Joins to `lseg_ref.exchange_ref`.                          |
| `trading_currency_iso`  | `CHAR(3)`      | NO   |    | The currency this listing trades in (can differ from `instrument_master.currency_iso`).      |
| `lot_size`              | `INTEGER`      | YES  |    | Round-lot size on this venue.                                                                |
| `tick_size_rule_code`   | `VARCHAR(32)`  | YES  |    | Reference to MiFID II tick-size regime where applicable.                                     |
| `is_primary_listing`    | `BOOLEAN`      | NO   |    | TRUE for the venue LSEG considers the canonical listing.                                     |
| `is_consolidated_tape`  | `BOOLEAN`      | NO   |    | TRUE if this `quote_perm_id` represents a consolidated/composite tape, not a single venue.   |
| `listing_date`          | `DATE`         | YES  |    | First trade date on this venue.                                                              |
| `delisting_date`        | `DATE`         | YES  |    | Last trade date on this venue.                                                               |
| `quote_status_code`     | `VARCHAR(16)`  | NO   |    | `ACTIVE`, `HALTED`, `SUSPENDED`, `DELISTED`, `WITHDRAWN`.                                    |
| `sedol`                 | `CHAR(7)`      | YES  |    | SEDOL — UK convention is listing-level, so it lives here, not on `instrument_master`.        |
| `exchange_ticker`       | `VARCHAR(16)`  | YES  |    | Native exchange ticker (e.g. `AAPL`, not `AAPL.OQ`).                                         |
| `figi`                  | `CHAR(12)`     | YES  |    | OpenFIGI exchange-level FIGI.                                                                |
| `loaded_ts`             | `TIMESTAMP(6)` | NO   |    |                                                                                              |

### B.4 Indexes

| Name                              | Columns                                              | Purpose                       |
| --------------------------------- | ---------------------------------------------------- | ----------------------------- |
| `pk_quote_master`                 | `(quote_perm_id, valid_from_ts)`                     | Primary key.                  |
| `ix_quote_master_ric_current`     | `(ric)` WHERE `is_current = TRUE`                    | Lookup by current RIC.        |
| `ix_quote_master_instrument`      | `(instrument_perm_id, is_current)`                   | All listings for a security.  |
| `ix_quote_master_primary`         | `(instrument_perm_id)` WHERE `is_primary_listing = TRUE AND is_current = TRUE` | Primary-listing fast path. |
| `ix_quote_master_sedol`           | `(sedol)` WHERE `sedol IS NOT NULL`                  | Lookup by SEDOL.              |

---

## C) `lseg_ref.ric_history`

### C.1 Purpose

Append-only audit table of every (`quote_perm_id`, `ric`) binding over time.
Necessary for any historical analysis that starts from a RIC string supplied
by a downstream user.

### C.2 Grain & key

- **Grain:** one row per (`quote_perm_id`, `ric`, `effective_from_date`).
- **Primary key:** (`quote_perm_id`, `effective_from_date`).

### C.3 Schema

| Column                  | Type           | Null | Description                                                              |
| ----------------------- | -------------- | ---- | ------------------------------------------------------------------------ |
| `quote_perm_id`         | `BIGINT`       | NO   | The stable identifier.                                                   |
| `ric`                   | `VARCHAR(20)`  | NO   | RIC string in effect during the band.                                    |
| `effective_from_date`   | `DATE`         | NO   | Inclusive.                                                               |
| `effective_to_date`     | `DATE`         | NO   | Exclusive. `9999-12-31` if current.                                      |
| `change_reason_code`    | `VARCHAR(32)`  | NO   | `INITIAL`, `TICKER_RENAME`, `EXCHANGE_MIGRATION`, `MARKET_REFORM`, `VENDOR_FIX`. |
| `loaded_ts`             | `TIMESTAMP(6)` | NO   |                                                                          |

---

## D) Sample queries

### D.1 ISIN → current primary listing RIC

```sql
SELECT  im.isin,
        im.instrument_name,
        qm.ric             AS primary_ric,
        qm.mic             AS primary_mic,
        qm.trading_currency_iso
FROM    lseg_ref.instrument_master im
JOIN    lseg_ref.quote_master      qm
  ON    qm.instrument_perm_id = im.instrument_perm_id
WHERE   im.isin = 'US0378331005'
  AND   im.is_current = TRUE
  AND   qm.is_current = TRUE
  AND   qm.is_primary_listing = TRUE;
```

### D.2 Resolve a historical RIC to today's RIC

```sql
SELECT  rh.ric              AS legacy_ric,
        qm.ric              AS current_ric,
        qm.quote_perm_id
FROM    lseg_ref.ric_history rh
JOIN    lseg_ref.quote_master qm
  ON    qm.quote_perm_id = rh.quote_perm_id
WHERE   rh.ric = 'FB.OQ'        -- the old Facebook RIC
  AND   DATE '2020-01-15'
        BETWEEN rh.effective_from_date AND rh.effective_to_date
  AND   qm.is_current = TRUE;
-- Returns: META.OQ
```

### D.3 All listings (global) for a company

```sql
SELECT  em.entity_common_name,
        im.instrument_name,
        qm.ric,
        qm.mic,
        ex.exchange_name,
        qm.trading_currency_iso,
        qm.is_primary_listing
FROM    lseg_ref.entity_master      em
JOIN    lseg_ref.instrument_master  im ON im.org_perm_id = em.org_perm_id
JOIN    lseg_ref.quote_master       qm ON qm.instrument_perm_id = im.instrument_perm_id
JOIN    lseg_ref.exchange_ref       ex ON ex.mic = qm.mic
WHERE   em.org_perm_id = 4295905573       -- Apple
  AND   em.is_current = TRUE
  AND   im.is_current = TRUE
  AND   im.asset_class_code = 'EQTY'
  AND   qm.is_current = TRUE
ORDER BY qm.is_primary_listing DESC, ex.exchange_name;
```

## E) Known quirks

- `is_primary_security` and `is_primary_listing` are two **different**
  judgements made by separate LSEG editorial teams; they are consistent
  ~99.7% of the time but you will occasionally see a primary security
  whose primary listing flag is on a secondary venue during reorganisations.
- SEDOLs are recycled by the LSE after 10+ years of inactivity. Always
  band-filter SEDOL lookups by date when going further back than that.
- For some Asian markets, `exchange_ticker` is numeric (e.g. `'0700'` for
  Tencent on HKEX). Always treat it as a string, never `CAST` to int.
