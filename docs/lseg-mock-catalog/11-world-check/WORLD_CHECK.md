# World-Check (KYC / AML / Sanctions)

> **Domain:** Risk & Compliance — World-Check
> **Physical location:** `lseg_wc.*`
> **Source product:** Refinitiv World-Check Risk Intelligence
> **Update cadence:** Streaming (sub-second push for sanctions); EOD reconciliation 23:00 UTC
> **Volume:** ~6.1M individuals, ~2.7M organisations, ~5,200 sanctions lists tracked, ~1.4M PEPs
> **Entitlement:** **ALL columns are [RESTRICTED]**. Requires IAM role `LSEG_WC_VIEWER` (read), `LSEG_WC_INVESTIGATOR` (full PII).

> **⚠ Compliance notice.** This is the most sensitive domain in the catalog.
> Even the mock data here is synthetic. Real World-Check data is subject to
> the firm's Information Barrier policy; the assistant must enforce
> entitlement checks before returning any row.

---

## 1. Tables

| Table                          | Grain                                                              | Purpose                              |
| ------------------------------ | ------------------------------------------------------------------ | ------------------------------------ |
| `lseg_wc.wc_individuals`       | one row per (`wc_subject_id`, `valid_from_ts`) SCD-2               | Master record per natural person     |
| `lseg_wc.wc_organisations`     | one row per (`wc_subject_id`, `valid_from_ts`) SCD-2               | Master record per legal entity       |
| `lseg_wc.wc_aliases`           | one row per (`wc_subject_id`, `alias_seq`)                         | All known name variants              |
| `lseg_wc.wc_sanctions_listings`| one row per (`wc_subject_id`, `sanctions_list_code`, `valid_from_ts`) | Membership on each sanctions list |
| `lseg_wc.wc_pep_listings`      | one row per (`wc_subject_id`, `pep_role_seq`, `valid_from_ts`)     | Politically-exposed-person roles     |
| `lseg_wc.wc_adverse_media`     | one row per (`wc_subject_id`, `article_id`)                        | Adverse-media tagging                |
| `lseg_wc.wc_screening_events`  | one row per (`screening_event_id`)                                 | Audit log of every screen the firm has done |

---

## 2. `lseg_wc.wc_individuals` (key columns)

| Column                       | Type             | Null | PK | Description                                                                              |
| ---------------------------- | ---------------- | ---- | -- | ---------------------------------------------------------------------------------------- |
| `wc_subject_id`              | `BIGINT`         | NO   | ✅ | LSEG World-Check internal ID.                                                            |
| `valid_from_ts`              | `TIMESTAMP(6)`   | NO   | ✅ |                                                                                          |
| `valid_to_ts`                | `TIMESTAMP(6)`   | NO   |    |                                                                                          |
| `is_current`                 | `BOOLEAN`        | NO   |    |                                                                                          |
| `subject_status_code`        | `VARCHAR(16)`    | NO   |    | `ACTIVE`, `DECEASED`, `DELISTED` (removed from any list & no media).                     |
| `risk_category_code`         | `VARCHAR(16)`    | NO   |    | `SANCTIONS`, `PEP`, `LAW_ENF`, `REG_ENF`, `ADVERSE_MEDIA`, `OTHER`, `NONE_FLAGGED`.      |
| `risk_subcategory_codes`     | `ARRAY<VARCHAR(16)>` | YES |    | Finer classification (e.g. `TERR_FIN`, `NARC_TRAF`, `FRAUD`, `CORRUPTION`, `WMD`).       |
| `full_name`                  | `VARCHAR(256)`   | NO   |    | Primary romanised name. **[RESTRICTED]**                                                 |
| `original_script_name`       | `VARCHAR(256)`   | YES  |    | E.g. Cyrillic, Arabic. **[RESTRICTED]**                                                  |
| `date_of_birth`              | `DATE`           | YES  |    | **[RESTRICTED]**                                                                          |
| `date_of_birth_estimated`    | `BOOLEAN`        | YES  |    | TRUE when DOB is approximate (common for sanctions subjects).                            |
| `gender_code`                | `CHAR(1)`        | YES  |    | `M`, `F`, `U`.                                                                            |
| `nationality_iso_codes`      | `ARRAY<CHAR(2)>` | YES  |    | Possibly multiple. **[RESTRICTED]**                                                       |
| `country_of_residence_iso`   | `CHAR(2)`        | YES  |    | **[RESTRICTED]**                                                                          |
| `passport_numbers`           | `ARRAY<VARCHAR(32)>` | YES |    | **[RESTRICTED — INVESTIGATOR]** Only investigators see actual numbers.                   |
| `national_ids`               | `ARRAY<VARCHAR(64)>` | YES |    | **[RESTRICTED — INVESTIGATOR]**                                                          |
| `key_titles`                 | `VARCHAR(512)`   | YES  |    | E.g. "Former Deputy Finance Minister, …".                                                |
| `associated_org_perm_ids`    | `ARRAY<BIGINT>`  | YES  |    | Cross-ref to `entity_master`.                                                            |
| `first_added_date`           | `DATE`           | NO   |    | First date World-Check ever flagged this subject.                                        |
| `last_reviewed_date`         | `DATE`           | NO   |    |                                                                                          |
| `notes`                      | `VARCHAR(2048)`  | YES  |    | Curator notes. **[RESTRICTED]**                                                          |
| `loaded_ts`                  | `TIMESTAMP(6)`   | NO   |    |                                                                                          |

