# Identifiers & Entity Model

> **Domain:** Cross-cutting foundation. Read this **before** any other catalog page.
> **Owner:** Reference Data Engineering
> **Mock vendor source:** LSEG PermID Open Identifier System + Refinitiv Reference Data

This page explains the identifier hierarchy that every other table in the catalog
joins on. ~80% of "why doesn't my join work?" tickets reduce to confusing one
of these IDs for another.

---

## 1. The four-level PermID hierarchy

LSEG's Permanent Identifier (PermID) is a 10-digit (sometimes longer) numeric
opaque key that is **never reused** and **never changes** for the life of the
real-world entity it points to. There are four kinds of PermID, in a strict
parent-child hierarchy:

```
                ┌─────────────────────────┐
                │  Organisation PermID    │   Real-world legal entity
                │      org_perm_id        │   (e.g. Apple Inc., 4295905573)
                └────────────┬────────────┘
                             │ 1 : many
                ┌────────────▼────────────┐
                │   Instrument PermID     │   Issued security
                │   instrument_perm_id    │   (e.g. AAPL common stock, 8590932301)
                └────────────┬────────────┘
                             │ 1 : many
                ┌────────────▼────────────┐
                │      Quote PermID       │   Listing on a specific venue
                │     quote_perm_id       │   (e.g. AAPL on NASDAQ, 55839165994)
                └────────────┬────────────┘
                             │ 1 : 1 (current)
                ┌────────────▼────────────┐
                │  Reuters Instrument Code│   Display ticker
                │           ric           │   ("AAPL.OQ")
                └─────────────────────────┘
```

### 1.1 Organisation PermID (`org_perm_id`)

- Identifies a **legal entity**, not a security.
- Anchor for: fundamentals, ESG, I/B/E/S estimates, ownership data, World-Check.
- A holding company and its operating subsidiary are **different** `org_perm_id`s.
- `org_perm_id` of an acquired company is **not retired** after M&A — instead its
  `entity_status_code` becomes `MERGED` and `successor_org_perm_id` is populated.

### 1.2 Instrument PermID (`instrument_perm_id`)

- Identifies a **security issued by an organisation** (equity share class,
  specific bond ISIN, ETF, fund, future, option, etc.).
- One company can have many instruments: Alphabet has `GOOG` (Class C) and
  `GOOGL` (Class A) as two distinct `instrument_perm_id`s tied to the **same**
  `org_perm_id`.
- Anchor for: corporate actions, instrument-level reference, ISIN/CUSIP/SEDOL/FIGI.

### 1.3 Quote PermID (`quote_perm_id`)

- Identifies a **specific listing** of an instrument on a **specific venue**.
- AAPL trades on NASDAQ, Frankfurt, Mexico → three `quote_perm_id`s, one
  `instrument_perm_id`.
- Anchor for: pricing (EOD and tick), trading-status flags, MIC codes.
- The **primary listing** flag (`is_primary_listing`) distinguishes the venue
  LSEG considers canonical for valuation purposes.

### 1.4 RIC (`ric`)

- Reuters Instrument Code — the human-readable string (`"AAPL.OQ"`, `"VOD.L"`,
  `"BMW.DE"`).
- **RICs can change** (e.g. ticker rename, exchange migration). The historical
  RIC of a `quote_perm_id` is preserved in `lseg_ref.ric_history`.
- ⚠ Do not use RIC as a join key in historical analysis. Use `quote_perm_id`.

---

## 2. External (non-LSEG) identifiers

These are industry-standard identifiers that LSEG cross-references onto its
own keys. Every external ID is **versioned per `instrument_perm_id` over time**
because ISINs/CUSIPs/SEDOLs themselves can change (re-incorporation, share
class consolidation, etc.).

