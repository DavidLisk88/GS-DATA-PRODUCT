"""Normalise scraped LSEG content into a standard markdown document format
with YAML frontmatter, suitable for the indexer pipeline."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


def to_markdown_doc(
    *,
    title: str,
    body: str,
    source_url: str,
    dataset: str | None = None,
    domain: str | None = None,
    tags: list[str] | None = None,
    doc_type: str = "qa_article",
) -> str:
    """Produce a markdown document with YAML frontmatter."""
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fm_lines = [
        "---",
        f"title: {_yaml_escape(title)}",
        f"source_url: {source_url}",
        f"doc_type: {doc_type}",
        f"scraped_at: {scraped_at}",
    ]
    if dataset:
        fm_lines.append(f"dataset: {dataset}")
    if domain:
        fm_lines.append(f"domain: {domain}")
    if tags:
        fm_lines.append(f"tags: [{', '.join(tags)}]")
    fm_lines.append("---")
    fm_lines.append("")

    body_clean = _normalise_body(body)
    fm_lines.append(f"# {title}")
    fm_lines.append("")
    fm_lines.append(body_clean)
    return "\n".join(fm_lines)


def detect_dataset(text: str) -> str | None:
    """Guess which LSEG dataset an article is about from its content."""
    lower = text.lower()
    dataset_signals: list[tuple[str, list[str]]] = [
        ("datastream", ["datastream", "ds2", "dscode", "dsqtinfo"]),
        ("worldscope", ["worldscope", "wscope", "ws_"]),
        ("ibes", ["i/b/e/s", "ibes", "ibes_", "estimate"]),
        ("starmine", ["starmine", "sm_"]),
        ("compustat", ["compustat", "cs_", "gvkey"]),
        ("tick_history", ["tick history", "tick_history", "normalised", "normalisedll2"]),
        ("ownership", ["ownership", "insider", "13f"]),
        ("esg", ["esg", "environmental", "governance", "eu taxonomy"]),
        ("fixed_income", ["fixed income", "bond", "credit default"]),
        ("symbology", ["symbology", "permid", "perm_id", "ric history"]),
        ("fundamentals", ["fundamental", "financials", "balance sheet", "income statement"]),
    ]
    for dataset, signals in dataset_signals:
        if any(sig in lower for sig in signals):
            return dataset
    return None


def detect_domain(dataset: str | None) -> str | None:
    """Map dataset name to catalog domain code."""
    if not dataset:
        return None
    mapping = {
        "datastream": "pricing",
        "worldscope": "fundamentals",
        "ibes": "estimates",
        "starmine": "analytics",
        "compustat": "fundamentals",
        "tick_history": "pricing",
        "ownership": "ownership",
        "esg": "esg",
        "fixed_income": "fixed_income",
        "symbology": "reference",
        "fundamentals": "fundamentals",
    }
    return mapping.get(dataset)


def extract_tags(text: str) -> list[str]:
    """Pull out relevant keyword tags from article text."""
    tags: list[str] = []
    lower = text.lower()
    tag_keywords = [
        "join", "query", "schema", "table", "column", "field",
        "permid", "ric", "ticker", "isin", "cusip",
        "point-in-time", "scd", "temporal",
        "sql", "snowflake", "oracle",
    ]
    for kw in tag_keywords:
        if kw in lower:
            tags.append(kw)
    return tags


def _normalise_body(text: str) -> str:
    """Clean up article body text."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def _yaml_escape(value: str) -> str:
    """Escape a string for safe YAML scalar output."""
    if any(c in value for c in ":#{}[]|>&*!"):
        return f'"{value}"'
    return value