`lseg_wc.wc_organisations` has analogous columns plus `lei`, `registered_address`,
and `parent_wc_subject_id` for corporate hierarchies.

---

## 3. `lseg_wc.wc_sanctions_listings`

| Column                        | Type             | Null | PK | Description                                                              |
| ----------------------------- | ---------------- | ---- | -- | ------------------------------------------------------------------------ |
| `wc_subject_id`               | `BIGINT`         | NO   | ✅ |                                                                          |
| `sanctions_list_code`         | `VARCHAR(32)`    | NO   | ✅ | E.g. `OFAC_SDN`, `OFAC_SSI`, `UN_CONS`, `EU_FSF`, `UK_HMT`, `SWISS_SECO`, `CAN_OSFI`, `AU_DFAT`. |
| `valid_from_ts`               | `TIMESTAMP(6)`   | NO   | ✅ | Date of listing.                                                         |
| `valid_to_ts`                 | `TIMESTAMP(6)`   | NO   |    | Date of de-listing (sentinel if still listed).                           |
| `is_current_listing`          | `BOOLEAN`        | NO   |    |                                                                          |
| `listing_program_code`        | `VARCHAR(64)`    | NO   |    | OFAC program code (`UKRAINE-EO13662`), or equivalent.                    |
| `listing_reference`           | `VARCHAR(64)`    | YES  |    | Official reference number on the source list.                            |
| `listing_basis`               | `VARCHAR(512)`   | YES  |    | Short justification from the sanctioning authority. **[RESTRICTED]**     |
| `regulatory_action_url`       | `VARCHAR(512)`   | YES  |    | URL to the official action.                                              |
| `loaded_ts`                   | `TIMESTAMP(6)`   | NO   |    |                                                                          |

## 4. `lseg_wc.wc_pep_listings`

