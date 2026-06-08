"""Catalog loader: reads schemas/catalog.json and the per-table YAML schemas
into typed Pydantic models, plus builds a lightweight symbol index used by
the retriever and the SQL planner."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .paths import workspace_paths


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class ColumnSpec(BaseModel):
    name: str
    type: str
    nullable: bool = True
    pk: bool = False
    description: str | None = None
    restricted: bool = False


class JoinSpec(BaseModel):
    to: str
    on: str
    cardinality: str = "many_to_one"


class TableSpec(BaseModel):
    fqn: str  # lseg_ref.entity_master
    domain: str
    description: str | None = None
    source_product: str | None = None
    update_cadence: str | None = None
    temporal_model: str | None = None
    pii_level: str | None = None
    restricted: bool = False
    required_entitlement: str | None = None
    grain: str | None = None
    pk: list[str] = Field(default_factory=list)
    partitioned_by: str | None = None
    columns: list[ColumnSpec] = Field(default_factory=list)
    joins: list[JoinSpec] = Field(default_factory=list)
    catalog_doc_path: str | None = None
    schema_path: str | None = None  # populated from catalog.json
    tags: list[str] = Field(default_factory=list)
    has_restricted_columns: bool = False
    approx_row_count: int | None = None

    @property
    def schema_name(self) -> str:
        return self.fqn.split(".", 1)[0]

    @property
    def table_name(self) -> str:
        return self.fqn.split(".", 1)[1]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


class DomainSpec(BaseModel):
    code: str
    name: str
    anchor_keys: list[str] = Field(default_factory=list)


class CatalogManifest(BaseModel):
    catalog_version: str
    vendor: str
    license_tier: str
    generated_at: str
    domains: list[DomainSpec]
    tables: list[dict[str, Any]]


# --------------------------------------------------------------------------- #
# Catalog object                                                              #
# --------------------------------------------------------------------------- #


class Catalog:
    """In-memory representation of the entire LSEG mock data catalog."""

    def __init__(
        self,
        manifest: CatalogManifest,
        tables: dict[str, TableSpec],
        symbol_index: dict[str, list[str]],
    ) -> None:
        self.manifest = manifest
        self._tables = tables
        self.symbol_index = symbol_index  # symbol -> list of table FQNs that own it

    # ----- lookups -----

    @property
    def tables(self) -> list[TableSpec]:
        return list(self._tables.values())

    def get_table(self, fqn: str) -> TableSpec | None:
        return self._tables.get(fqn)

    def tables_in_domain(self, domain_code: str) -> list[TableSpec]:
        return [t for t in self._tables.values() if t.domain == domain_code]

    def tables_owning_symbol(self, symbol: str) -> list[TableSpec]:
        return [
            self._tables[fqn]
            for fqn in self.symbol_index.get(symbol.lower(), [])
            if fqn in self._tables
        ]

    def restricted_tables(self) -> list[TableSpec]:
        return [t for t in self._tables.values() if t.restricted or t.has_restricted_columns]

    # ----- loading -----

    @classmethod
    def load(cls, *, base_path: Path | None = None) -> "Catalog":
        paths = workspace_paths()
        root = base_path or paths["root"]
        manifest_path = root / "schemas" / "catalog.json"
        manifest_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = CatalogManifest(**manifest_raw)

        tables: dict[str, TableSpec] = {}
        for entry in manifest_raw["tables"]:
            schema_rel = entry.get("schema_path")
            yaml_path = root / schema_rel if schema_rel else None
            yaml_docs: list[dict[str, Any]] = []
            if yaml_path and yaml_path.exists():
                with yaml_path.open("r", encoding="utf-8") as fh:
                    for doc in yaml.safe_load_all(fh):
                        if doc:
                            yaml_docs.append(doc)

            # If the YAML file holds multiple tables, pick the one whose
            # `table:` field matches this catalog entry's fqn. If none match
            # (older schema files that only have one doc and use a slightly
            # different fqn), fall back to the single doc.
            entry_fqn = entry["fqn"]
            matched_docs = [d for d in yaml_docs if d.get("table") == entry_fqn]
            if matched_docs:
                docs_to_use = matched_docs
            elif len(yaml_docs) == 1:
                docs_to_use = yaml_docs
            else:
                docs_to_use = [{}]  # no schema details available

            for yaml_doc in docs_to_use:
                yaml_doc = _normalize_yaml_doc(yaml_doc)
                fqn = yaml_doc.get("table") or entry_fqn
                spec_kwargs = {
                    **{k: v for k, v in entry.items() if k not in {"fqn", "schema_path"}},
                    **yaml_doc,
                    "fqn": fqn,
                    "schema_path": schema_rel,
                }
                # Drop catalog-only keys that aren't in TableSpec
                spec_kwargs.pop("doc_path", None)
                spec = TableSpec(**spec_kwargs)
                tables[spec.fqn] = spec

        symbol_index = _build_symbol_index(tables)
        return cls(manifest=manifest, tables=tables, symbol_index=symbol_index)


def _normalize_yaml_doc(doc: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(doc)
    joins = normalized.get("joins")
    if isinstance(joins, list):
        normalized["joins"] = [_normalize_join_spec(join) for join in joins]
    return normalized


def _normalize_join_spec(join: Any) -> Any:
    if not isinstance(join, dict):
        return join
    normalized = dict(join)
    if True in normalized and "on" not in normalized:
        normalized["on"] = normalized.pop(True)
    return normalized


def _build_symbol_index(tables: dict[str, TableSpec]) -> dict[str, list[str]]:
    """Map every lowercased table name, column name, FQN, and anchor key to
    the list of tables that contain it. Used by the retriever for symbol-boost."""
    index: dict[str, list[str]] = defaultdict(list)
    for fqn, table in tables.items():
        index[fqn.lower()].append(fqn)
        index[table.table_name.lower()].append(fqn)
        index[table.schema_name.lower()].append(fqn)
        for col in table.columns:
            index[col.name.lower()].append(fqn)
        for tag in table.tags:
            index[tag.lower()].append(fqn)
    return {k: sorted(set(v)) for k, v in index.items()}
