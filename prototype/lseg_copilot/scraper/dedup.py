"""De-duplicate scraped knowledge documents using content hashing."""
from __future__ import annotations

import hashlib
from pathlib import Path


def dedup_directory(knowledge_dir: Path, *, dry_run: bool = False) -> list[str]:
    """Remove duplicate markdown files by content hash. Returns paths removed."""
    hashes: dict[str, Path] = {}
    removed: list[str] = []

    for md_path in sorted(knowledge_dir.rglob("*.md")):
        content = md_path.read_text(encoding="utf-8", errors="replace")
        # Hash the body only (strip frontmatter).
        body = _strip_frontmatter(content)
        h = hashlib.sha256(body.encode("utf-8")).hexdigest()

        if h in hashes:
            removed.append(str(md_path))
            if not dry_run:
                md_path.unlink()
        else:
            hashes[h] = md_path

    return removed


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter for hashing purposes."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3:].strip()
    return text.strip()
