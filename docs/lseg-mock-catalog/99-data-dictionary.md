# LSEG Catalog — Cross-Table Data Dictionary

> A flat dictionary of every column that appears in two or more catalog
> tables, plus the canonical glossary of business terms. Used by the AI
> assistant for synonym expansion during retrieval.

---

## A) Shared column glossary

| Column                          | Type            | Appears in                                                                                                       | Canonical meaning                                                                            |
| ------------------------------- | --------------- | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `org_perm_id`                   | `BIGINT`        | `entity_master`, `instrument_master`, `corporate_actions`, `company_fundamentals`, `ibes_ticker_xref`, `esg_scores` | LSEG Organisation PermID — immutable legal-entity identifier.                                |
| `instrument_perm_id`            | `BIGINT`        | `instrument_master`, `quote_master`, `corporate_actions`, `corporate_action_terms`                               | LSEG Instrument PermID — immutable issued-security identifier.                               |
| `quote_perm_id`                 | `BIGINT`        | `quote_master`, `eod_pricing`, `eod_pricing_corrections`, `tick_trades`, `tick_quotes`, `ric_history`            | LSEG Quote PermID — instrument-on-venue identifier.                                          |
| `ric`                           | `VARCHAR(20)`   | `quote_master`, `ric_history`, `eod_pricing.ric_as_of`                                                           | Reuters Instrument Code; can change over time.                                               |
| `isin`                          | `CHAR(12)`      | `instrument_master`, `ibes_ticker_xref.primary_isin`                                                             | ISO 6166 ISIN.                                                                               |
| `cusip`                         | `CHAR(9)`       | `instrument_master`                                                                                              | CUSIP — US/CA.                                                                               |
| `sedol`                         | `CHAR(7)`       | `quote_master`                                                                                                   | SEDOL — listing-level (not instrument-level).                                                |
| `lei`                           | `CHAR(20)`      | `entity_master`                                                                                                  | GLEIF Legal Entity Identifier.                                                               |
| `mic`                           | `CHAR(4)`       | `quote_master`, `eod_pricing`, `tick_trades`, `tick_quotes`, `exchange_ref`                                      | ISO 10383 Market Identifier Code.                                                            |
| `valid_from_ts` / `valid_to_ts` | `TIMESTAMP(6)`  | every SCD-2 table                                                                                                | Inclusive / exclusive validity band of an SCD-2 row.                                         |
| `is_current`                    | `BOOLEAN`       | every SCD-2 table                                                                                                | `valid_to_ts = '9999-12-31'`. Index hint only — do not use in historical PIT queries.        |
| `loaded_ts`                     | `TIMESTAMP(6)`  | every table                                                                                                      | When the row landed in the firm's EDL. ≠ vendor publish time.                                |
| `vendor_received_ts`            | `TIMESTAMP(6)`  | pricing, CA, ESG, fundamentals                                                                                   | When LSEG itself generated / received the data.                                              |
| `currency_iso`                  | `CHAR(3)`       | `currency_ref`, `instrument_master`, `eod_pricing.trading_currency_iso`, `ibes_ticker_xref.primary_currency_iso`, `company_fundamentals.report_currency_iso`, FX | ISO 4217 alphabetic currency code.                                                           |
| `country_iso`                   | `CHAR(2)`       | `entity_master.entity_country_iso`, `instrument_master.country_of_issue_iso`, `exchange_ref.country_iso`, `country_ref` | ISO 3166-1 alpha-2.                                                                          |
| `trbc_industry_code`            | `VARCHAR(10)`   | `entity_master`, `sector_classification`                                                                         | Leaf-level TRBC code (Activity, 10 digits).                                                  |
| `ibes_ticker`                   | `VARCHAR(8)`    | `ibes_ticker_xref`, `estimate_consensus`, `estimate_detail`                                                      | I/B/E/S ticker — per region; not equal to exchange ticker.                                   |
| `period_end_date`               | `DATE`          | `company_fundamentals`, `estimate_consensus`, `estimate_detail`, `esg_scores.score_period_end_date`              | Last calendar day of the reporting period.                                                   |

---

