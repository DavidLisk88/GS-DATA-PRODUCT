# `lseg_ref.entity_master`

> **Domain:** Reference Data
> **Physical location:** `lseg_ref.entity_master`
> **Source product:** Refinitiv Reference Data (DSS feed `RefDataPro_Entity_v3`)
> **Update cadence:** Daily delta (06:00 NYT); full snapshot every Saturday 22:00 NYT
> **Row volume (prod):** ~3.1M active rows + ~5.4M historical SCD-2 rows (~8.5M total)
> **Grain:** One row per `org_perm_id` per validity period (SCD Type 2)
> **Primary key:** (`org_perm_id`, `valid_from_ts`)
> **Partitioning:** `partition by entity_country_iso` (cluster by `org_perm_id`)

---

## 1. Purpose

The single source of truth for **legal-entity** reference attributes. Every
fundamentals, ESG, ownership, or I/B/E/S query ultimately joins back here to
get country, name, sector, and active/inactive status as-of a date.

This is a **slowly changing dimension type 2 (SCD-2)** table — when any tracked
attribute changes (e.g. re-incorporation, name change), the prior row is
expired and a new row is inserted.

## 2. Schema

| Column                         | Type           | Null | PK | Description                                                                              |
| ------------------------------ | -------------- | ---- | -- | ---------------------------------------------------------------------------------------- |
| `org_perm_id`                  | `BIGINT`       | NO   | ✅ | LSEG Organisation PermID. Immutable for the life of the legal entity.                    |
| `valid_from_ts`                | `TIMESTAMP(6)` | NO   | ✅ | Inclusive UTC timestamp when this version of the row became effective.                   |
| `valid_to_ts`                  | `TIMESTAMP(6)` | NO   |    | Exclusive UTC timestamp when this version was superseded. `9999-12-31 00:00:00` if current. |
| `is_current`                   | `BOOLEAN`      | NO   |    | Convenience flag = (`valid_to_ts = '9999-12-31'`). Indexed.                              |
| `entity_legal_name`            | `VARCHAR(512)` | NO   |    | Full registered legal name in the entity's home language.                                |
| `entity_common_name`           | `VARCHAR(256)` | NO   |    | Marketing / display name (e.g. "Apple" vs "Apple Inc.").                                 |
| `entity_status_code`           | `VARCHAR(16)`  | NO   |    | One of `ACTIVE`, `INACTIVE`, `MERGED`, `LIQUIDATED`, `DISSOLVED`, `SUSPENDED`. See §3.   |
| `entity_type_code`             | `VARCHAR(16)`  | NO   |    | One of `PUB_CO`, `PRV_CO`, `FUND`, `GOVT`, `MUNI`, `SUPRA`, `SPV`, `TRUST`, `OTHER`.    |
| `entity_country_iso`           | `CHAR(2)`      | NO   |    | ISO 3166-1 alpha-2 of country of incorporation. Joins to `lseg_ref.country_ref`.        |
| `entity_country_iso_hq`        | `CHAR(2)`      | YES  |    | ISO 3166-1 alpha-2 of headquarters country, if different from incorporation.            |
| `entity_state_code`            | `VARCHAR(8)`   | YES  |    | Sub-national code (US states, CA provinces). ISO 3166-2 stripped of country prefix.     |
| `lei`                          | `CHAR(20)`     | YES  |    | Global Legal Entity Identifier (GLEIF). Unique-but-nullable; some private entities lack one. |
| `parent_org_perm_id`           | `BIGINT`       | YES  |    | Immediate parent in the corporate hierarchy. Self-join to `entity_master`.              |
| `ultimate_parent_org_perm_id`  | `BIGINT`       | YES  |    | Top of the corporate tree.                                                              |
| `successor_org_perm_id`        | `BIGINT`       | YES  |    | Populated when `entity_status_code = 'MERGED'`. The surviving entity.                   |
| `predecessor_org_perm_ids`     | `ARRAY<BIGINT>`| YES  |    | Entities that merged into this one. Inverse of `successor_org_perm_id`.                 |
| `incorporation_date`           | `DATE`         | YES  |    | Date the legal entity was created.                                                      |
| `delisting_date`               | `DATE`         | YES  |    | First date the entity was no longer publicly traded (any venue).                        |
| `nace_code`                    | `VARCHAR(8)`   | YES  |    | NACE Rev. 2 industry classification.                                                    |
| `naics_code`                   | `VARCHAR(8)`   | YES  |    | NAICS 2022 industry classification.                                                     |
| `trbc_industry_code`           | `VARCHAR(10)`  | YES  |    | Refinitiv Business Classification (TRBC) leaf industry. Joins to `sector_classification`.|
| `website_url`                  | `VARCHAR(512)` | YES  |    | Primary corporate website. Stripped of scheme; lowercase.                                |
| `source_change_reason_code`    | `VARCHAR(32)`  | NO   |    | Why this SCD-2 row was created. See §4.                                                  |
| `loaded_ts`                    | `TIMESTAMP(6)` | NO   |    | When this row landed in EDL. May differ from `valid_from_ts` (delayed delivery).        |

## 3. `entity_status_code` enumeration

| Code         | Meaning                                                                       |
| ------------ | ----------------------------------------------------------------------------- |
| `ACTIVE`     | Operating, all securities tradeable somewhere.                                |
| `INACTIVE`   | Not currently operating, but still legally existent (e.g. shell after disposal). |
| `MERGED`     | Absorbed into another entity. See `successor_org_perm_id`.                    |
| `LIQUIDATED` | Wound up; assets distributed.                                                 |
| `DISSOLVED`  | Legally struck from companies register.                                       |
| `SUSPENDED`  | Trading suspended on all venues, status under review.                         |

