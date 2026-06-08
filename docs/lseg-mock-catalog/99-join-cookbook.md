# LSEG Catalog — Join Cookbook

> This is the highest-value page for anyone querying multiple LSEG domains.
> Bookmark it.

The patterns below recur in ~80% of real-world queries. Memorise them and your
joins will be correct on the first try.

---

## 1. Identifier resolution (the "Rosetta path")

Always resolve the user's input identifier to a stable PermID at the right
level before joining anything else.

### 1.1 RIC → everything

```sql
WITH resolved AS (
    SELECT qm.quote_perm_id,
           qm.instrument_perm_id,
           im.org_perm_id,
           qm.is_primary_listing
    FROM   lseg_ref.quote_master      qm
    JOIN   lseg_ref.instrument_master im
      ON   im.instrument_perm_id = qm.instrument_perm_id
      AND  im.is_current = TRUE
    WHERE  qm.ric = :input_ric
      AND  qm.is_current = TRUE
)
SELECT * FROM resolved;
```

### 1.2 Historical RIC (string) → today's PermIDs

```sql
WITH resolved AS (
    SELECT  qm.quote_perm_id,
            qm.instrument_perm_id,
            im.org_perm_id
    FROM    lseg_ref.ric_history       rh
    JOIN    lseg_ref.quote_master      qm
      ON    qm.quote_perm_id = rh.quote_perm_id
    JOIN    lseg_ref.instrument_master im
      ON    im.instrument_perm_id = qm.instrument_perm_id
    WHERE   rh.ric                = :legacy_ric
      AND   :as_of_date BETWEEN rh.effective_from_date AND rh.effective_to_date
      AND   qm.is_current = TRUE
      AND   im.is_current = TRUE
)
SELECT * FROM resolved;
```

### 1.3 ISIN → company

```sql
SELECT  im.org_perm_id
FROM    lseg_ref.instrument_master im
WHERE   im.isin = :isin
  AND   im.is_current = TRUE;
```

### 1.4 LEI → company

```sql
SELECT  em.org_perm_id
FROM    lseg_ref.entity_master em
WHERE   em.lei = :lei
  AND   em.is_current = TRUE;
```

---

## 2. Pricing × Reference patterns

### 2.1 Get the primary-listing closing price per company

```sql
SELECT  em.org_perm_id,
        em.entity_common_name,
        p.price_date,
        p.close_price,
        p.trading_currency_iso
FROM    lseg_ref.entity_master       em
JOIN    lseg_ref.instrument_master   im
  ON    im.org_perm_id           = em.org_perm_id
  AND   im.is_current            = TRUE
  AND   im.is_primary_security   = TRUE
JOIN    lseg_ref.quote_master        qm
  ON    qm.instrument_perm_id    = im.instrument_perm_id
  AND   qm.is_current            = TRUE
  AND   qm.is_primary_listing    = TRUE
JOIN    lseg_dss.eod_pricing         p
  ON    p.quote_perm_id          = qm.quote_perm_id
WHERE   em.is_current = TRUE
  AND   em.org_perm_id IN (:org_ids)
  AND   p.price_date = :as_of_date;
```

### 2.2 Convert any close price to USD

```sql
SELECT  p.quote_perm_id,
        p.price_date,
        p.close_price,
        p.trading_currency_iso,
        p.close_price / fx.mid_rate AS close_price_usd
FROM    lseg_dss.eod_pricing  p
JOIN    lseg_fx.fx_rates_eod  fx
  ON    fx.base_ccy  = 'USD'
  AND   fx.quote_ccy = p.trading_currency_iso
  AND   fx.fix_date  = p.price_date
  AND   fx.fix_code  = 'WMR_LON_4PM'
WHERE   p.quote_perm_id = :quote_perm_id
  AND   p.price_date BETWEEN :start_date AND :end_date;
```

---

## 3. Point-in-time correctness

The cardinal rule: **never join an SCD-2 dimension on `is_current = TRUE` for
historical analysis**. Use the validity band.

### 3.1 Get the sector classification of a company as of a date

```sql
SELECT  em.org_perm_id,
        sc.trbc_econ_sector_name,
        sc.trbc_industry_name
FROM    lseg_ref.entity_master         em
JOIN    lseg_ref.sector_classification sc
  ON    sc.trbc_industry_code = em.trbc_industry_code
  AND   :as_of_ts BETWEEN sc.valid_from_ts AND sc.valid_to_ts
WHERE   em.org_perm_id = :org_perm_id
  AND   :as_of_ts BETWEEN em.valid_from_ts AND em.valid_to_ts;
```

### 3.2 What did we know about fundamentals on a specific date?

```sql
SELECT  cf.*
FROM    lseg_wsf.company_fundamentals cf
WHERE   cf.org_perm_id            = :org_perm_id
  AND   cf.period_end_date       <= :as_of_date
  AND   :as_of_ts BETWEEN cf.valid_from_ts AND cf.valid_to_ts
ORDER BY cf.period_end_date DESC
LIMIT 1;
```

### 3.3 Survivorship-bias-free universe construction

```sql
-- All companies that were ACTIVE on 2015-01-01 in the Tech sector
SELECT  em.org_perm_id
FROM    lseg_ref.entity_master         em
JOIN    lseg_ref.sector_classification sc
  ON    sc.trbc_industry_code = em.trbc_industry_code
  AND   TIMESTAMP '2015-01-01 00:00:00' BETWEEN sc.valid_from_ts AND sc.valid_to_ts
WHERE   TIMESTAMP '2015-01-01 00:00:00' BETWEEN em.valid_from_ts AND em.valid_to_ts
  AND   em.entity_status_code          = 'ACTIVE'
  AND   sc.trbc_econ_sector_code       = '50';
-- DO NOT add: AND em.is_current = TRUE  ← that would exclude later-merged firms.
```

