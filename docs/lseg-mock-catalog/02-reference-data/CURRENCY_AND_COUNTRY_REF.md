# `lseg_ref.currency_ref` and `lseg_ref.country_ref`

> **Domain:** Reference Data
> **Source product:** LSEG Reference Data — Static Lookups
> **Update cadence:** Monthly (1st business day, 04:00 NYT)
> **Volume:** `currency_ref` ~280 rows; `country_ref` ~250 rows
> **Grain:** one row per ISO code per validity period (SCD-2)

These are small, slow-moving lookups. SCD-2 is retained because currencies and
country codes do occasionally change (e.g. South Sudan 2011, redenominations,
Eurozone joins, Crimea reclassifications), and historical analytics must
respect the codes as of the as-of date.

---

## A) `lseg_ref.currency_ref`

### A.1 Schema

| Column                | Type           | Null | PK | Description                                                              |
| --------------------- | -------------- | ---- | -- | ------------------------------------------------------------------------ |
| `currency_iso`        | `CHAR(3)`      | NO   | ✅ | ISO 4217 alphabetic code, e.g. `USD`, `EUR`, `JPY`.                      |
| `valid_from_ts`       | `TIMESTAMP(6)` | NO   | ✅ |                                                                          |
| `valid_to_ts`         | `TIMESTAMP(6)` | NO   |    |                                                                          |
| `is_current`          | `BOOLEAN`      | NO   |    |                                                                          |
| `currency_iso_num`    | `CHAR(3)`      | NO   |    | ISO 4217 numeric code, e.g. `840`.                                       |
| `currency_name`       | `VARCHAR(64)`  | NO   |    | "United States Dollar".                                                  |
| `minor_unit_digits`   | `INTEGER`      | NO   |    | Number of decimal places (USD=2, JPY=0, BHD=3).                          |
| `is_active`           | `BOOLEAN`      | NO   |    | FALSE for retired currencies (DEM, FRF, etc.).                           |
| `country_iso_primary` | `CHAR(2)`      | YES  |    | Primary issuing country, where unambiguous (USD → US).                   |
| `replacement_currency_iso` | `CHAR(3)` | YES  |    | For redenominations (e.g. VEF → VES, ZMK → ZMW).                         |
| `loaded_ts`           | `TIMESTAMP(6)` | NO   |    |                                                                          |

### A.2 Sample queries

```sql
-- All deprecated currencies replaced by the euro
SELECT currency_iso, currency_name, valid_to_ts
FROM   lseg_ref.currency_ref
WHERE  replacement_currency_iso = 'EUR'
  AND  is_active = FALSE;
```

---

## B) `lseg_ref.country_ref`

### B.1 Schema

| Column                 | Type           | Null | PK | Description                                                              |
| ---------------------- | -------------- | ---- | -- | ------------------------------------------------------------------------ |
| `country_iso`          | `CHAR(2)`      | NO   | ✅ | ISO 3166-1 alpha-2.                                                      |
| `valid_from_ts`        | `TIMESTAMP(6)` | NO   | ✅ |                                                                          |
| `valid_to_ts`          | `TIMESTAMP(6)` | NO   |    |                                                                          |
| `is_current`           | `BOOLEAN`      | NO   |    |                                                                          |
| `country_iso_3`        | `CHAR(3)`      | NO   |    | ISO 3166-1 alpha-3, e.g. `USA`.                                          |
| `country_iso_num`      | `CHAR(3)`      | NO   |    | ISO 3166-1 numeric, e.g. `840`.                                          |
| `country_name`         | `VARCHAR(96)`  | NO   |    | Short name.                                                              |
| `country_name_official`| `VARCHAR(192)` | NO   |    | Official long form.                                                      |
| `region_code`          | `VARCHAR(16)`  | NO   |    | LSEG region: `NAMR`, `LATM`, `EMEA`, `APAC`, `JPN`.                      |
| `sub_region_code`      | `VARCHAR(16)`  | NO   |    | LSEG sub-region, e.g. `EUR_WST`, `EUR_NDC`, `ASIA_SE`.                   |
| `currency_iso_primary` | `CHAR(3)`      | YES  |    |                                                                          |
| `is_developed_market`  | `BOOLEAN`      | NO   |    | LSEG/FTSE Russell developed-market classification flag (snapshot).       |
| `is_emerging_market`   | `BOOLEAN`      | NO   |    |                                                                          |
| `is_frontier_market`   | `BOOLEAN`      | NO   |    |                                                                          |
| `is_eu_member`         | `BOOLEAN`      | NO   |    |                                                                          |
| `is_oecd_member`       | `BOOLEAN`      | NO   |    |                                                                          |
| `loaded_ts`            | `TIMESTAMP(6)` | NO   |    |                                                                          |

### B.2 Sample queries

```sql
-- DM countries in EMEA as of 2015
SELECT country_iso, country_name
FROM   lseg_ref.country_ref
WHERE  region_code = 'EMEA'
  AND  is_developed_market = TRUE
  AND  TIMESTAMP '2015-12-31 00:00:00' BETWEEN valid_from_ts AND valid_to_ts;
```

## C) Known quirks

- The DM/EM/FM flags are derived from FTSE Russell's annual country
  classification review (September). They will lag the announcement
  by ~3 business days.
- `country_iso = 'GB'` is the UK; `country_iso = 'UK'` does NOT exist in
  ISO 3166-1 and will never appear here (frequent newbie mistake).
- For securities issued in jurisdictions that no longer exist (e.g. Yugoslav
  domestic bonds), historical rows with retired `country_iso` codes are
  retained — do not filter on `is_current = TRUE` for historical PIT queries.
