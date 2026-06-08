"""Streamlit chat UI for the LSEG Data Copilot prototype.

Run with:
    streamlit run prototype/lseg_copilot/ui_streamlit.py
"""
from __future__ import annotations

import os

import streamlit as st

from .pipeline import CopilotPipeline, bootstrap
from .reasoner import create_reasoner
from .sql_executor import execute_validated_sql


@st.cache_resource(show_spinner="Loading catalog & sample data...")
def _bootstrap() -> CopilotPipeline:
    return bootstrap(load_warehouse=True)


def main() -> None:
    st.set_page_config(page_title="LSEG Data Copilot", layout="wide")
    st.title("LSEG Data Copilot — prototype")
    st.caption("RAG + Text-to-SQL over a mock LSEG enterprise catalog.")

    pipe = _bootstrap()
    with st.sidebar:
        st.markdown(f"**Catalog version**: `{pipe.catalog.manifest.catalog_version}`")
        st.markdown(f"**Tables**: {len(pipe.catalog.tables)}")
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

    retrieved = pipe.retriever.search(question, top_k=8)
    plan = pipe.planner.plan(question, retrieved, user_entitlements=ents)
    reasoner = create_reasoner(pipe.catalog, use_llm=use_llm)
    answer = reasoner.answer(plan)

    with st.chat_message("assistant"):
        st.markdown(answer.text)
        if answer.refusal:
            st.error("Refused due to entitlement check.")
        if answer.citations:
            with st.expander("Citations"):
                for c in answer.citations:
                    st.markdown(f"- `{c}`")
        if answer.sql and pipe.warehouse is not None:
            result = execute_validated_sql(answer.sql, pipe.catalog, pipe.warehouse)
            st.code(result.validation.sql, language="sql")
            if result.validation.errors:
                st.error(f"SQL validation errors: {result.validation.errors}")
            for w in result.validation.warnings:
                st.warning(w)
            if result.executed:
                st.dataframe(result.dataframe)
            elif result.error:
                st.error(f"Execution error: {result.error}")
    st.session_state["history"].append(("assistant", answer.text))


if __name__ == "__main__":
    main()