## B) Status / enumeration cross-reference

| Field & code                              | Means                                                                              |
| ----------------------------------------- | ---------------------------------------------------------------------------------- |
| `entity_status_code = 'ACTIVE'`           | Operating, securities tradeable.                                                   |
| `entity_status_code = 'MERGED'`           | Absorbed; see `successor_org_perm_id`.                                             |
| `instrument_status_code = 'MATURED'`      | Fixed-income reached maturity; no longer tradeable.                                |
| `quote_status_code = 'HALTED'`            | Trading temporarily suspended on this venue.                                       |
| `ca_event_status_code = 'WITHDRAWN'`      | CA was announced but cancelled — exclude from pricing adjustments.                 |
| `quality_flag_code = 'STALE'`             | Pricing row carries last good print due to halt or no-trade.                       |
| `quality_flag_code = 'CORRECTED'`         | Pricing row was restated; check `eod_pricing_corrections`.                         |
| `revision_direction_code = 'NEW'`         | Analyst initiated coverage with this estimate.                                     |
| `revision_direction_code = 'DROPPED'`     | Analyst dropped coverage.                                                          |

---

## C) Business term glossary

| Term                                  | Definition / mapping                                                                                                    |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Total return**                      | `(close_adj_price[t] / close_adj_price[t-1]) - 1` on `eod_pricing`.                                                     |
| **Price return**                      | As above but using `close_price` or `close_adj_split_only` (excludes dividends).                                        |
| **Free float**                        | Not in this mock catalog by default; supplemented by index-provider feeds. Coming soon: `lseg_ref.shares_free_float`.   |
| **Survivorship-bias-free universe**   | Include rows where `entity_status_code IN ('MERGED','LIQUIDATED','DISSOLVED','INACTIVE','SUSPENDED')` if active at as-of. |
| **Point-in-time (PIT)**               | Filter SCD-2 / bitemporal tables by `:as_of_ts BETWEEN valid_from_ts AND valid_to_ts` only.                             |
| **As-restated**                       | Use only `is_current_version = TRUE` (fundamentals/estimates) or `is_current = TRUE` (reference) for the snapshot view. |
| **Primary listing**                   | `quote_master.is_primary_listing = TRUE` — LSEG's choice of canonical venue.                                            |
| **Primary security**                  | `instrument_master.is_primary_security = TRUE` — LSEG's choice of the issuer's main share line.                         |
| **TERP (Theoretical Ex-Rights Price)**| Used to compute the adjustment factor for rights issues. See CORPORATE_ACTIONS §4.                                      |
| **Bitemporal**                        | Has both *valid time* (period_end_date) and *transaction time* (valid_from_ts) — fundamentals, estimates, ESG.          |
| **WMR fix**                           | WM/Refinitiv FX Benchmark; `WMR_LON_4PM` is the standard institutional reference rate.                                  |
| **EBITDA (in this catalog)**          | Computed by LSEG as `operating_income + depreciation + amortisation`; differs from issuer-disclosed "Adjusted EBITDA".  |
| **Restricted (`[RESTRICTED]`)**       | Column requires named IAM entitlement; default users see `NULL`.                                                        |
| **Consensus**                         | Pre-aggregated mean/median across active analyst estimates for a given measure/period.                                  |
| **Detail (estimate detail)**          | Analyst-level row per submission; only the most recent per analyst has `is_active = TRUE`.                              |
| **Scope 1/2/3 emissions**             | Direct / purchased-energy / value-chain GHG emissions per the GHG Protocol.                                             |

---

## D) Unit / scale conventions

- Monetary values are in **units** of `report_currency_iso` / `trading_currency_iso`,
  not thousands or millions. A USD revenue of `2.5e10` is $25 billion.
- Percentages are stored as percents (12.5, not 0.125), suffixed `_pct`.
- Basis points are stored as `_bps` and as integers.
- Volumes are in shares (equities), contracts (derivatives), or face value
  (fixed income — denominated in `trading_currency_iso`).
- Timestamps suffixed `_ts` are UTC; suffix `_local` indicates exchange-local.
- Dates suffixed `_date` are calendar dates with no time component.