| Column        | Format               | Issued by              | Scope                    | Notes |
| ------------- | -------------------- | ---------------------- | ------------------------ | ----- |
| `isin`        | 12 chars, alphanumeric (e.g. `US0378331005`) | National Numbering Agencies via ANNA | Per issued security (instrument-level) | Global; recommended primary external ID. |
| `cusip`       | 9 chars (e.g. `037833100`) | CUSIP Global Services (US) | US/CA securities | First 6 chars = issuer; chars 7–8 = issue; char 9 = check digit. |
| `sedol`       | 7 chars (e.g. `2046251`) | London Stock Exchange  | UK/IE/intl securities    | Listing-level (closer to `quote_perm_id`). |
| `figi`        | 12 chars (e.g. `BBG000B9XRY4`) | OpenFIGI (Bloomberg) | Multi-level (share-class, composite, exchange) | Free + open; we map `composite_figi` to instrument and `figi` to quote. |
| `lei`         | 20 chars (e.g. `HWUPKR0MPOU8FGXBT394`) | GLEIF | Legal-entity level | Joins to `org_perm_id`, not to instruments. |
| `mic`         | 4 chars (e.g. `XNAS`) | ISO 10383 | Trading venue | Joins to `quote_perm_id` via `lseg_ref.exchange_ref`. |
| `ibes_ticker` | up to 8 chars (e.g. `AAPL`) | LSEG I/B/E/S | Per company, per region  | NOT the same as exchange ticker; see §4. |

---

## 3. Cardinality cheat-sheet

| From              | To                | Cardinality            | Note                                                |
| ----------------- | ----------------- | ---------------------- | --------------------------------------------------- |
| `org_perm_id`     | `instrument_perm_id` | 1 : N               | A company has many issued securities.               |
| `instrument_perm_id` | `quote_perm_id` | 1 : N                  | A security trades on many venues.                   |
| `quote_perm_id`   | `ric`             | 1 : 1 (current) / 1 : N (historical) | RIC can change.                       |
| `instrument_perm_id` | `isin`         | 1 : 1 (current) / 1 : N (historical) | ISIN can change.                      |
| `org_perm_id`     | `lei`             | 1 : 1                  | LEI is also legal-entity-level.                     |
| `org_perm_id`     | `ibes_ticker`     | 1 : N (per region)     | A company can have a US `ibes_ticker` and an EMEA one. |

---

## 4. Common pitfalls (the AI assistant must catch these)

1. **Joining fundamentals to pricing on RIC.** Wrong — fundamentals are
   organisation-level. Resolve `ric → quote_perm_id → instrument_perm_id →
   org_perm_id`, then join fundamentals on `org_perm_id`.
2. **Using current RIC for a 5-year backtest.** Vodafone's UK RIC changed
   formatting in 2018. Pull `lseg_ref.ric_history` and join on the
   as-of-date band.
3. **De-duplicating on `isin` to count holdings.** A dual-listed ADR shares an
   ISIN with its ordinary — use `instrument_perm_id` for unique securities.
4. **Filtering `entity_status_code = 'ACTIVE'` on historical analysis.** This
   induces survivorship bias. Use the SCD-2 effective date band.
5. **Joining I/B/E/S to fundamentals on company name.** Always go through
   `ibes_ticker → org_perm_id` (`lseg_ibes.ibes_ticker_xref`), never strings.

---

## 5. Resolution table summary

The "Rosetta Stone" tables that translate between IDs all live in
[`02-reference-data/`](02-reference-data/):

- [`ENTITY_MASTER`](02-reference-data/ENTITY_MASTER.md) — `org_perm_id` ↔ LEI, names, country.
- [`INSTRUMENT_MASTER`](02-reference-data/INSTRUMENT_MASTER.md) — `instrument_perm_id` ↔ ISIN/CUSIP/FIGI, issuer.
- `QUOTE_MASTER` — `quote_perm_id` ↔ RIC, MIC, primary-listing flag (documented within INSTRUMENT_MASTER appendix).
- `RIC_HISTORY` — historical RIC bands per `quote_perm_id`.
- `IBES_TICKER_XREF` — `ibes_ticker` ↔ `org_perm_id` (lives under `06-estimates-ibes/`).
