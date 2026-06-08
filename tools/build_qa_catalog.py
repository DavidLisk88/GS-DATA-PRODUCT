"""Build a production catalog from extracted QA documentation.

Reads QA-DOCS/_extracted/{qa_tables.json, qa_columns.json, relationships.json}
and emits:

  schemas/qa_catalog.json   – catalog manifest with all real QA tables
  schemas/qa/<doc_slug>.yaml – per-content-set YAML schema files

The output format is compatible with the existing ``catalog.py`` loader so the
prototype can load both mock and real QA schemas.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ── domain mapping ─────────────────────────────────────────────────────────
# Map QA document slugs (from filename) to (domain_code, schema_prefix) pairs.

_DOC_DOMAIN_MAP: dict[str, tuple[str, str]] = {
    "axioma":                   ("risk_models",       "qa_axioma"),
    "barra":                    ("risk_models",       "qa_barra"),
    "crb":                      ("commodities",       "qa_crb"),
    "compustat_global":         ("fundamentals",      "qa_compustat_global"),
    "compustat_na":             ("fundamentals",      "qa_compustat_na"),
    "core_tables":              ("reference",         "qa_core"),
    "credit_default_swap":      ("fixed_income",      "qa_cds"),
    "data_explorers":           ("short_interest",    "qa_dataexp"),
    "datastream":               ("pricing",           "qa_datastream"),
    "deals_m_and_a":            ("corporate_actions", "qa_deals"),
    "esg":                      ("esg",               "qa_esg"),
    "esg_version_2":            ("esg",               "qa_esg_v2"),
    "eu_taxonomy":              ("esg",               "qa_eu_taxonomy"),
    "ftse_green_revenues":      ("esg",               "qa_ftse_green"),
    "fixed_income_ejv":         ("fixed_income",      "qa_fi_ejv"),
    "hanweck_options_data":     ("derivatives",       "qa_hanweck"),
    "ibes_estimates_version_2": ("estimates",         "qa_ibes_v2"),
    "ibes_pit":                 ("estimates",         "qa_ibes_pit"),
    "ibes":                     ("estimates",         "qa_ibes"),
    "idc_pricing_global":       ("pricing",           "qa_idc_global"),
    "idc_pricing_na":           ("pricing",           "qa_idc_na"),
    "index_data":               ("indices",           "qa_index"),
    "lseg_climate":             ("esg",               "qa_climate"),
    "lseg_esg":                 ("esg",               "qa_lseg_esg"),
    "lseg_financials":          ("fundamentals",      "qa_lseg_fin"),
    "lseg_indices":             ("indices",           "qa_lseg_idx"),
    "msci":                     ("risk_models",       "qa_msci"),
    "marketpsych_analytics":    ("sentiment",         "qa_mktpsych"),
    "northfield_risk_factors":  ("risk_models",       "qa_northfield"),
    "ownership_version_2":      ("ownership",         "qa_own_v2"),
    "ownership_and_global_insider": ("ownership",     "qa_own_insider"),
    "rdc":                      ("reference",         "qa_rdc"),
    "s_p_gics":                 ("reference",         "qa_gics"),
    "short_interest_data":      ("short_interest",    "qa_short_int"),
    "starmine_analytics":       ("analytics",         "qa_starmine_an"),
    "starmine":                 ("analytics",         "qa_starmine"),
    "starminemarketpsychmediasentiment": ("sentiment", "qa_starmine_mps"),
    "street_events":            ("events",            "qa_street_ev"),
    "symbology":                ("reference",         "qa_symbology"),
    "trbc":                     ("reference",         "qa_trbc"),
    "toyo_keizai":              ("fundamentals",      "qa_toyo"),
    "us_insider":               ("ownership",         "qa_us_insider"),
    "worldscope_point_in_time": ("fundamentals",      "qa_wscope_pit"),
    "worldscope":               ("fundamentals",      "qa_wscope"),
    "quantitative_analytics_schema_catalog": ("reference", "qa_catalog"),
}

# New domain definitions that don't exist in the mock catalog.
_EXTRA_DOMAINS: list[dict[str, Any]] = [
    {"code": "risk_models",    "name": "Risk Models (Axioma / Barra / MSCI / Northfield)", "anchor_keys": ["SecID"]},
    {"code": "commodities",    "name": "Commodities (CRB)",                                "anchor_keys": ["Code"]},
    {"code": "short_interest", "name": "Short Interest / Securities Lending",              "anchor_keys": ["SecID"]},
    {"code": "indices",        "name": "Index Data",                                       "anchor_keys": ["IndexID"]},
    {"code": "sentiment",      "name": "Sentiment / MarketPsych",                          "anchor_keys": ["AssetCode"]},
    {"code": "analytics",      "name": "Analytics (StarMine)",                             "anchor_keys": ["SecID"]},
    {"code": "events",         "name": "Street Events (Transcripts / Guidance)",           "anchor_keys": ["EventID"]},
    {"code": "ownership",      "name": "Ownership / Insider",                              "anchor_keys": ["SecID", "org_perm_id"]},
]


# ── helpers ────────────────────────────────────────────────────────────────

def _normalise_doc_key(document_id: str) -> str:
    """Extract a compact content-set key from the full document_id slug."""
    # Strip the 'qa_database_schema_' prefix and trailing version/date.
    key = re.sub(r"^qa_database_schema_", "", document_id)
    key = re.sub(r"_v\d.*$", "", key)
    key = re.sub(r"_\d{4}_\d{2}_\d{2}$", "", key)
    return key


def _normalise_type(raw_type: str) -> str:
    """Map QA PDF type names to the YAML schema conventions."""
    t = raw_type.strip()
    upper = t.upper()
    if upper.startswith("VARCHAR"):
        return t
    if upper.startswith("INT") and "(" not in t:
        return "INTEGER"
    if upper == "INT":
        return "INTEGER"
    if upper.startswith("FLOAT") or upper.startswith("REAL"):
        return "FLOAT"
    if upper.startswith("DATETIME"):
        return "TIMESTAMP(6)"
    if upper.startswith("SMALLINT"):
        return "SMALLINT"
    if upper.startswith("TINYINT"):
        return "TINYINT"
    if upper.startswith("BIGINT"):
        return "BIGINT"
    if upper.startswith("BIT"):
        return "BOOLEAN"
    if upper.startswith("NUMERIC") or upper.startswith("DECIMAL"):
        return t
    if upper.startswith("CHAR"):
        return t
    if upper.startswith("TEXT") or upper.startswith("NTEXT"):
        return "TEXT"
    if upper.startswith("NVARCHAR"):
        return t
    if upper.startswith("VARBINARY") or upper.startswith("IMAGE"):
        return t
    return t


def _normalise_nullable(raw: str) -> bool:
    val = raw.strip().lower()
    return val in {"yes", "y", "nullable", "null"}


def _build_doc_index(tables_data: list[dict]) -> dict[str, list[dict]]:
    """Group raw table records by document_id."""
    idx: dict[str, list[dict]] = defaultdict(list)
    for rec in tables_data:
        idx[rec["document_id"]].append(rec)
    return idx


def _build_column_index(columns_data: list[dict]) -> dict[str, list[dict]]:
    """Group columns by (document_id, table_name)."""
    idx: dict[str, list[dict]] = defaultdict(list)
    for rec in columns_data:
        key = f"{rec['document_id']}:{rec['table_name']}"
        idx[key].append(rec)
    return idx


def _build_relationship_index(rels_data: list[dict]) -> dict[str, list[dict]]:
    """Group relationships by document_id."""
    idx: dict[str, list[dict]] = defaultdict(list)
    for rec in rels_data:
        idx[rec["document_id"]].append(rec)
    return idx


# ── YAML generation ────────────────────────────────────────────────────────

def _make_yaml_doc(
    fqn: str,
    domain: str,
    table_rec: dict,
    columns: list[dict],
    doc_relationships: list[dict],
) -> dict[str, Any]:
    """Build a single YAML-serialisable dict for one table."""
    col_specs: list[dict[str, Any]] = []
    for col in columns:
        spec: dict[str, Any] = {
            "name": col["field_name"],
            "type": _normalise_type(col["data_type"]),
            "nullable": _normalise_nullable(col["nullable"]),
        }
        if col.get("description"):
            desc = col["description"].strip()
            if desc:
                spec["description"] = desc[:500]
        col_specs.append(spec)

    doc: dict[str, Any] = {
        "table": fqn,
        "domain": domain,
    }
    if table_rec.get("title_or_description"):
        doc["description"] = table_rec["title_or_description"][:500]
    if table_rec.get("update_cycle"):
        doc["update_cadence"] = table_rec["update_cycle"]
    if col_specs:
        doc["columns"] = col_specs

    # Attach join hints from relationships that target tables in the same doc.
    joins: list[dict[str, str]] = []
    table_name = table_rec["table_name"]
    for rel in doc_relationships:
        if rel.get("table_name") == table_name and rel.get("target_table"):
            joins.append({
                "to": rel["target_table"],
                "evidence": (rel.get("evidence") or "")[:300],
                "type": rel.get("relationship_type", "cross_reference"),
            })
    if joins:
        doc["join_hints"] = joins

    return doc


# ── main ───────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build QA catalog from extracted data.")
    parser.add_argument("--extracted", default="QA-DOCS/_extracted", help="Extracted data dir.")
    parser.add_argument("--out-catalog", default="schemas/qa_catalog.json", help="Output catalog JSON.")
    parser.add_argument("--out-schemas", default="schemas/qa", help="Output YAML schema dir.")
    args = parser.parse_args()

    extracted = Path(args.extracted)
    out_catalog_path = Path(args.out_catalog)
    out_schemas_dir = Path(args.out_schemas)
    out_schemas_dir.mkdir(parents=True, exist_ok=True)

    tables_data: list[dict] = json.loads((extracted / "qa_tables.json").read_text("utf-8"))
    columns_data: list[dict] = json.loads((extracted / "qa_columns.json").read_text("utf-8"))
    rels_data: list[dict] = json.loads((extracted / "relationships.json").read_text("utf-8"))

    doc_tables = _build_doc_index(tables_data)
    col_index = _build_column_index(columns_data)
    rel_index = _build_relationship_index(rels_data)

    all_tables: list[dict[str, Any]] = []
    yaml_files_written = 0
    skipped_docs: list[str] = []

    for document_id, table_recs in sorted(doc_tables.items()):
        doc_key = _normalise_doc_key(document_id)
        mapping = _DOC_DOMAIN_MAP.get(doc_key)
        if not mapping:
            skipped_docs.append(doc_key)
            continue

        domain_code, schema_prefix = mapping
        doc_rels = rel_index.get(document_id, [])

        yaml_docs: list[dict[str, Any]] = []
        for table_rec in table_recs:
            table_name = table_rec["table_name"]
            fqn = f"{schema_prefix}.{table_name}"
            columns = col_index.get(f"{document_id}:{table_name}", [])

            yaml_doc = _make_yaml_doc(fqn, domain_code, table_rec, columns, doc_rels)
            yaml_docs.append(yaml_doc)

            catalog_entry: dict[str, Any] = {
                "fqn": fqn,
                "domain": domain_code,
                "schema_path": f"schemas/qa/{doc_key}.yaml",
                "source_document": table_rec["filename"],
                "tags": [doc_key, domain_code, "qa_real"],
            }
            if table_rec.get("update_cycle"):
                catalog_entry["update_cadence"] = table_rec["update_cycle"]
            all_tables.append(catalog_entry)

        # Write multi-doc YAML
        yaml_path = out_schemas_dir / f"{doc_key}.yaml"
        with yaml_path.open("w", encoding="utf-8") as fh:
            for i, doc in enumerate(yaml_docs):
                if i > 0:
                    fh.write("---\n")
                yaml.dump(doc, fh, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)
        yaml_files_written += 1

    # Collect all domains.
    existing_domain_codes = {
        "reference", "pricing", "corporate_actions", "fundamentals",
        "estimates", "esg", "fx", "fixed_income", "derivatives", "funds", "world_check",
    }
    domains: list[dict[str, Any]] = []
    for d in _EXTRA_DOMAINS:
        if d["code"] not in existing_domain_codes:
            domains.append(d)

    catalog: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "catalog_version": f"qa-real.{datetime.now(timezone.utc).strftime('%Y.%m')}",
        "vendor": "London Stock Exchange Group (LSEG)",
        "license_tier": "Enterprise",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "QA Database Schema PDFs (45 documents)",
        "extra_domains": domains,
        "tables": all_tables,
    }

    out_catalog_path.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(all_tables)} table entries to {out_catalog_path}")
    print(f"Wrote {yaml_files_written} YAML schema files to {out_schemas_dir}/")
    if skipped_docs:
        print(f"Skipped {len(skipped_docs)} unmapped doc keys: {skipped_docs}")
    print(f"New domains added: {[d['code'] for d in domains]}")


if __name__ == "__main__":
    main()
