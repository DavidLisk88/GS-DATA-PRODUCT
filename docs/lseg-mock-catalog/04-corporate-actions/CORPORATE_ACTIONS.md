# `lseg_ref.corporate_actions` (header) and supporting tables

> **Domain:** Corporate Actions
> **Physical location:** `lseg_ref.corporate_actions`, `lseg_ref.corporate_action_terms`, `lseg_ref.corporate_action_elections`
> **Source product:** Refinitiv Corporate Actions feed (DSS `CAs_v4`)
> **Update cadence:** Intraday (every 15 min), with EOD reconciliation 22:00 NYT
> **Volume:** ~1.4M events/year globally across all asset classes
> **Grain (header):** one row per (`ca_event_id`)
> **Grain (terms):** one row per (`ca_event_id`, `term_seq`)

---

## 1. Purpose

Lifecycle of every corporate action (CA) — announcement → ex-date → record
date → payment. Drives adjusted pricing, position adjustment, P&L attribution,
and proxy/voting workflows.

## 2. Data model

Three tables in a header / terms / elections pattern:

```
┌──────────────────────────────────┐
│  corporate_actions (header)      │  1 row per event
│  ca_event_id                     │
└────────────┬─────────────────────┘
             │ 1 : N
┌────────────▼─────────────────────┐
│  corporate_action_terms          │  N rows per event (e.g. multi-stage spin-off)
│  ca_event_id + term_seq          │
└────────────┬─────────────────────┘
             │ 0 : N
┌────────────▼─────────────────────┐
│  corporate_action_elections      │  for voluntary events only (DRIPs, mergers w/ election)
│  ca_event_id + election_seq      │
└──────────────────────────────────┘
```

---

## 3. `lseg_ref.corporate_actions`

### 3.1 Schema

| Column                       | Type           | Null | PK | Description                                                                            |
| ---------------------------- | -------------- | ---- | -- | -------------------------------------------------------------------------------------- |
| `ca_event_id`                | `BIGINT`       | NO   | ✅ | LSEG-assigned unique event identifier.                                                 |
| `instrument_perm_id`         | `BIGINT`       | NO   |    | Affected security. Joins to `instrument_master`.                                       |
| `org_perm_id`                | `BIGINT`       | NO   |    | Issuer. Denormalised for convenience; equals `instrument_master.org_perm_id` PIT.      |
| `ca_type_code`               | `VARCHAR(16)`  | NO   |    | See §4.                                                                                |
| `ca_subtype_code`            | `VARCHAR(32)`  | YES  |    | Vendor-specific finer classification (e.g. `SPECIAL_CASH_DIV`, `RIGHTS_NONTRANSFER`).  |
| `is_mandatory`               | `BOOLEAN`      | NO   |    | TRUE for mandatory; FALSE for voluntary (holder must elect).                           |
| `announce_date`              | `DATE`         | YES  |    | First public announcement.                                                             |
| `ex_date`                    | `DATE`         | YES  |    | Date on which the security trades without the right. The most important date.          |
| `record_date`                | `DATE`         | YES  |    | Holders of record at end-of-day on this date are entitled.                             |
| `payment_date`               | `DATE`         | YES  |    | Cash / new-security distribution date.                                                 |
| `effective_date`             | `DATE`         | YES  |    | For non-distribution events (name changes, redenominations).                           |
| `event_status_code`          | `VARCHAR(16)`  | NO   |    | `ANNOUNCED`, `CONFIRMED`, `PAID`, `WITHDRAWN`, `LAPSED`.                              |
| `narrative`                  | `VARCHAR(2048)`| YES  |    | LSEG editorial description of the event.                                               |
| `vendor_received_ts`         | `TIMESTAMP(6)` | NO   |    | When LSEG first published this event row (any field).                                  |
| `last_updated_ts`            | `TIMESTAMP(6)` | NO   |    | When LSEG last updated any field on this event.                                        |
| `loaded_ts`                  | `TIMESTAMP(6)` | NO   |    |                                                                                        |

### 3.2 Indexes

| Name                                  | Definition                                          |
| ------------------------------------- | --------------------------------------------------- |
| `pk_corporate_actions`                | `(ca_event_id)`                                     |
| `ix_ca_instrument_ex_date`            | `(instrument_perm_id, ex_date)`                     |
| `ix_ca_org_announce`                  | `(org_perm_id, announce_date)`                      |
| `ix_ca_type_ex_date`                  | `(ca_type_code, ex_date)`                           |