Survivorship-bias guidance: a backtest on the S&P 500 starting in 2010 must
include rows where `entity_status_code IN ('MERGED','LIQUIDATED','DISSOLVED')`
as long as the row was `ACTIVE` at the as-of date. See join cookbook §3.

## 4. `source_change_reason_code` enumeration

| Code                  | Triggers a new SCD-2 row when…                                  |
| --------------------- | --------------------------------------------------------------- |
| `INITIAL_LOAD`        | First time we saw this `org_perm_id`.                           |
| `NAME_CHANGE`         | `entity_legal_name` or `entity_common_name` changed.            |
| `STATUS_CHANGE`       | `entity_status_code` changed.                                   |
| `REINCORPORATION`     | Country of incorporation changed.                               |
| `PARENT_CHANGE`       | `parent_org_perm_id` changed (M&A, restructuring).              |
| `CLASSIFICATION_FIX`  | TRBC / NACE / NAICS reclassification by LSEG.                   |
| `VENDOR_CORRECTION`   | LSEG issued a retroactive correction.                           |

## 5. Indexes

| Name                            | Columns                                    | Purpose                          |
| ------------------------------- | ------------------------------------------ | -------------------------------- |
| `pk_entity_master`              | `(org_perm_id, valid_from_ts)`             | Primary key, unique.             |
| `ix_entity_master_lei`          | `(lei)` WHERE `lei IS NOT NULL`            | Look up by LEI.                  |
| `ix_entity_master_current`      | `(org_perm_id)` WHERE `is_current = TRUE`  | Hot path for "give me the latest". |
| `ix_entity_master_country`      | `(entity_country_iso, is_current)`         | Country-filtered universe scans. |

## 6. Relationships

| Joins to                                                          | On                                                                  | Cardinality |
| ----------------------------------------------------------------- | ------------------------------------------------------------------- | ----------- |
| [`lseg_ref.instrument_master`](INSTRUMENT_MASTER.md)              | `entity_master.org_perm_id = instrument_master.org_perm_id`         | 1 : N       |
| [`lseg_ref.country_ref`](COUNTRY_REF.md)                          | `entity_master.entity_country_iso = country_ref.country_iso`        | N : 1       |
| [`lseg_ref.sector_classification`](SECTOR_CLASSIFICATION.md)      | `entity_master.trbc_industry_code = sector_classification.trbc_industry_code` | N : 1 |
| `lseg_wsf.company_fundamentals`                                   | `entity_master.org_perm_id = company_fundamentals.org_perm_id` (PIT band) | 1 : N |
| `lseg_ibes.ibes_ticker_xref`                                      | `entity_master.org_perm_id = ibes_ticker_xref.org_perm_id`          | 1 : N       |
| `lseg_esg.esg_scores`                                             | `entity_master.org_perm_id = esg_scores.org_perm_id`                | 1 : N       |
| Self-join (parent/child)                                          | `child.parent_org_perm_id = parent.org_perm_id`                     | N : 1       |

## 7. Sample queries

### 7.1 Get current legal name for a list of LEIs

```sql
SELECT  em.lei,
        em.org_perm_id,
        em.entity_legal_name,
        em.entity_country_iso
FROM    lseg_ref.entity_master em
WHERE   em.lei IN ('HWUPKR0MPOU8FGXBT394', '529900T8BM49AURSDO55')
  AND   em.is_current = TRUE;
```

### 7.2 Point-in-time name as of 2018-06-30

```sql
SELECT  em.org_perm_id,
        em.entity_legal_name
FROM    lseg_ref.entity_master em
WHERE   em.org_perm_id = 4295903669       -- Facebook → Meta
  AND   TIMESTAMP '2018-06-30 00:00:00'
        BETWEEN em.valid_from_ts AND em.valid_to_ts;
-- Returns: "Facebook, Inc." (the rename to Meta Platforms happened 2021-10-28)
```

### 7.3 Trace a merger lineage

```sql
WITH RECURSIVE lineage AS (
    SELECT  org_perm_id,
            entity_legal_name,
            successor_org_perm_id,
            0 AS depth
    FROM    lseg_ref.entity_master
    WHERE   org_perm_id = 4295905278    -- starting point
      AND   is_current = TRUE

    UNION ALL

    SELECT  e.org_perm_id,
            e.entity_legal_name,
            e.successor_org_perm_id,
            l.depth + 1
    FROM    lseg_ref.entity_master e
    JOIN    lineage l
      ON    e.org_perm_id = l.successor_org_perm_id
    WHERE   e.is_current = TRUE
      AND   l.depth < 10
)
SELECT * FROM lineage ORDER BY depth;
```

## 8. Known data quirks (read before complaining to vendor)

- `entity_common_name` can lag `entity_legal_name` by 1–3 business days after
  a rename; the legal name is updated first from filings, the common name from
  the editorial desk.
- For Chinese A-share issuers, `entity_legal_name` is in pinyin; the Hanzi
  form is in `lseg_ref.entity_master_i18n` (not documented here).
- `lei` will be `NULL` for some pre-2014 historical rows even on entities that
  later obtained one — LEIs are not backfilled by GLEIF.
- TRBC reclassifications happen ~quarterly and trigger an SCD-2 row even
  though nothing about the company "changed" — be ready for spurious
  `valid_from_ts` boundaries in analytics.
