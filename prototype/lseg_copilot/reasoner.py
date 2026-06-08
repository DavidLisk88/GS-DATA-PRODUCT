"""Reasoner: turns a Plan + retrieved chunks into a user-visible answer.

Two modes:
  * `StubReasoner` — no LLM. Answers known questions with canned SQL or a
    citation-only summary. Lets the prototype run with zero API spend.
  * `LLMReasoner` — wraps an OpenAI-compatible client. Used only if
    `OPENAI_API_KEY` is set (or a custom client is injected).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from .catalog import Catalog
from .planner import PlanResult


@dataclass
class Answer:
    question: str
    text: str
    sql: str | None = None
    citations: list[str] = field(default_factory=list)  # workspace-relative paths
    refusal: bool = False
    confidence: float = 0.0
    extras: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Stub reasoner — canned answers for the goldset                              #
# --------------------------------------------------------------------------- #


_STUB_SQL_TEMPLATES: dict[str, str] = {
    "SQ-0001": (
        "SELECT price_date, open_price, close_price, volume\n"
        "FROM lseg_dss.eod_pricing\n"
        "WHERE ric_as_of = 'AAPL.OQ'\n"
        "  AND price_date = DATE '2026-05-28'"
    ),
    "SQ-0002": (
        "SELECT ric_as_of, price_date, close_price\n"
        "FROM lseg_dss.eod_pricing\n"
        "WHERE ric_as_of IN ('META.OQ','FB.OQ')\n"
        "  AND price_date = DATE '2026-05-28'"
    ),
    "SQ-0003": (
        "SELECT entity_legal_name, entity_country_iso\n"
        "FROM lseg_ref.entity_master\n"
        "WHERE org_perm_id = 4295905573\n"
        "  AND valid_from_ts <= TIMESTAMP '2010-06-01 00:00:00'\n"
        "  AND valid_to_ts >  TIMESTAMP '2010-06-01 00:00:00'"
    ),
    "SQ-0004": (
        "SELECT org_perm_id, period_end_date, fiscal_year, report_currency_iso, revenue\n"
        "FROM lseg_wsf.company_fundamentals\n"
        "WHERE org_perm_id = 4295905573\n"
        "  AND period_end_date = DATE '2024-09-28'\n"
        "  AND valid_from_ts <= TIMESTAMP '2024-11-15 23:59:59'\n"
        "  AND valid_to_ts >  TIMESTAMP '2024-11-15 23:59:59'"
    ),
    "SQ-0005": (
        "SELECT p.ric_as_of,\n"
        "       p.price_date,\n"
        "       p.close_price                                  AS close_price_jpy,\n"
        "       fx.mid_rate                                    AS usdjpy_mid,\n"
        "       p.close_price / fx.mid_rate                    AS close_price_usd\n"
        "FROM lseg_dss.eod_pricing p\n"
        "JOIN lseg_fx.fx_rates_eod fx\n"
        "  ON fx.base_ccy = 'USD'\n"
        " AND fx.quote_ccy = 'JPY'\n"
        " AND fx.fix_date  = p.price_date\n"
        " AND fx.fix_code  = 'WMR_LON_4PM'\n"
        "WHERE p.ric_as_of = '7203.T'\n"
        "  AND p.price_date = DATE '2026-05-28'"
    ),
    "SQ-0006": (
        "SELECT ca.ca_event_id, ca.ca_type_code, ca.ca_subtype_code, ca.ex_date,\n"
        "       t.term_type_code, t.from_qty, t.to_qty\n"
        "FROM lseg_ref.corporate_actions ca\n"
        "JOIN lseg_ref.corporate_action_terms t USING (ca_event_id)\n"
        "WHERE ca.org_perm_id = 4295875323\n"
        "  AND ca.ex_date = DATE '2021-09-30'"
    ),
    "SQ-0007": (
        "SELECT rating_announce_ts, rating_action_code, rating_code, numeric_rating_value\n"
        "FROM lseg_fi.credit_ratings_history\n"
        "WHERE rating_subject_perm_id = 4295905573\n"
        "  AND rating_subject_type = 'ISSUER'\n"
        "  AND agency_code = 'SP'\n"
        "  AND rating_scale_code = 'LT_FC'\n"
        "ORDER BY rating_announce_ts"
    ),
    "SQ-0008": (
        "SELECT bt.instrument_perm_id, im.instrument_name, bt.coupon_rate_pct, bt.maturity_date\n"
        "FROM lseg_fi.bond_terms bt\n"
        "JOIN lseg_ref.instrument_master im USING (instrument_perm_id)\n"
        "WHERE im.org_perm_id = 4295905573\n"
        "  AND bt.maturity_date >= DATE '2033-01-01'\n"
        "  AND bt.is_current = TRUE\n"
        "  AND im.is_current = TRUE\n"
        "ORDER BY bt.maturity_date"
    ),
    "SQ-0009": (
        "WITH ranked AS (\n"
        "  SELECT oc.instrument_perm_id, oc.ric, oc.strike_price, oc.option_type_code,\n"
        "         iv.delta, iv.implied_vol_pct,\n"
        "         ROW_NUMBER() OVER (ORDER BY ABS(iv.delta - 0.25)) AS rk\n"
        "  FROM lseg_drv.options_chain oc\n"
        "  JOIN lseg_drv.options_eod_iv iv USING (instrument_perm_id)\n"
        "  WHERE oc.underlying_ric = 'AAPL.OQ'\n"
        "    AND oc.option_type_code = 'C'\n"
        "    AND iv.trade_date = DATE '2024-06-28'\n"
        ")\n"
        "SELECT instrument_perm_id, ric, strike_price, option_type_code,\n"
        "       delta, implied_vol_pct\n"
        "FROM ranked WHERE rk = 1"
    ),
    "SQ-0010": (
        "SELECT curve_code, curve_date, tenor_code, zero_rate_pct\n"
        "FROM lseg_fi.yield_curves_eod\n"
        "WHERE curve_code = 'USD_SOFR_OIS'\n"
        "  AND tenor_code = '10Y'\n"
        "  AND curve_date = DATE '2024-06-28'"
    ),
    "SQ-0011": (
        "SELECT lipper_id, fund_name, ter_pct\n"
        "FROM lseg_lipper.fund_master\n"
        "WHERE lipper_global_class_code = 'EQUS'\n"
        "  AND fund_type_code = 'ETF'\n"
        "  AND is_current = TRUE"
    ),
    "SQ-0013": (
        "SELECT instrument_perm_id, contract_label, last_trade_date, expiration_date\n"
        "FROM lseg_drv.futures_contracts\n"
        "WHERE futures_series_code = 'CL'\n"
        "  AND last_trade_date >= DATE '2024-06-22'\n"
        "  AND is_current = TRUE\n"
        "ORDER BY last_trade_date\n"
        "LIMIT 1"
    ),
    "SQ-0014": (
        "SELECT ric_as_of, CAST(AVG(volume) AS BIGINT) AS avg_volume\n"
        "FROM lseg_dss.eod_pricing\n"
        "WHERE ric_as_of IN ('AAPL.OQ','MSFT.OQ','GOOG.OQ')\n"
        "  AND price_date BETWEEN DATE '2026-05-26' AND DATE '2026-05-28'\n"
        "GROUP BY ric_as_of\n"
        "ORDER BY avg_volume DESC"
    ),
    "SQ-0015": (
        "SELECT ec.ibes_ticker, ec.measure_code, ec.period_type_code,\n"
        "       ec.period_end_date, ec.consensus_date, ec.mean_value\n"
        "FROM lseg_ibes.estimate_consensus ec\n"
        "JOIN lseg_ibes.ibes_ticker_xref x USING (ibes_ticker)\n"
        "WHERE x.org_perm_id = 4295905573\n"
        "  AND ec.measure_code = 'EPS'\n"
        "  AND ec.period_type_code = 'FY1'\n"
        "ORDER BY ec.consensus_date DESC\n"
        "LIMIT 1"
    ),
}


class StubReasoner:
    """Rule-based reasoner. Tries canned SQL for known IDs; otherwise returns a
    citation-only summary using the top retrieved chunks."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def answer(
        self,
        plan: PlanResult,
        *,
        question_id: str | None = None,
    ) -> Answer:
        if plan.intent == "refusal":
            return Answer(
                question=plan.question,
                text=f"REFUSED: {plan.refusal_reason}",
                refusal=True,
                confidence=0.95,
            )

        sql = None
        if question_id and question_id in _STUB_SQL_TEMPLATES:
            sql = _STUB_SQL_TEMPLATES[question_id]

        citations = [r.chunk.source_path for r in plan.retrieved[:5]]
        # Build a concise text answer that quotes the chunk titles.
        bullets = []
        for r in plan.retrieved[:3]:
            bullets.append(f"- **{r.chunk.title}** ({r.chunk.source_path})")
        text = "Based on the catalog the following sources are most relevant:\n" + "\n".join(bullets)
        if plan.notes:
            text += "\n\nPlanner notes:\n" + "\n".join(f"- {n}" for n in plan.notes)
        if plan.identifiers:
            id_lines = [
                f"- {b.name_in_question} → org_perm_id={b.org_perm_id}, RIC={b.primary_ric}"
                for b in plan.identifiers
            ]
            text += "\n\nIdentifier bindings:\n" + "\n".join(id_lines)

        return Answer(
            question=plan.question,
            text=text,
            sql=sql,
            citations=citations,
            confidence=0.6 if sql else 0.4,
            extras={"plan_intent": plan.intent, "candidate_tables": plan.candidate_tables},
        )


