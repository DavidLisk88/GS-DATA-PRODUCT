# `lseg_ref.sector_classification`

> **Domain:** Reference Data
> **Physical location:** `lseg_ref.sector_classification`
> **Source product:** The Refinitiv Business Classification (TRBC)
> **Update cadence:** Quarterly (Mar/Jun/Sep/Dec — 15th of month)
> **Volume:** ~150 economic sectors / business sectors / industry groups / industries / activities (5-level hierarchy)
> **Grain:** one row per TRBC code per validity period (SCD-2)
> **Primary key:** (`trbc_industry_code`, `valid_from_ts`)

## 1. Purpose

The TRBC hierarchy used by LSEG to classify every issuer. Joined from
`entity_master.trbc_industry_code` to obtain sector / industry-group rollups.

## 2. The TRBC hierarchy

```
Economic Sector       (10 sectors)         e.g. 50 - Technology
└── Business Sector   (28)                 e.g. 5710 - Technology Equipment
    └── Industry Group(54)                 e.g. 571020 - Computers, Phones & Household Electronics
        └── Industry  (136)                e.g. 57102010 - Computer Hardware
            └── Activity (898)             e.g. 5710201010 - Personal Computers
```

All five levels are stored as separate columns; the leaf is the join key.

## 3. Schema

| Column                       | Type           | Null | PK | Description                                                              |
| ---------------------------- | -------------- | ---- | -- | ------------------------------------------------------------------------ |
| `trbc_industry_code`         | `VARCHAR(10)`  | NO   | ✅ | Leaf-level TRBC code (Activity, 10 digits).                              |
| `valid_from_ts`              | `TIMESTAMP(6)` | NO   | ✅ |                                                                          |
| `valid_to_ts`                | `TIMESTAMP(6)` | NO   |    |                                                                          |
| `is_current`                 | `BOOLEAN`      | NO   |    |                                                                          |
| `trbc_industry_name`         | `VARCHAR(128)` | NO   |    | Human-readable leaf name.                                                |
| `trbc_industry_parent_code`  | `VARCHAR(8)`   | NO   |    | Industry code (one level up).                                            |
| `trbc_industry_parent_name`  | `VARCHAR(128)` | NO   |    |                                                                          |
| `trbc_group_code`            | `VARCHAR(6)`   | NO   |    | Industry Group code.                                                     |
| `trbc_group_name`            | `VARCHAR(128)` | NO   |    |                                                                          |
| `trbc_bus_sector_code`       | `VARCHAR(4)`   | NO   |    | Business Sector code.                                                    |
| `trbc_bus_sector_name`       | `VARCHAR(128)` | NO   |    |                                                                          |
| `trbc_econ_sector_code`      | `VARCHAR(2)`   | NO   |    | Economic Sector code.                                                    |
| `trbc_econ_sector_name`      | `VARCHAR(128)` | NO   |    |                                                                          |
| `gics_sector_code_xref`      | `VARCHAR(8)`   | YES  |    | Best-effort GICS cross-reference (sector level only).                    |
| `nace_code_xref`             | `VARCHAR(8)`   | YES  |    |                                                                          |
| `loaded_ts`                  | `TIMESTAMP(6)` | NO   |    |                                                                          |

## 4. Indexes

| Name                                   | Columns                                          |
| -------------------------------------- | ------------------------------------------------ |
| `pk_sector_classification`             | `(trbc_industry_code, valid_from_ts)`            |
| `ix_sector_econ_sector`                | `(trbc_econ_sector_code, is_current)`            |
| `ix_sector_bus_sector`                 | `(trbc_bus_sector_code, is_current)`             |

## 5. Sample queries

### 5.1 All "Renewable Energy" issuers (Industry Group level)

```sql
SELECT em.org_perm_id,
       em.entity_common_name,
       sc.trbc_industry_name
FROM   lseg_ref.entity_master         em
JOIN   lseg_ref.sector_classification sc
  ON   sc.trbc_industry_code = em.trbc_industry_code
WHERE  em.is_current = TRUE
  AND  sc.is_current = TRUE
  AND  sc.trbc_group_code = '501020';   -- Renewable Energy industry group
```

### 5.2 Sector rollup of revenue

```sql
SELECT sc.trbc_econ_sector_name,
       SUM(cf.revenue_usd) / 1e9 AS revenue_bn_usd
FROM   lseg_wsf.company_fundamentals  cf
JOIN   lseg_ref.entity_master         em
  ON   em.org_perm_id = cf.org_perm_id
  AND  cf.period_end_date BETWEEN em.valid_from_ts AND em.valid_to_ts
JOIN   lseg_ref.sector_classification sc
  ON   sc.trbc_industry_code = em.trbc_industry_code
  AND  cf.period_end_date BETWEEN sc.valid_from_ts AND sc.valid_to_ts
WHERE  cf.period_end_date = DATE '2025-12-31'
  AND  cf.fiscal_period_type_code = 'FY'
GROUP BY sc.trbc_econ_sector_name
ORDER BY revenue_bn_usd DESC;
```

## 6. Known quirks

- TRBC quarterly reclassifications can move an issuer between leaves without
  any real business change; track via `entity_master.source_change_reason_code = 'CLASSIFICATION_FIX'`.
- The GICS cross-reference is **sector-level only** and is provided "as a courtesy" by LSEG;
  do not use it for index-replication work where GICS is contractually required.