## 4. `ca_type_code` enumeration

| Code                  | Description                                                  | Affects pricing adjust? |
| --------------------- | ------------------------------------------------------------ | ----------------------- |
| `CASH_DIV`            | Ordinary cash dividend                                       | Yes                     |
| `SPECIAL_DIV`         | Special / one-off cash dividend                              | Yes                     |
| `STOCK_DIV`           | Stock dividend (N% of held)                                  | Yes                     |
| `STOCK_SPLIT`         | Forward split (N-for-1)                                      | Yes                     |
| `REVERSE_SPLIT`       | Reverse split (1-for-N)                                      | Yes                     |
| `SPINOFF`             | Distribution of shares of a different entity                 | Yes                     |
| `RIGHTS_ISSUE`        | Pre-emptive rights offering                                  | Yes (TERP)              |
| `WARRANT_DIST`        | Warrant distribution                                         | Yes                     |
| `MERGER`              | Merger / acquisition affecting the security                  | Yes (terminal)          |
| `TAKEOVER`            | Successful tender offer                                      | Yes (terminal)          |
| `NAME_CHANGE`         | Issuer or security name change                               | No                      |
| `TICKER_CHANGE`       | RIC / ticker change                                          | No (but updates ref)    |
| `DELISTING`           | Removal from a venue                                         | No (terminal for quote) |
| `BANKRUPTCY`          | Insolvency proceeding affecting equity                       | No (data flag)          |
| `REDEMPTION`          | Fixed-income redemption (maturity / call / put)              | N/A                     |
| `COUPON`              | Fixed-income coupon                                          | N/A (cash flow)         |
| `EXCHANGE_OFFER`      | Exchange of one security for another (often debt for equity) | Yes                     |
| `CAPITAL_REDUCTION`   | Reduction of par value                                       | No                      |

---

## 5. `lseg_ref.corporate_action_terms`

Multi-leg events (e.g. spin-off with cash component) need more than one term.

### 5.1 Schema

| Column                       | Type            | Null | PK | Description                                                              |
| ---------------------------- | --------------- | ---- | -- | ------------------------------------------------------------------------ |
| `ca_event_id`                | `BIGINT`        | NO   | ✅ | FK to `corporate_actions`.                                               |
| `term_seq`                   | `SMALLINT`      | NO   | ✅ | 1, 2, 3, ... for multi-leg.                                              |
| `term_type_code`             | `VARCHAR(16)`   | NO   |    | `CASH`, `NEW_STOCK`, `RIGHT`, `WARRANT`.                                 |
| `from_qty`                   | `DECIMAL(18,6)` | YES  |    | "For every `from_qty` shares held…"                                       |
| `to_qty`                     | `DECIMAL(18,6)` | YES  |    | "…holder receives `to_qty` of the distributed asset."                    |
| `cash_amount`                | `DECIMAL(18,6)` | YES  |    | Per-share cash payment for `CASH` terms.                                 |
| `cash_currency_iso`          | `CHAR(3)`       | YES  |    |                                                                          |
| `new_instrument_perm_id`     | `BIGINT`        | YES  |    | For `NEW_STOCK`, the distributed security.                              |
| `fractional_treatment_code`  | `VARCHAR(16)`   | YES  |    | `ROUND_DOWN`, `ROUND_UP`, `CASH_IN_LIEU`, `BANK`.                        |
| `gross_per_share_amount`     | `DECIMAL(18,6)` | YES  |    | Gross-of-WHT figure for dividends.                                       |
| `withholding_tax_pct`        | `DECIMAL(5,2)`  | YES  |    | Issuer-country statutory withholding rate.                               |

### 5.2 Examples

| Event              | Term 1                                            | Term 2                                              |
| ------------------ | ------------------------------------------------- | --------------------------------------------------- |
| 4-for-1 split      | `STOCK_DIV from_qty=1, to_qty=3`                  | —                                                   |
| $0.50 cash div     | `CASH cash_amount=0.50 cash_currency_iso='USD'`   | —                                                   |
| Spin-off w/ cash   | `NEW_STOCK from_qty=10, to_qty=1, new_instrument_perm_id=...` | `CASH cash_amount=0.25, cash_currency_iso='USD'` |
| Rights 1:5 @ $20   | `RIGHT from_qty=5, to_qty=1, cash_amount=20.00`   | —                                                   |