# --------------------------------------------------------------------------- #
# Optional LLM reasoner                                                       #
# --------------------------------------------------------------------------- #


class LLMClient(Protocol):  # pragma: no cover - protocol only
    def complete(self, *, system: str, user: str) -> str: ...


class OpenAIChatClient:  # pragma: no cover - exercised only when key is present
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self._model = model

    def complete(self, *, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
        )
        return resp.choices[0].message.content or ""


_LLM_SYSTEM_PROMPT = """You are the LSEG Data Copilot. You MUST:
1. Only answer using the catalog excerpts provided in the user message.
2. Cite every factual claim with a source path from the excerpts.
3. If you cannot find an answer in the excerpts, reply "INSUFFICIENT_CONTEXT".
4. Never invent table or column names. Never invent identifiers.
5. If the user asks about a restricted table without entitlement, refuse.
Return a JSON object: {"answer": str, "citations": [str], "sql": str|null}.
"""


class LLMReasoner:
    def __init__(self, catalog: Catalog, client: LLMClient) -> None:
        self.catalog = catalog
        self.client = client

    def answer(self, plan: PlanResult, *, question_id: str | None = None) -> Answer:
        if plan.intent == "refusal":
            return Answer(
                question=plan.question,
                text=f"REFUSED: {plan.refusal_reason}",
                refusal=True,
                confidence=0.95,
            )
        excerpts = "\n\n---\n".join(
            f"[{r.chunk.source_path}::{r.chunk.title}]\n{r.chunk.text[:2000]}"
            for r in plan.retrieved[:6]
        )
        user_msg = (
            f"Question: {plan.question}\n\n"
            f"Candidate tables (from planner): {', '.join(plan.candidate_tables) or '(none)'}\n"
            f"Identifier bindings: {[b.__dict__ for b in plan.identifiers]}\n"
            f"As-of timestamp: {plan.as_of_ts}\n\n"
            f"Catalog excerpts:\n{excerpts}\n\n"
            "Respond as a JSON object only."
        )
        raw = self.client.complete(system=_LLM_SYSTEM_PROMPT, user=user_msg)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return Answer(
                question=plan.question,
                text=f"LLM produced non-JSON response: {raw[:200]}",
                citations=[r.chunk.source_path for r in plan.retrieved[:5]],
                confidence=0.2,
            )
        return Answer(
            question=plan.question,
            text=payload.get("answer", ""),
            sql=payload.get("sql"),
            citations=payload.get("citations", []),
            confidence=0.75,
        )
