"""CLI entry point. Examples:

    python -m lseg_copilot load-data
    python -m lseg_copilot index
    python -m lseg_copilot ask "What was Apple's close on 2026-05-28?"
    python -m lseg_copilot eval --kind sql --max 5
"""
from __future__ import annotations

import csv
import logging
import os
import sys
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .catalog import Catalog
from .data_loader import load_sample_data, open_warehouse, summarise_warehouse
from .indexer import build_index, save_chunks
from .paths import workspace_paths
from .planner import Planner
from .reasoner import LLMReasoner, OpenAIChatClient, StubReasoner
from .retriever import HybridRetriever
from .sql_validator import validate_sql

console = Console()


@click.group(help="LSEG Data Copilot prototype CLI.")
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# --------------------------------------------------------------------------- #
@main.command("load-data")
def load_data_cmd() -> None:
    """Load sample CSVs into an ephemeral DuckDB and print row counts."""
    con = open_warehouse()
    catalog = Catalog.load()
    loaded = load_sample_data(con, catalog=catalog)
    table = Table("table", "rows", title="Sample data loaded")
    for fqn, n in sorted(loaded.items()):
        table.add_row(fqn, str(n))
    console.print(table)


# --------------------------------------------------------------------------- #
@main.command("describe")
def describe_cmd() -> None:
    """Show catalog table count + restricted tables."""
    catalog = Catalog.load()
    console.print(
        Panel.fit(
            f"Catalog version: [bold]{catalog.manifest.catalog_version}[/bold]\n"
            f"Domains: {len(catalog.manifest.domains)}\n"
            f"Tables : {len(catalog.tables)}\n"
            f"Restricted tables: {len(catalog.restricted_tables())}",
            title="Catalog summary",
        )
    )
    table = Table("fqn", "domain", "temporal_model", "restricted")
    for spec in sorted(catalog.tables, key=lambda t: t.fqn):
        table.add_row(
            spec.fqn,
            spec.domain or "-",
            spec.temporal_model or "-",
            "yes" if spec.restricted or spec.has_restricted_columns else "",
        )
    console.print(table)


# --------------------------------------------------------------------------- #
@main.command("index")
@click.option("--no-embed", is_flag=True, help="Skip dense embeddings.")
def index_cmd(no_embed: bool) -> None:
    """Build the hybrid index (lexical + optional dense)."""
    catalog = Catalog.load()
    artifacts = build_index(catalog=catalog, embed=not no_embed)
    chunks_path = save_chunks(artifacts)
    mode = artifacts.embedding_model_name or "lexical-only"
    console.print(
        f"Indexed [bold]{len(artifacts.chunks)}[/bold] chunks ({mode}); "
        f"saved → {chunks_path}"
    )


# --------------------------------------------------------------------------- #
@main.command("ask")
@click.argument("question", type=str)
@click.option("--use-llm", is_flag=True, help="Use OpenAI client if OPENAI_API_KEY set.")
@click.option(
    "--entitlement",
    "entitlements",
    multiple=True,
    help="User entitlement codes (repeatable).",
)
@click.option("--execute/--no-execute", default=True, help="Execute generated SQL.")
def ask_cmd(question: str, use_llm: bool, entitlements: tuple[str, ...], execute: bool) -> None:
    """One-shot ask: retrieve → plan → reason → (optionally) execute SQL."""
    catalog = Catalog.load()
    artifacts = build_index(catalog=catalog, embed=False)  # cheap path
    retriever = HybridRetriever(artifacts, catalog)
    planner = Planner(catalog)

    retrieved = retriever.search(question, top_k=8)
    plan = planner.plan(question, retrieved, user_entitlements=list(entitlements))

    reasoner: StubReasoner | LLMReasoner
    if use_llm and os.environ.get("OPENAI_API_KEY"):
        reasoner = LLMReasoner(catalog, OpenAIChatClient())
    else:
        reasoner = StubReasoner(catalog)
    answer = reasoner.answer(plan)

    console.print(Panel.fit(answer.text, title="Answer"))
    if answer.citations:
        console.print("[bold]Citations:[/bold]")
        for c in answer.citations:
            console.print(f"  - {c}")
    if answer.sql:
        validation = validate_sql(answer.sql, catalog)
        console.print("\n[bold]Generated SQL:[/bold]")
        console.print(Syntax(validation.sql, "sql", theme="ansi_dark", word_wrap=True))
        if validation.errors:
            console.print(f"[red]SQL validation errors:[/red] {validation.errors}")
        for w in validation.warnings:
            console.print(f"[yellow]warn:[/yellow] {w}")
        if execute and validation.ok:
            con = open_warehouse()
            load_sample_data(con, catalog=catalog)
            try:
                df = con.execute(validation.sql).fetchdf()
                console.print("\n[bold]Result:[/bold]")
                console.print(df.to_string(index=False))
            except Exception as exc:
                console.print(f"[red]Execution error:[/red] {exc}")
                raise SystemExit(1) from exc


