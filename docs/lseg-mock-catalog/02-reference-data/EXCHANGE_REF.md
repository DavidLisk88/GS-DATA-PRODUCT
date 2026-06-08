# `lseg_ref.exchange_ref`

> **Domain:** Reference Data
> **Physical location:** `lseg_ref.exchange_ref`
> **Source product:** LSEG Reference Data — Exchange Master
> **Update cadence:** Weekly delta (Sunday 04:00 NYT)
> **Row volume (prod):** ~2,400 active venues, ~3,700 historical
> **Grain:** one row per `mic` per validity period (SCD-2)
> **Primary key:** (`mic`, `valid_from_ts`)

## 1. Purpose

Lookup for ISO 10383 Market Identifier Codes (MICs). Joined from
`lseg_ref.quote_master` to give human-readable exchange info, time zones, and
session calendars.

## 2. Schema

| Column                    | Type           | Null | PK | Description                                                              |
| ------------------------- | -------------- | ---- | -- | ------------------------------------------------------------------------ |
| `mic`                     | `CHAR(4)`      | NO   | ✅ | ISO 10383 Market Identifier Code.                                        |
| `valid_from_ts`           | `TIMESTAMP(6)` | NO   | ✅ | SCD-2 effective.                                                         |
| `valid_to_ts`             | `TIMESTAMP(6)` | NO   |    | SCD-2 superseded.                                                        |
| `is_current`              | `BOOLEAN`      | NO   |    |                                                                          |
| `operating_mic`           | `CHAR(4)`      | NO   |    | Parent MIC for venues that are segments. Self-join (`XNAS` → `XNAS`).    |
| `exchange_name`           | `VARCHAR(128)` | NO   |    | "NASDAQ Stock Market", "London Stock Exchange", etc.                     |
| `acronym`                 | `VARCHAR(16)`  | YES  |    | "NASDAQ", "LSE", "TSE".                                                  |
| `country_iso`             | `CHAR(2)`      | NO   |    | ISO 3166-1 alpha-2.                                                      |
| `city`                    | `VARCHAR(64)`  | NO   |    |                                                                          |
| `timezone_iana`           | `VARCHAR(64)`  | NO   |    | IANA tz database name, e.g. `America/New_York`.                          |
| `regular_session_open_local`  | `TIME`     | YES  |    | Local-time open of regular session.                                      |
| `regular_session_close_local` | `TIME`     | YES  |    | Local-time close of regular session.                                     |
| `mic_status_code`         | `VARCHAR(16)`  | NO   |    | `ACTIVE`, `EXPIRED`, `MODIFIED`.                                         |
| `mic_type_code`           | `VARCHAR(16)`  | NO   |    | `EXCH` (exchange), `MTF`, `OTF`, `SI`, `OTH`.                            |
| `website_url`             | `VARCHAR(256)` | YES  |    |                                                                          |
| `holiday_calendar_code`   | `VARCHAR(16)`  | YES  |    | Joins to `lseg_ref.holiday_calendar` (not documented in this mock).      |
| `loaded_ts`               | `TIMESTAMP(6)` | NO   |    |                                                                          |

## 3. Indexes

| Name                       | Columns                                        |
| -------------------------- | ---------------------------------------------- |
| `pk_exchange_ref`          | `(mic, valid_from_ts)`                         |
| `ix_exchange_ref_country`  | `(country_iso, is_current)`                    |
| `ix_exchange_ref_op_mic`   | `(operating_mic, is_current)`                  |

## 4. Sample queries

### 4.1 All MTFs in the EU

```sql
SELECT mic, exchange_name, country_iso
FROM   lseg_ref.exchange_ref
WHERE  mic_type_code = 'MTF'
  AND  country_iso IN ('DE','FR','NL','IE','ES','IT','BE','LU')
  AND  is_current = TRUE
ORDER BY country_iso, exchange_name;
```

### 4.2 All segment MICs under NASDAQ

```sql
SELECT mic, exchange_name
FROM   lseg_ref.exchange_ref
WHERE  operating_mic = 'XNAS'
  AND  is_current = TRUE;
-- Returns XNAS, XNCM, XNGS, XNMS, etc.
```

## 5. Known quirks

- Some primary listings (notably ADRs traded "off-exchange") carry the MIC
  `OOTC` or `XOFF`. These are not venues in the conventional sense.
- The `operating_mic` self-reference can occasionally lag by one weekly cycle
  after ISO publishes a new segment MIC.
