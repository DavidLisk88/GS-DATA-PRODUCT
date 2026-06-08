"""Resolve workspace paths regardless of where the CLI is invoked from."""
from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from `start` until we find the workspace marker (`schemas/catalog.json`)."""
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "schemas" / "catalog.json").exists():
            return parent
    raise FileNotFoundError(
        "Could not locate workspace root (no schemas/catalog.json found in any parent)."
    )


def workspace_paths() -> dict[str, Path]:
    root = find_repo_root()
    return {
        "root": root,
        "catalog_json": root / "schemas" / "catalog.json",
        "qa_catalog_json": root / "schemas" / "qa_catalog.json",
        "schemas_dir": root / "schemas",
        "qa_schemas_dir": root / "schemas" / "qa",
        "docs_dir": root / "docs",
        "qa_docs_dir": root / "QA-DOCS",
        "qa_extracted_dir": root / "QA-DOCS" / "_extracted",
        "sample_data_dir": root / "sample_data",
        "tests_dir": root / "tests",
        "fixtures_dir": root / "tests" / "fixtures",
        "goldset_dir": root / "tests" / "goldset",
        "index_dir": root / "prototype" / ".index",
    }