---

## 6. `lseg_ref.corporate_action_elections` (voluntary only)

| Column                       | Type            | Null | PK | Description                                                              |
| ---------------------------- | --------------- | ---- | -- | ------------------------------------------------------------------------ |
| `ca_event_id`                | `BIGINT`        | NO   | ✅ |                                                                          |
| `election_seq`               | `SMALLINT`      | NO   | ✅ | 1..N possible elections.                                                 |
| `election_code`              | `VARCHAR(16)`   | NO   |    | Free-form-ish: `CASH`, `STOCK`, `CASH_STOCK_MIX`, `DRIP`, `NO_ACTION`.   |
| `election_deadline_ts`       | `TIMESTAMP(6)`  | NO   |    | Voting / election cut-off.                                               |
| `default_election`           | `BOOLEAN`       | NO   |    | TRUE for the option applied if holder fails to elect.                    |
| `proration_factor_pct`       | `DECIMAL(5,2)`  | YES  |    | Post-event proration ratio if oversubscribed.                            |
| `description`                | `VARCHAR(512)`  | YES  |    |                                                                          |

---

## 7. Sample queries

### 7.1 All dividends paid on a security in 2025

```sql
SELECT  ca.ex_date,
        ca.payment_date,
        ca.ca_type_code,
        t.cash_amount,
        t.cash_currency_iso,
        t.gross_per_share_amount,
        t.withholding_tax_pct
FROM    lseg_ref.corporate_actions       ca
JOIN    lseg_ref.corporate_action_terms  t   USING (ca_event_id)
WHERE   ca.instrument_perm_id = 8590932301         -- AAPL common
  AND   ca.ca_type_code IN ('CASH_DIV','SPECIAL_DIV')
  AND   ca.event_status_code = 'PAID'
  AND   ca.ex_date BETWEEN DATE '2025-01-01' AND DATE '2025-12-31'
ORDER BY ca.ex_date;
```

### 7.2 Reconstruct the cumulative adjustment factor

```sql
WITH events AS (
    SELECT  ca.instrument_perm_id,
            ca.ex_date,
            CASE
                WHEN ca.ca_type_code = 'STOCK_SPLIT'   THEN t.to_qty / t.from_qty
                WHEN ca.ca_type_code = 'REVERSE_SPLIT' THEN t.to_qty / t.from_qty
                WHEN ca.ca_type_code = 'CASH_DIV'      THEN
                    1 - (t.cash_amount / pp.close_price)
                ELSE 1.0
            END AS factor
    FROM    lseg_ref.corporate_actions       ca
    JOIN    lseg_ref.corporate_action_terms  t  USING (ca_event_id)
    LEFT JOIN lseg_dss.eod_pricing           pp
      ON    pp.quote_perm_id = (
                SELECT quote_perm_id
                FROM   lseg_ref.quote_master qm
                WHERE  qm.instrument_perm_id = ca.instrument_perm_id
                  AND  qm.is_primary_listing = TRUE
                  AND  ca.ex_date BETWEEN qm.valid_from_ts AND qm.valid_to_ts
                LIMIT 1
            )
      AND   pp.price_date = ca.ex_date - INTERVAL '1 day'
    WHERE   ca.instrument_perm_id = 8590932301
      AND   ca.event_status_code  = 'PAID'
)
SELECT  ex_date,
        factor,
        EXP(SUM(LN(factor)) OVER (ORDER BY ex_date DESC)) AS cumulative_back_adjust
FROM    events
ORDER BY ex_date;
```

## 8. Known quirks

- `withholding_tax_pct` is the **statutory** issuer-country rate. The actual
  rate suffered depends on the holder's tax-treaty status and is computed by
  the firm's tax engine, not by LSEG.
- For US ADRs, the underlying foreign-issuer dividend appears as a single
  `CASH_DIV` against the ADR `instrument_perm_id` and the FX conversion is
  handled by the depositary; you will not see the local-currency leg here.
- `event_status_code = 'WITHDRAWN'` events are kept and **must** be filtered
  out for production pricing-adjust logic.
- Spin-off valuations rely on a "when-issued" market for the spinco; if no
  WI market existed, the `t.cash_amount` field is populated with the
  vendor's modelled value and the row is flagged in
  `ca.narrative`.
