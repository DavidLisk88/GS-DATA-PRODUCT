"""Unit tests for lseg_copilot.indexer — covers chunk_markdown, tag_symbols,
_chunk_id, _tokenise, Chunk.to_dict, and save_chunks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lseg_copilot.indexer import (
    Chunk,
    _chunk_id,
    _tokenise,
    build_index,
    chunk_markdown,
    save_chunks,
    tag_symbols,
)


# ------------------------------------------------------------------ #
# _tokenise                                                           #
# ------------------------------------------------------------------ #

class TestTokenise:
    def test_basic_tokenisation(self) -> None:
        tokens = _tokenise("Hello World! foo_bar 123")
        assert tokens == ["hello", "world", "foo_bar", "123"]

    def test_empty_string(self) -> None:
        assert _tokenise("") == []

    def test_special_chars_stripped(self) -> None:
        tokens = _tokenise("price = $42.00")
        assert "price" in tokens
        assert "42" in tokens


# ------------------------------------------------------------------ #
# _chunk_id                                                           #
# ------------------------------------------------------------------ #

class TestChunkId:
    def test_deterministic(self) -> None:
        a = _chunk_id("docs/foo.md", "section1")
        b = _chunk_id("docs/foo.md", "section1")
        assert a == b

    def test_prefix(self) -> None:
        cid = _chunk_id("docs/foo.md", "bar")
        assert cid.startswith("chk_")

    def test_different_inputs_differ(self) -> None:
        a = _chunk_id("docs/a.md", "x")
        b = _chunk_id("docs/b.md", "x")
        assert a != b


# ------------------------------------------------------------------ #
# chunk_markdown                                                      #
# ------------------------------------------------------------------ #

class TestChunkMarkdown:
    def test_no_headers_returns_single_chunk(self) -> None:
        text = "Just a plain paragraph with no markdown headers."
        chunks = chunk_markdown(text, "docs/plain.md")
        assert len(chunks) == 1
        assert chunks[0].title == "plain"

    def test_h2_splits(self) -> None:
        text = "## Section A\nContent A.\n## Section B\nContent B."
        chunks = chunk_markdown(text, "docs/x.md")
        titles = [c.title for c in chunks]
        assert "Section A" in titles
        assert "Section B" in titles

    def test_preamble_captured(self) -> None:
        text = "Preamble text.\n## First header\nBody."
        chunks = chunk_markdown(text, "docs/y.md")
        assert len(chunks) >= 2
        assert chunks[0].title == "y"  # preamble uses file stem
        assert "Preamble" in chunks[0].text

    def test_h4_not_split(self) -> None:
        text = "## Main\nPara.\n#### Sub-sub\nDetail."
        chunks = chunk_markdown(text, "docs/z.md")
        # H4 should NOT create its own chunk — only H1-H3 split.
        titles = [c.title for c in chunks]
        assert "Sub-sub" not in titles

    def test_empty_body_skipped(self) -> None:
        text = "## Empty\n## Next\nReal content."
        chunks = chunk_markdown(text, "docs/e.md")
        # "Empty" header has no body between it and "Next", but the header
        # line itself is included in the chunk text, so it won't be empty.
        assert all(c.text.strip() for c in chunks)


# ------------------------------------------------------------------ #
# tag_symbols                                                         #
# ------------------------------------------------------------------ #

class TestTagSymbols:
    def test_matching_symbols_added(self) -> None:
        chunk = Chunk(
            chunk_id="c1",
            source_path="docs/a.md",
            title="Test",
            text="The entity_master table stores org_perm_id values.",
        )
        result = tag_symbols(chunk, ["entity_master", "org_perm_id", "ric"])
        assert "entity_master" in result.symbols
        assert "org_perm_id" in result.symbols
        assert "ric" not in result.symbols

    def test_case_insensitive(self) -> None:
        chunk = Chunk(
            chunk_id="c2",
            source_path="docs/b.md",
            title="Test",
            text="The ENTITY_MASTER table.",
        )
        result = tag_symbols(chunk, ["entity_master"])
        assert "entity_master" in result.symbols

    def test_empty_symbols_list(self) -> None:
        chunk = Chunk(
            chunk_id="c3",
            source_path="docs/c.md",
            title="Test",
            text="Some text.",
        )
        result = tag_symbols(chunk, [])
        assert result.symbols == []


# ------------------------------------------------------------------ #
# Chunk.to_dict                                                       #
# ------------------------------------------------------------------ #

class TestChunkToDict:
    def test_round_trip(self) -> None:
        chunk = Chunk(
            chunk_id="chk_abc",
            source_path="docs/x.md",
            title="Title",
            text="Body text",
            symbols=["lseg_ref.entity_master"],
        )
        d = chunk.to_dict()
        assert d["chunk_id"] == "chk_abc"
        assert d["symbols"] == ["lseg_ref.entity_master"]
        # Verify it's JSON-serialisable.
        json.dumps(d)


# ------------------------------------------------------------------ #
# save_chunks                                                         #
# ------------------------------------------------------------------ #

class TestSaveChunks:
    def test_writes_jsonl(self, tmp_path: Path) -> None:
        from lseg_copilot.catalog import Catalog
        artifacts = build_index(catalog=Catalog.load(), embed=False)
        out = save_chunks(artifacts, out_dir=tmp_path)
        assert out.exists()
        lines = out.read_text().strip().split("\n")
        assert len(lines) == len(artifacts.chunks)
        # Each line is valid JSON.
        for line in lines:
            json.loads(line)