# --------------------------------------------------------------------------- #
@main.command("eval")
@click.option("--kind", type=click.Choice(["qa", "sql"]), default="sql")
@click.option("--max", "max_n", type=int, default=0, help="Limit number of cases (0=all).")
def eval_cmd(kind: str, max_n: int) -> None:
    """Run a smoke evaluation against the goldset."""
    paths = workspace_paths()
    catalog = Catalog.load()
    artifacts = build_index(catalog=catalog, embed=False)
    retriever = HybridRetriever(artifacts, catalog)
    planner = Planner(catalog)
    reasoner = StubReasoner(catalog)

    goldset_file = paths["goldset_dir"] / f"{kind}.yaml"
    if not goldset_file.exists():
        console.print(f"[red]Goldset file missing:[/red] {goldset_file}")
        sys.exit(1)
    spec = yaml.safe_load(goldset_file.read_text(encoding="utf-8"))
    questions = spec["questions"]
    if max_n:
        questions = questions[:max_n]

    if kind == "sql":
        con = open_warehouse()
        load_sample_data(con, catalog=catalog)
        _eval_sql(questions, con, catalog, retriever, planner, reasoner)
    else:
        _eval_qa(questions, retriever, planner, reasoner)


def _eval_sql(
    questions, con, catalog, retriever, planner, reasoner
) -> None:
    paths = workspace_paths()
    table = Table(
        "id", "intent", "exec_ok", "rows_ok", "tables_ok",
        title="SQL goldset smoke results",
    )
    passes = 0
    for q in questions:
        qid = q["id"]
        question = q["question"]
        retrieved = retriever.search(question, top_k=8)
        plan = planner.plan(question, retrieved, user_entitlements=q.get("user_entitlements"))
        answer = reasoner.answer(plan, question_id=qid)

        if q.get("expected_sql_action") == "refuse":
            ok = answer.refusal
            table.add_row(qid, q.get("intent", ""), "n/a", "n/a", "refused" if ok else "MISS")
            if ok:
                passes += 1
            continue

        exec_ok = False
        rows_ok = False
        tables_ok = False
        if answer.sql:
            validation = validate_sql(answer.sql, catalog)
            if validation.ok:
                try:
                    df = con.execute(validation.sql).fetchdf()
                    exec_ok = True
                    fix_path = q.get("fixture")
                    if fix_path:
                        fix_rows = _read_fixture(paths["root"] / fix_path)
                        rows_ok = _compare_rows(df, fix_rows)
                except Exception as exc:
                    console.print(f"[red]{qid} exec error:[/red] {exc}")

        expected_tables = set(q.get("expected_tables") or [])
        if expected_tables:
            actual_tables = set(plan.candidate_tables)
            tables_ok = bool(expected_tables & actual_tables)
        else:
            tables_ok = True

        table.add_row(
            qid,
            q.get("intent", ""),
            "ok" if exec_ok else "FAIL",
            "ok" if rows_ok else "FAIL",
            "ok" if tables_ok else "FAIL",
        )
        if exec_ok and rows_ok and tables_ok:
            passes += 1

    console.print(table)
    console.print(f"[bold]Passed:[/bold] {passes}/{len(questions)}")


def _eval_qa(questions, retriever, planner, reasoner) -> None:
    table = Table("id", "intent", "citation_recall", "must_mention_cov", title="Q&A smoke results")
    for q in questions:
        retrieved = retriever.search(q["question"], top_k=8)
        plan = planner.plan(
            q["question"], retrieved, user_entitlements=q.get("user_entitlements")
        )
        answer = reasoner.answer(plan, question_id=q["id"])
        expected_cit = set(q.get("expected_citations") or [])
        got_cit = set(answer.citations)
        if expected_cit:
            cit_recall = f"{len(got_cit & expected_cit)}/{len(expected_cit)}"
        else:
            cit_recall = "n/a" if not q.get("refusal_expected") else (
                "refused" if answer.refusal else "MISS"
            )
        must_mention = q.get("must_mention") or []
        if must_mention:
            text_lower = answer.text.lower()
            hits = sum(1 for m in must_mention if m.lower() in text_lower)
            mention_cov = f"{hits}/{len(must_mention)}"
        else:
            mention_cov = "n/a"
        table.add_row(q["id"], q.get("intent", ""), cit_recall, mention_cov)
    console.print(table)


def _read_fixture(path: Path) -> list[dict]:
    if not path.exists():
        console.print(f"[red]Fixture file missing:[/red] {path}")
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            return [row for row in reader]
    except (OSError, csv.Error) as exc:
        console.print(f"[red]Fixture read error ({path.name}):[/red] {exc}")
        return []


def _compare_rows(df, fixture_rows: list[dict]) -> bool:
    if len(df) != len(fixture_rows):
        return False
    if not fixture_rows:
        return True
    cols = list(fixture_rows[0].keys())
    # Reorder df columns to match fixture; missing column -> False.
    if not set(cols).issubset(df.columns.tolist()):
        return False
    df_norm = df[cols].astype(str).reset_index(drop=True)
    fx_norm = [{k: str(v) for k, v in row.items()} for row in fixture_rows]
    # Loose float comparison
    for i, fx_row in enumerate(fx_norm):
        for col in cols:
            try:
                a = float(df_norm.iloc[i][col])
                b = float(fx_row[col])
                if abs(a - b) > max(1e-3 * max(abs(a), abs(b)), 1e-3):
                    return False
            except ValueError:
                if df_norm.iloc[i][col].strip() != fx_row[col].strip():
                    return False
    return True


if __name__ == "__main__":
    main()
