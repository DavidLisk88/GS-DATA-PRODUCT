"""Document chunker + lexical (BM25) + symbol indexer for the LSEG mock catalog.

We deliberately keep dense embeddings *optional*: the prototype must run
without an API key. If `sentence-transformers` and `faiss-cpu` are installed,
we additionally build a FAISS index for semantic search; otherwise we degrade
gracefully to BM25 + symbol-boost only.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from rank_bm25 import BM25Okapi

from .catalog import Catalog
from .paths import workspace_paths

LOGGER = logging.getLogger(__name__)

# Try to load the embedding stack; if missing, we run lexical-only.
try:
    import faiss  # type: ignore
    import numpy as np  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore

    _EMBEDDINGS_AVAILABLE = True
except Exception:  # pragma: no cover - optional dep
    _EMBEDDINGS_AVAILABLE = False


_DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# --------------------------------------------------------------------------- #
# Chunk model                                                                 #
# --------------------------------------------------------------------------- #


@dataclass
class Chunk:
    chunk_id: str
    source_path: str  # workspace-relative
    title: str
    text: str
    symbols: list[str] = field(default_factory=list)  # table FQNs / column names found

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Chunking                                                                    #
# --------------------------------------------------------------------------- #


_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def chunk_markdown(text: str, source_path: str) -> list[Chunk]:
    """Split a markdown doc on H2/H3 boundaries. Falls back to whole-doc chunk."""
    headers = list(_HEADER_RE.finditer(text))
    if not headers:
        return [
            Chunk(
                chunk_id=_chunk_id(source_path, "doc"),
                source_path=source_path,
                title=Path(source_path).stem,
                text=text.strip(),
            )
        ]

    # Slice between headers; treat top-of-file as its own chunk if non-empty.
    chunks: list[Chunk] = []
    pre = text[: headers[0].start()].strip()
    if pre:
        chunks.append(
            Chunk(
                chunk_id=_chunk_id(source_path, "preamble"),
                source_path=source_path,
                title=Path(source_path).stem,
                text=pre,
            )
        )

    for idx, match in enumerate(headers):
        level = len(match.group(1))
        title = match.group(2).strip()
        # Only chunk on H1/H2/H3
        if level > 3:
            continue
        start = match.start()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        chunks.append(
            Chunk(
                chunk_id=_chunk_id(source_path, title),
                source_path=source_path,
                title=title,
                text=body,
            )
        )
    return chunks


def _chunk_id(source_path: str, key: str) -> str:
    digest = hashlib.sha256(f"{source_path}::{key}".encode("utf-8")).hexdigest()[:12]
    return f"chk_{digest}"


# --------------------------------------------------------------------------- #
# Symbol tagging                                                              #
# --------------------------------------------------------------------------- #


def tag_symbols(chunk: Chunk, catalog_symbols: Iterable[str]) -> Chunk:
    text_lower = chunk.text.lower()
    found: list[str] = []
    for sym in catalog_symbols:
        if sym and sym.lower() in text_lower:
            found.append(sym)
    chunk.symbols = sorted(set(found))
    return chunk


# --------------------------------------------------------------------------- #
# Indexer                                                                     #
# --------------------------------------------------------------------------- #


@dataclass
class IndexArtifacts:
    chunks: list[Chunk]
    bm25_tokens: list[list[str]]  # parallel to chunks
    bm25: BM25Okapi
    embedding_model_name: str | None = None
    faiss_index: object | None = None  # faiss.Index or None
    embeddings: object | None = None  # np.ndarray or None


def _tokenise(text: str) -> list[str]:
    # cheap, deterministic tokeniser
    return re.findall(r"[A-Za-z0-9_]+", text.lower())


def build_index(
    *,
    catalog: Catalog | None = None,
    embed: bool = True,
    embedding_model_name: str = _DEFAULT_EMBEDDING_MODEL,
) -> IndexArtifacts:
    """Scan the catalog markdown docs + YAML schemas and produce a hybrid index."""
    paths = workspace_paths()
    catalog = catalog or Catalog.load()

    catalog_symbols = set(catalog.symbol_index.keys())
    catalog_symbols.update(t.fqn for t in catalog.tables)
    catalog_symbols.update(t.table_name for t in catalog.tables)

    chunks: list[Chunk] = []

    # Markdown docs
    for md_path in sorted(paths["docs_dir"].rglob("*.md")):
        rel = md_path.relative_to(paths["root"]).as_posix()
        text = md_path.read_text(encoding="utf-8")
        for chunk in chunk_markdown(text, rel):
            chunks.append(tag_symbols(chunk, catalog_symbols))

    # YAML schemas — treat each schema as one chunk
    for yaml_path in sorted(paths["schemas_dir"].glob("*.yaml")):
        rel = yaml_path.relative_to(paths["root"]).as_posix()
        text = yaml_path.read_text(encoding="utf-8")
        chunks.append(
            tag_symbols(
                Chunk(
                    chunk_id=_chunk_id(rel, "schema"),
                    source_path=rel,
                    title=yaml_path.stem,
                    text=text,
                ),
                catalog_symbols,
            )
        )

    LOGGER.info("Indexed %d chunks", len(chunks))

    bm25_tokens = [_tokenise(c.text) for c in chunks]
    bm25 = BM25Okapi(bm25_tokens)

    embeddings_array = None
    faiss_index = None
    model_name = None
    if embed and _EMBEDDINGS_AVAILABLE and chunks:
        try:
            model = SentenceTransformer(embedding_model_name)
            embeddings_array = model.encode(
                [c.text for c in chunks],
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            dim = embeddings_array.shape[1]
            faiss_index = faiss.IndexFlatIP(dim)
            faiss_index.add(embeddings_array)
            model_name = embedding_model_name
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Embedding build failed (%s) — falling back to lexical-only.", exc)

    return IndexArtifacts(
        chunks=chunks,
        bm25_tokens=bm25_tokens,
        bm25=bm25,
        embedding_model_name=model_name,
        faiss_index=faiss_index,
        embeddings=embeddings_array,
    )


# --------------------------------------------------------------------------- #
# Disk persistence (minimal: chunks.jsonl)                                    #
# --------------------------------------------------------------------------- #


def save_chunks(artifacts: IndexArtifacts, out_dir: Path | None = None) -> Path:
    paths = workspace_paths()
    out_dir = out_dir or paths["index_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = out_dir / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as fh:
        for ch in artifacts.chunks:
            fh.write(json.dumps(ch.to_dict()) + "\n")
    return chunks_path