---

## 4. Corporate-actions adjustment patterns

### 4.1 Adjusted return between two dates (already provided by `close_adj_price`)

```sql
SELECT  (later.close_adj_price / earlier.close_adj_price) - 1 AS total_return
FROM    lseg_dss.eod_pricing later
JOIN    lseg_dss.eod_pricing earlier USING (quote_perm_id)
WHERE   later.quote_perm_id   = :quote_perm_id
  AND   later.price_date      = :end_date
  AND   earlier.price_date    = :start_date;
```

### 4.2 Build a position-adjustment ledger for a specific holding

```sql
SELECT  ca.ex_date,
        ca.ca_type_code,
        t.from_qty, t.to_qty,
        t.cash_amount, t.cash_currency_iso,
        t.new_instrument_perm_id
FROM    lseg_ref.corporate_actions       ca
JOIN    lseg_ref.corporate_action_terms  t USING (ca_event_id)
WHERE   ca.instrument_perm_id = :instrument_perm_id
  AND   ca.event_status_code  = 'PAID'
  AND   ca.ex_date BETWEEN :acquisition_date AND :as_of_date
ORDER BY ca.ex_date, t.term_seq;
```

---

## 5. Fundamentals × pricing — valuation multiples

### 5.1 Trailing P/E ratio

```sql
WITH last_fy AS (
    SELECT cf.org_perm_id,
           cf.eps_diluted,
           cf.report_currency_iso
    FROM   lseg_wsf.company_fundamentals cf
    WHERE  cf.org_perm_id = :org_perm_id
      AND  cf.fiscal_period_type_code = 'FY'
      AND  cf.is_current_version      = TRUE
    QUALIFY ROW_NUMBER() OVER (ORDER BY cf.period_end_date DESC) = 1
),
primary_price AS (
    SELECT p.close_price, p.trading_currency_iso
    FROM   lseg_dss.eod_pricing p
    JOIN   lseg_ref.quote_master qm USING (quote_perm_id)
    JOIN   lseg_ref.instrument_master im
      ON   im.instrument_perm_id = qm.instrument_perm_id
      AND  im.org_perm_id = :org_perm_id
      AND  im.is_primary_security = TRUE
      AND  im.is_current = TRUE
    WHERE  qm.is_primary_listing = TRUE AND qm.is_current = TRUE
      AND  p.price_date = :as_of_date
)
SELECT  pp.close_price / lf.eps_diluted AS trailing_pe
FROM    primary_price pp CROSS JOIN last_fy lf
WHERE   lf.report_currency_iso = pp.trading_currency_iso;     -- ensure same ccy
```

---

## 6. Estimates × actuals — earnings surprises

See [IBES_CONSENSUS §E.2](06-estimates-ibes/IBES_CONSENSUS.md#e-sample-queries).

---

## 7. ESG × sector — peer-relative scoring

```sql
WITH peer_set AS (
    SELECT em.org_perm_id, em.trbc_industry_code
    FROM   lseg_ref.entity_master em
    WHERE  em.trbc_industry_code = (
                SELECT trbc_industry_code FROM lseg_ref.entity_master
                WHERE  org_perm_id = :org_perm_id AND is_current = TRUE)
      AND  em.is_current = TRUE
      AND  em.entity_status_code = 'ACTIVE'
)
SELECT  em.entity_common_name,
        es.esg_score,
        PERCENT_RANK() OVER (ORDER BY es.esg_score) AS peer_percentile
FROM    peer_set                       p
JOIN    lseg_ref.entity_master         em ON em.org_perm_id = p.org_perm_id AND em.is_current = TRUE
JOIN    lseg_esg.esg_scores            es
  ON    es.org_perm_id = p.org_perm_id
  AND   es.is_current_version = TRUE
  AND   es.score_period_end_date = (
            SELECT MAX(score_period_end_date) FROM lseg_esg.esg_scores
            WHERE org_perm_id = p.org_perm_id AND is_current_version = TRUE);
```

---

## 8. Anti-patterns the AI assistant must flag

| Anti-pattern                                                       | Why it fails                                                |
| ------------------------------------------------------------------ | ----------------------------------------------------------- |
| `JOIN ... ON ric = ric`                                            | RICs change; use `quote_perm_id`.                           |
| `JOIN entity_master ... WHERE is_current = TRUE` in a historical Q | Survivorship + restated-attribute bias.                     |
| `WHERE isin = X` to count holdings                                 | ADR + ordinary share the same ISIN; use `instrument_perm_id`. |
| Computing P/E across currencies                                    | EPS in JPY ÷ price in USD = nonsense.                       |
| Filtering out `audit_status_code = 'QUALIFIED'`                    | Removes legitimate (and important) data.                    |
| Filtering out `entity_status_code IN ('MERGED','LIQUIDATED')`      | Survivorship bias.                                          |
| Joining I/B/E/S to fundamentals on `ibes_ticker = exchange_ticker` | They are different namespaces — go through `ibes_ticker_xref`. |
| Reading `lseg_tick.*` without `event_date` predicate               | Query governance will kill the job.                         |
| Using `close_adj_price` without re-loading on the day of a new CA  | Adjusted prices are continuously back-adjusted.             |
