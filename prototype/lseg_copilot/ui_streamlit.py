"""Streamlit chat UI for the LSEG Data Copilot prototype.

Run with:
    streamlit run prototype/lseg_copilot/ui_streamlit.py
"""
from __future__ import annotations

import os

import streamlit as st

from .catalog import Catalog
from .data_loader import load_sample_data, open_warehouse
from .indexer import build_index
from .planner import Planner
from .reasoner import LLMReasoner, OpenAIChatClient, StubReasoner
from .retriever import HybridRetriever
from .sql_validator import validate_sql


@st.cache_resource(show_spinner="Loading catalog & sample data...")
def _bootstrap():
    catalog = Catalog.load()
    artifacts = build_index(catalog=catalog, embed=False)
    retriever = HybridRetriever(artifacts, catalog)
    planner = Planner(catalog)
    con = open_warehouse()
    load_sample_data(con, catalog=catalog)
    return catalog, retriever, planner, con


def main() -> None:
    st.set_page_config(page_title="LSEG Data Copilot", layout="wide")
    st.title("LSEG Data Copilot — prototype")
    st.caption("RAG + Text-to-SQL over a mock LSEG enterprise catalog.")

    catalog, retriever, planner, con = _bootstrap()
    with st.sidebar:
        st.markdown(f"**Catalog version**: `{catalog.manifest.catalog_version}`")
        st.markdown(f"**Tables**: {len(catalog.tables)}")
        ents = st.multiselect(
            "Entitlements",
            ["LSEG_WC_VIEWER", "LSEG_WC_INVESTIGATOR"],
            default=[],
            help="Restricted tables (e.g. World-Check) require entitlements.",
        )
        use_llm = st.checkbox(
            "Use LLM (requires OPENAI_API_KEY)",
            value=bool(os.environ.get("OPENAI_API_KEY")),
        )

    if "history" not in st.session_state:
        st.session_state["history"] = []
    for role, content in st.session_state["history"]:
        with st.chat_message(role):
            st.markdown(content)

    question = st.chat_input("Ask about the LSEG catalog...")
    if not question:
        return

    st.session_state["history"].append(("user", question))
    with st.chat_message("user"):
        st.markdown(question)

    retrieved = retriever.search(question, top_k=8)
    plan = planner.plan(question, retrieved, user_entitlements=ents)
    if use_llm and os.environ.get("OPENAI_API_KEY"):
        reasoner = LLMReasoner(catalog, OpenAIChatClient())
    else:
        reasoner = StubReasoner(catalog)
    answer = reasoner.answer(plan)

    with st.chat_message("assistant"):
        st.markdown(answer.text)
        if answer.refusal:
            st.error("Refused due to entitlement check.")
        if answer.citations:
            with st.expander("Citations"):
                for c in answer.citations:
                    st.markdown(f"- `{c}`")
        if answer.sql:
            validation = validate_sql(answer.sql, catalog)
            st.code(validation.sql, language="sql")
            if validation.errors:
                st.error(f"SQL validation errors: {validation.errors}")
            for w in validation.warnings:
                st.warning(w)
            if validation.ok:
                try:
                    df = con.execute(validation.sql).fetchdf()
                    st.dataframe(df)
                except Exception as exc:
                    st.error(f"Execution error: {exc}")
    st.session_state["history"].append(("assistant", answer.text))


if __name__ == "__main__":
    main()
