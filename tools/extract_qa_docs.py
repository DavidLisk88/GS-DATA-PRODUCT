"""Extract structured content from LSEG Quantitative Analytics PDF docs.

Outputs generated artifacts under QA-DOCS/_extracted:
- manifest.json: run summary
- inventory.csv/json: document-level metadata
- pages.jsonl: page-level extracted text
- chunks.jsonl: smaller searchable text chunks
- raw_pdf_tables.jsonl: tables detected by pdfplumber
- qa_tables.csv/json: inferred QA database table sections
- qa_columns.csv/json: inferred field/type/nullability/description rows
- relationships.csv/json: simple cross-reference/join hints
- schema_patterns.json: repeated schema/convention statements
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pdfplumber
from pypdf import PdfReader


TABLE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,}$")
VERSION_RE = re.compile(r"\bVersion\s+([0-9]+(?:\.[0-9]+)*(?:\s*[A-Za-z0-9.-]+)?)", re.IGNORECASE)
DATE_RE = re.compile(r"\((\d{4}-\d{2}-\d{2})\)")
COLUMN_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9_]{1,})\s+"
    r"([A-Za-z][A-Za-z0-9_]*(?:\([^)]*\))?)\s+"
    r"(Yes|No|Y|N|Nullable|Not\s+Nullable|NULL|NOT\s+NULL)\s+"
    r"(.+)$",
    re.IGNORECASE,
)

SKIP_TABLE_TOKENS = {
    "CORPORATE",
    "Contents",
    "Introduction",
    "Subscriptions",
    "Exposure",
    "Tables",
    "Table",
    "NOTE",
    "Note",
    "ITEM",
    "Item",
    "Data",
    "Values",
    "Month",
    "Descriptions",
    "Presentation",
    "Fundamentals",
    "Indexes",
    "Field",
    "Fields",
    "Type",
    "Nullable",
    "Description",
    "Update",
    "Cycle",
    "Adjusted",
    "IndexFields",
    "Index",
}


@dataclass
class DocumentRecord:
    document_id: str
    filename: str
    title: str
    version: str | None
    effective_date: str | None
    page_count: int
    file_size_bytes: int
    extracted_pages: int
    extraction_warning: str | None = None


@dataclass
class TableRecord:
    document_id: str
    filename: str
    table_name: str
    title_or_description: str | None
    update_cycle: str | None
    adjusted: str | None
    indexes_raw: str | None
    first_page: int
    last_page: int


@dataclass
class ColumnRecord:
    document_id: str
    filename: str
    table_name: str
    field_name: str
    data_type: str
    nullable: str
    description: str
    page: int


@dataclass
class RelationshipRecord:
    document_id: str
    filename: str
    table_name: str | None
    field_name: str | None
    target_table: str | None
    target_field: str | None
    relationship_type: str
    evidence: str
    page: int


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract QA PDF schema docs.")
    parser.add_argument("--source", default="QA-DOCS", help="Folder containing QA PDFs.")
    parser.add_argument("--out", default="QA-DOCS/_extracted", help="Output folder.")
    parser.add_argument(
        "--raw-tables",
        action="store_true",
        help="Also run pdfplumber table detection. Slower; text/schema extraction does not require it.",
    )
    args = parser.parse_args()

    source_dir = Path(args.source)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_paths = sorted(source_dir.glob("*.pdf"))
    inventory: list[DocumentRecord] = []
    table_records: list[TableRecord] = []
    column_records: list[ColumnRecord] = []
    relationship_records: list[RelationshipRecord] = []
    pattern_records: list[dict] = []

    pages_path = out_dir / "pages.jsonl"
    chunks_path = out_dir / "chunks.jsonl"
    raw_tables_path = out_dir / "raw_pdf_tables.jsonl"

    with pages_path.open("w", encoding="utf-8") as pages_fh, chunks_path.open(
        "w", encoding="utf-8"
    ) as chunks_fh, raw_tables_path.open("w", encoding="utf-8") as raw_tables_fh:
        for pdf_path in pdf_paths:
            result = extract_document(
                pdf_path,
                pages_fh,
                chunks_fh,
                raw_tables_fh,
                extract_raw_tables=args.raw_tables,
            )
            inventory.append(result["document"])
            table_records.extend(result["tables"])
            column_records.extend(result["columns"])
            relationship_records.extend(result["relationships"])
            pattern_records.extend(result["patterns"])

    write_records(out_dir / "inventory.csv", inventory)
    write_json(out_dir / "inventory.json", [asdict(r) for r in inventory])
    write_records(out_dir / "qa_tables.csv", table_records)
    write_json(out_dir / "qa_tables.json", [asdict(r) for r in table_records])
    write_records(out_dir / "qa_columns.csv", column_records)
    write_json(out_dir / "qa_columns.json", [asdict(r) for r in column_records])
    write_records(out_dir / "relationships.csv", relationship_records)
    write_json(out_dir / "relationships.json", [asdict(r) for r in relationship_records])
    write_json(out_dir / "schema_patterns.json", dedupe_patterns(pattern_records))

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(source_dir),
        "output_dir": str(out_dir),
        "pdf_count": len(pdf_paths),
        "documents": len(inventory),
        "tables_inferred": len(table_records),
        "columns_inferred": len(column_records),
        "relationships_inferred": len(relationship_records),
        "raw_pdf_tables_enabled": args.raw_tables,
        "artifacts": [
            "inventory.csv",
            "inventory.json",
            "pages.jsonl",
            "chunks.jsonl",
            "raw_pdf_tables.jsonl",
            "qa_tables.csv",
            "qa_tables.json",
            "qa_columns.csv",
            "qa_columns.json",
            "relationships.csv",
            "relationships.json",
            "schema_patterns.json",
        ],
    }
    write_json(out_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2))


def extract_document(
    pdf_path: Path,
    pages_fh,
    chunks_fh,
    raw_tables_fh,
    *,
    extract_raw_tables: bool,
) -> dict:
    document_id = slugify(pdf_path.stem)
    warning = None
    pages: list[dict] = []
    try:
        reader = PdfReader(str(pdf_path))
        for page_index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            page_record = {
                "document_id": document_id,
                "filename": pdf_path.name,
                "page": page_index,
                "text": text,
                "sha1": sha1(text),
            }
            pages.append(page_record)
            pages_fh.write(json.dumps(page_record, ensure_ascii=False) + "\n")
            for chunk in chunk_page(document_id, pdf_path.name, page_index, text):
                chunks_fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        if extract_raw_tables:
            with pdfplumber.open(pdf_path) as pdf:
                for page_index, page in enumerate(pdf.pages, start=1):
                    tables = page.extract_tables() or []
                    for table_index, table in enumerate(tables, start=1):
                        raw_tables_fh.write(
                            json.dumps(
                                {
                                    "document_id": document_id,
                                    "filename": pdf_path.name,
                                    "page": page_index,
                                    "table_index": table_index,
                                    "rows": table,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
    except Exception as exc:  # keep going across 45 PDFs
        warning = f"{type(exc).__name__}: {exc}"

    first_text = pages[0]["text"] if pages else ""
    title = infer_title(first_text, pdf_path.stem)
    document = DocumentRecord(
        document_id=document_id,
        filename=pdf_path.name,
        title=title,
        version=infer_version(first_text, pdf_path.name),
        effective_date=infer_effective_date(pdf_path.name),
        page_count=len(pages),
        file_size_bytes=pdf_path.stat().st_size,
        extracted_pages=sum(1 for page in pages if page["text"].strip()),
        extraction_warning=warning,
    )

    tables, columns = infer_tables_and_columns(document, pages)
    relationships = infer_relationships(document, pages, columns)
    patterns = infer_patterns(document, pages)

    return {
        "document": document,
        "tables": tables,
        "columns": columns,
        "relationships": relationships,
        "patterns": patterns,
    }


def infer_tables_and_columns(
    document: DocumentRecord, pages: list[dict]
) -> tuple[list[TableRecord], list[ColumnRecord]]:
    tables: list[TableRecord] = []
    columns: list[ColumnRecord] = []
    current_table: dict | None = None
    current_column: ColumnRecord | None = None
    collecting_indexes = False

    def close_table(last_page: int) -> None:
        nonlocal current_table
        if not current_table:
            return
        tables.append(
            TableRecord(
                document_id=document.document_id,
                filename=document.filename,
                table_name=current_table["table_name"],
                title_or_description=current_table.get("description"),
                update_cycle=current_table.get("update_cycle"),
                adjusted=current_table.get("adjusted"),
                indexes_raw=" ".join(current_table.get("indexes", [])).strip() or None,
                first_page=current_table["first_page"],
                last_page=last_page,
            )
        )
        current_table = None

    for page in pages:
        page_no = int(page["page"])
        lines = normalize_lines(page["text"].splitlines())
        for idx, line in enumerate(lines):
            table_heading = parse_table_heading(line, lines, idx)
            if table_heading:
                table_name, heading_title = table_heading
                close_table(page_no)
                current_table = {
                    "table_name": table_name,
                    "first_page": page_no,
                    "description": heading_title,
                    "update_cycle": None,
                    "adjusted": None,
                    "indexes": [],
                }
                current_column = None
                collecting_indexes = False
                continue

            if not current_table:
                continue

            if " table " in f" {line.lower()} ":
                if current_table.get("description"):
                    if line not in current_table["description"]:
                        current_table["description"] = f"{current_table['description']} | {line}"
                else:
                    current_table["description"] = line

            if line.lower().startswith("update cycle:"):
                current_table["update_cycle"] = line.split(":", 1)[1].strip()
                collecting_indexes = False
                continue

            if line.lower().startswith("adjusted:"):
                current_table["adjusted"] = line.split(":", 1)[1].strip()
                collecting_indexes = False
                continue

            compact = line.replace(" ", "").lower()
            if compact in {"indexesindexfields", "indexesindexfields", "indexindexfields"} or line.lower().startswith("indexes index"):
                collecting_indexes = True
                continue

            if line.lower().startswith("field") and "type" in line.lower() and "nullable" in line.lower():
                collecting_indexes = False
                current_column = None
                continue

            match = COLUMN_RE.match(line)
            if match:
                current_column = ColumnRecord(
                    document_id=document.document_id,
                    filename=document.filename,
                    table_name=current_table["table_name"],
                    field_name=match.group(1),
                    data_type=match.group(2),
                    nullable=match.group(3),
                    description=match.group(4).strip(),
                    page=page_no,
                )
                columns.append(current_column)
                collecting_indexes = False
                continue

            if collecting_indexes and line and not line.lower().startswith("field"):
                current_table["indexes"].append(line)
                continue

            if current_column and is_column_continuation(line):
                current_column.description = f"{current_column.description} {line}".strip()

    if pages:
        close_table(int(pages[-1]["page"]))
    return tables, columns


def infer_relationships(
    document: DocumentRecord,
    pages: list[dict],
    columns: list[ColumnRecord],
) -> list[RelationshipRecord]:
    relationships: list[RelationshipRecord] = []
    column_by_page_and_name = {(c.page, c.field_name): c for c in columns}
    for page in pages:
        page_no = int(page["page"])
        for sentence in split_sentences(page["text"]):
            normalized = " ".join(sentence.split())
            if "cross-reference" in normalized.lower() or "cross references" in normalized.lower():
                target_table = infer_target_table(normalized)
                field_name = infer_field_name_from_sentence(normalized)
                source_col = column_by_page_and_name.get((page_no, field_name or ""))
                relationships.append(
                    RelationshipRecord(
                        document_id=document.document_id,
                        filename=document.filename,
                        table_name=source_col.table_name if source_col else None,
                        field_name=field_name,
                        target_table=target_table,
                        target_field="Code" if target_table and "Code field" in normalized else None,
                        relationship_type="cross_reference",
                        evidence=normalized[:1000],
                        page=page_no,
                    )
                )
            if re.search(r"\bjoin\b|\bjoins\b", normalized, flags=re.IGNORECASE) and re.search(
                r"\bon\b", normalized, flags=re.IGNORECASE
            ):
                relationships.append(
                    RelationshipRecord(
                        document_id=document.document_id,
                        filename=document.filename,
                        table_name=None,
                        field_name=None,
                        target_table=infer_target_table(normalized),
                        target_field=None,
                        relationship_type="join_hint",
                        evidence=normalized[:1000],
                        page=page_no,
                    )
                )
    return relationships


def infer_patterns(document: DocumentRecord, pages: list[dict]) -> list[dict]:
    keywords = (
        "Table Name Conventions",
        "Zero Values and Nulls",
        "Update Cycle",
        "Adjusted",
        "Indexes",
        "Field, Type, Nullable",
        "Pervasive",
        "Oracle",
        "Snowflake",
        "effective",
        "expire",
        "activation",
        "PermID",
    )
    patterns: list[dict] = []
    for page in pages:
        for sentence in split_sentences(page["text"]):
            compact = " ".join(sentence.split())
            if any(k.lower() in compact.lower() for k in keywords):
                patterns.append(
                    {
                        "document_id": document.document_id,
                        "filename": document.filename,
                        "page": page["page"],
                        "pattern_text": compact[:1200],
                    }
                )
    return patterns


def chunk_page(document_id: str, filename: str, page: int, text: str) -> Iterable[dict]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|(?<=\.)\s+(?=[A-Z][A-Za-z ]{4,}:)", text) if p.strip()]
    buffer: list[str] = []
    char_count = 0
    chunk_index = 1
    for paragraph in paragraphs or [text]:
        if char_count + len(paragraph) > 2500 and buffer:
            body = "\n".join(buffer)
            yield chunk_record(document_id, filename, page, chunk_index, body)
            chunk_index += 1
            buffer = []
            char_count = 0
        buffer.append(paragraph)
        char_count += len(paragraph)
    if buffer:
        body = "\n".join(buffer)
        yield chunk_record(document_id, filename, page, chunk_index, body)


def chunk_record(document_id: str, filename: str, page: int, chunk_index: int, text: str) -> dict:
    return {
        "chunk_id": sha1(f"{document_id}:{page}:{chunk_index}:{text}")[:16],
        "document_id": document_id,
        "filename": filename,
        "page": page,
        "chunk_index": chunk_index,
        "text": text,
        "sha1": sha1(text),
    }


def parse_table_heading(line: str, lines: list[str], idx: int) -> tuple[str, str | None] | None:
    colon_match = re.match(r"^([A-Za-z][A-Za-z0-9_]{2,})\s*:\s*(.+)$", line)
    if colon_match:
        table_name = colon_match.group(1)
        title = colon_match.group(2).strip()
        if is_valid_table_name(table_name, lines, idx, extra_context=title):
            return table_name, title
        return None

    if is_valid_table_name(line, lines, idx, extra_context=""):
        return line, None
    return None


def is_valid_table_name(table_name: str, lines: list[str], idx: int, *, extra_context: str) -> bool:
    if table_name in SKIP_TABLE_TOKENS or table_name.strip(" .") in SKIP_TABLE_TOKENS:
        return False
    if not TABLE_NAME_RE.match(table_name):
        return False
    if len(table_name) < 4 or len(table_name) > 64:
        return False
    window = " ".join(lines[idx + 1 : idx + 8]).lower()
    context = f"{extra_context} {window}".lower()
    return any(token in context for token in ("this table", "update cycle:", "indexes", "field type nullable"))


def is_column_continuation(line: str) -> bool:
    if not line or line in SKIP_TABLE_TOKENS:
        return False
    if COLUMN_RE.match(line) or TABLE_NAME_RE.match(line):
        return False
    lower = line.lower()
    if lower.startswith(("update cycle:", "adjusted:", "indexes", "field ")):
        return False
    return True


def infer_title(first_page_text: str, fallback: str) -> str:
    lines = normalize_lines(first_page_text.splitlines())
    useful = [line for line in lines if line and line != "CORPORATE"]
    if useful:
        return " | ".join(useful[:3])[:300]
    return fallback


def infer_version(text: str, filename: str) -> str | None:
    match = VERSION_RE.search(text) or re.search(r"\bv([0-9]+(?:\.[0-9]+)+)\b", filename, re.IGNORECASE)
    return match.group(1).strip() if match else None


def infer_effective_date(filename: str) -> str | None:
    match = DATE_RE.search(filename)
    return match.group(1) if match else None


def infer_target_table(sentence: str) -> str | None:
    match = re.search(r"\b([A-Z][A-Za-z0-9_]{2,})\s+table\b", sentence)
    if match:
        return match.group(1)
    match = re.search(r"\b(?:join|joins|with|from)\s+([A-Z][A-Za-z0-9_]{2,})\b", sentence, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def infer_field_name_from_sentence(sentence: str) -> str | None:
    match = re.match(r"^([A-Za-z][A-Za-z0-9_]{1,})\b", sentence.strip())
    return match.group(1) if match else None


def split_sentences(text: str) -> list[str]:
    normalized = text.replace("\n", " ")
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", normalized) if s.strip()]


def normalize_lines(lines: Iterable[str]) -> list[str]:
    return [" ".join(line.replace("�", "-").split()) for line in lines if line and line.strip()]


def dedupe_patterns(records: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for record in records:
        key = sha1(record["pattern_text"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def write_records(path: Path, records: list) -> None:
    rows = [asdict(record) for record in records]
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return slug[:120]


if __name__ == "__main__":
    main()