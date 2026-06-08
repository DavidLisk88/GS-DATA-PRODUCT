# LSEG Enterprise Data Catalog — Overview (MOCK)

> **Document type:** Vendor product overview
> **Vendor:** London Stock Exchange Group plc (LSEG) — formerly Refinitiv post-2021
> **License tier:** Enterprise (firmwide, redistribution within legal entity permitted)
> **Catalog version:** `2026.05.r2`
> **Last updated:** 2026-05-28
> **Catalog owner:** Market Data Engineering, Goldman Sachs (internal contact: `gs-mde-lseg@gs.com`)
> **Vendor support:** LSEG My.Refinitiv portal, ticket queue `RDP-ENTERPRISE-GS`

---

## 1. What is covered by this catalog

This catalog documents every LSEG-sourced dataset that has been onboarded to the
firm's Enterprise Data Lake (EDL) under the namespace `lseg_*`. It does **not**
cover internal derived tables — those live in the `derived_*` namespace and are
documented separately.

## 2. Product → physical-dataset map

LSEG delivers data through several distribution channels. Each channel produces
one or more physical datasets in the lake. Knowing the channel matters because
it determines update cadence, point-in-time semantics, and how restatements arrive.

| LSEG Product (vendor name)           | Distribution                | Lake namespace           | Cadence              | PIT correctness |
| ------------------------------------ | --------------------------- | ------------------------ | -------------------- | --------------- |
| Refinitiv Data Platform (RDP)        | REST + streaming            | `lseg_rdp.*`             | Streaming → batch    | As-of effective |
| DataScope Select (DSS)               | SFTP bulk (gzip CSV)        | `lseg_dss.*`             | EOD T+0 by region    | Snapshot        |
| Tick History (RTH)                   | SFTP + HTTPS pull           | `lseg_tick.*`            | Intraday + EOD       | Point-in-time   |
| I/B/E/S Estimates                    | DSS feed (proprietary fmt)  | `lseg_ibes.*`            | Nightly + intraday   | Bitemporal      |
| Worldscope Fundamentals              | DSS feed                    | `lseg_wsf.*`             | Filing-driven        | Bitemporal      |
| StarMine Analytics                   | RDP API                     | `lseg_starmine.*`        | Daily                | Snapshot        |
| Lipper Fund Data                     | DSS feed                    | `lseg_lipper.*`          | Daily                | Snapshot        |
| ESG Scores (Refinitiv ESG)           | RDP API                     | `lseg_esg.*`             | Monthly refresh      | Bitemporal      |
| World-Check (KYC/AML)                | Secure API                  | `lseg_wc.*`              | Streaming            | As-of effective |
| FXall / FX Benchmarks (WM/Refinitiv) | Streaming + 4pm fix         | `lseg_fx.*`              | Intraday + fixings   | Point-in-time   |
| Refinitiv Reference Data             | DSS feed                    | `lseg_ref.*`             | Daily delta          | SCD-2           |

## 3. Domains in this catalog

For navigation, the catalog groups physical tables into logical **domains**.

| #  | Domain                | Folder                            | Anchor key(s)                   |
| -- | --------------------- | --------------------------------- | ------------------------------- |
| 01 | Identifiers & Entity  | [identifiers](01-identifiers-and-entity-model.md) | `org_perm_id`, `instrument_perm_id`, `quote_perm_id` |
| 02 | Reference Data        | [02-reference-data/](02-reference-data/)          | `instrument_perm_id`, `ric`     |
| 03 | Pricing               | [03-pricing/](03-pricing/)                        | `quote_perm_id`, `ric`          |
| 04 | Corporate Actions     | [04-corporate-actions/](04-corporate-actions/)    | `instrument_perm_id`, `ca_event_id` |
| 05 | Fundamentals          | [05-fundamentals/](05-fundamentals/)              | `org_perm_id`, `period_end_date` |
| 06 | I/B/E/S Estimates     | [06-estimates-ibes/](06-estimates-ibes/)          | `ibes_ticker`, `org_perm_id`    |
| 07 | ESG                   | [07-esg/](07-esg/)                                | `org_perm_id`                   |
| 99 | Cross-cutting         | [join cookbook](99-join-cookbook.md), [dictionary](99-data-dictionary.md) | — |

## 4. Service Level Agreement (SLA) summary

| Dataset family            | Availability target | Delivery SLA               | Backfill window |
| ------------------------- | ------------------- | -------------------------- | --------------- |
| `lseg_ref.*`              | 99.9%               | 06:00 NYT next business day| 30 days         |
| `lseg_dss.eod_pricing`    | 99.95%              | T+0 23:30 region-local     | 60 days         |
| `lseg_tick.*`             | 99.99%              | < 250ms p99 (streaming)    | 90 days         |
| `lseg_ibes.*`             | 99.5%               | 02:00 NYT nightly          | Full history    |
| `lseg_wsf.*`              | 99.5%               | Within 24h of filing       | Full history    |
| `lseg_esg.*`              | 99.0%               | 5th business day of month  | Full history    |

## 5. Restatement & survivorship policy

- **All reference-data tables are SCD Type 2.** Never use `WHERE current = TRUE`
  for historical queries — see [join cookbook §3](99-join-cookbook.md#3-point-in-time-correctness).
- **Pricing is restate-in-place** for prior-day corrections published in
  `lseg_dss.eod_pricing_corrections`. Always left-join corrections.
- **Fundamentals and estimates are bitemporal** — every row has both `period_end_date`
  (when it describes) and `valid_from_ts` (when LSEG knew it). PIT queries must
  filter on both.
- **De-listed instruments are retained** with `status_code IN ('INACTIVE','DELISTED')`.
  Survivorship-bias-free backtests must NOT filter these out.

## 6. Conventions used throughout this catalog

- All timestamps are stored UTC; columns suffixed `_ts` are `TIMESTAMP(6)`, columns
  suffixed `_date` are `DATE` (no time component).
- Monetary amounts are accompanied by an ISO 4217 `*_ccy` column; never assume USD.
- Nullability is explicit in every schema (`NOT NULL` if required).
- PII / restricted columns are tagged `[RESTRICTED]` and require entitlement
  `LSEG_WC_VIEWER` in the firm's IAM.

## 7. How to request a new dataset

Internal process (out of scope for this mock repo): file a `MDE-Onboarding` ticket
referencing the LSEG product code from §2.