| Column                       | Type             | Null | PK | Description                                                              |
| ---------------------------- | ---------------- | ---- | -- | ------------------------------------------------------------------------ |
| `wc_subject_id`              | `BIGINT`         | NO   | ✅ |                                                                          |
| `pep_role_seq`               | `INTEGER`        | NO   | ✅ |                                                                          |
| `valid_from_ts`              | `TIMESTAMP(6)`   | NO   | ✅ | Role start.                                                              |
| `valid_to_ts`                | `TIMESTAMP(6)`   | NO   |    | Role end (sentinel if still active).                                     |
| `pep_class_code`             | `VARCHAR(8)`     | NO   |    | `PEP1` (head of state / cabinet), `PEP2` (senior official), `PEP3` (other public official), `RCA` (relative / close associate), `LOCAL_PEP`. |
| `role_title`                 | `VARCHAR(256)`   | NO   |    |                                                                          |
| `role_org_perm_id`           | `BIGINT`         | YES  |    | The government/SOE/intl org cross-referenced.                            |
| `role_country_iso`           | `CHAR(2)`        | NO   |    |                                                                          |
| `is_active_role`             | `BOOLEAN`        | NO   |    |                                                                          |
| `loaded_ts`                  | `TIMESTAMP(6)`   | NO   |    |                                                                          |

## 5. Sample queries

> All queries assume `LSEG_WC_VIEWER` entitlement. The assistant's executor
> will silently rewrite `SELECT *` to omit `[RESTRICTED — INVESTIGATOR]`
> columns if the user lacks that elevated role.

### 5.1 Is this LEI / org_perm_id currently sanctioned?

```sql
SELECT  em.entity_legal_name,
        wo.wc_subject_id,
        sl.sanctions_list_code,
        sl.listing_program_code,
        sl.valid_from_ts AS listed_on_ts
FROM    lseg_ref.entity_master         em
JOIN    lseg_wc.wc_organisations       wo
  ON    wo.lei = em.lei
  AND   wo.is_current = TRUE
JOIN    lseg_wc.wc_sanctions_listings  sl
  ON    sl.wc_subject_id = wo.wc_subject_id
  AND   sl.is_current_listing = TRUE
WHERE   em.lei = :input_lei
  AND   em.is_current = TRUE;
```

### 5.2 Counterparty screening — any flag against a board-member individual

```sql
SELECT  wi.full_name,
        wi.risk_category_code,
        ARRAY_AGG(sl.sanctions_list_code) FILTER (WHERE sl.is_current_listing) AS active_lists,
        ARRAY_AGG(pl.role_title)         FILTER (WHERE pl.is_active_role)     AS active_pep_roles
FROM    lseg_wc.wc_individuals          wi
LEFT JOIN lseg_wc.wc_sanctions_listings sl USING (wc_subject_id)
LEFT JOIN lseg_wc.wc_pep_listings       pl USING (wc_subject_id)
WHERE   wi.wc_subject_id = :wc_subject_id
  AND   wi.is_current     = TRUE
GROUP BY wi.full_name, wi.risk_category_code;
```

### 5.3 Bulk negative-screen a list of LEIs (for onboarding pipeline)

```sql
WITH input_leis AS (SELECT UNNEST(ARRAY[:leis]) AS lei),
matched AS (
    SELECT  i.lei,
            wo.wc_subject_id,
            wo.risk_category_code
    FROM    input_leis i
    LEFT JOIN lseg_wc.wc_organisations wo
      ON    wo.lei = i.lei
      AND   wo.is_current = TRUE
)
SELECT  lei,
        COALESCE(risk_category_code, 'NONE_FLAGGED') AS risk
FROM    matched;
```

## 6. Known quirks & compliance notes

- **Name matching is HARD.** Romanisation differences, missing diacritics,
  and patronymic ordering generate false positives. Production systems must
  combine `wc_aliases` + phonetic matching (Soundex / Double Metaphone) +
  human review. The catalog deliberately does not ship a one-step "screen
  by name" view to discourage uncritical use.
- A delisted (`is_current_listing = FALSE`) sanctions row remains in the
  table and **must** be queryable for historical investigations (e.g. "was
  this counterparty sanctioned on the date we traded with them?").
- `risk_category_code = 'NONE_FLAGGED'` records exist because the firm
  sometimes loads its own counterparty universe with no current flag, so
  that future re-screens can match instantly. Do not confuse "in the table
  with NONE_FLAGGED" with "not in the table" — both mean "clean".
- The assistant must **never** auto-execute a World-Check query without an
  explicit user opt-in, even with valid entitlements. PII surface area is
  audited.
