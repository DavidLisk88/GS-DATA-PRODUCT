"""Schema linker + identifier resolver + PIT-mode resolver.

The planner converts a user question + retrieved context into a *plan* that
the SQL generator can use. We deliberately keep this rule-based for the
prototype so the system works without an LLM key. An optional LLM hook is
provided via `LLMSqlGenerator` in `reasoner.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .catalog import Catalog, TableSpec
from .retriever import RetrievedChunk

# --------------------------------------------------------------------------- #
# Pre-baked aliases. In production these would come from a curated
# `data_dictionary.yaml` + an entity-resolution service.                      #
# --------------------------------------------------------------------------- #

COMPANY_ALIASES: dict[str, dict] = {
    "apple": {"org_perm_id": 4295905573, "primary_ric": "AAPL.OQ", "ticker": "AAPL"},
    "aapl": {"org_perm_id": 4295905573, "primary_ric": "AAPL.OQ", "ticker": "AAPL"},
    "microsoft": {"org_perm_id": 4295902158, "primary_ric": "MSFT.OQ", "ticker": "MSFT"},
    "msft": {"org_perm_id": 4295902158, "primary_ric": "MSFT.OQ", "ticker": "MSFT"},
    "alphabet": {"org_perm_id": 4295902963, "primary_ric": "GOOG.OQ", "ticker": "GOOG"},
    "google": {"org_perm_id": 4295902963, "primary_ric": "GOOG.OQ", "ticker": "GOOG"},
    "goog": {"org_perm_id": 4295902963, "primary_ric": "GOOG.OQ", "ticker": "GOOG"},
    "meta": {"org_perm_id": 4295903669, "primary_ric": "META.OQ", "ticker": "META",
             "historical_rics": ["FB.OQ"]},
    "facebook": {"org_perm_id": 4295903669, "primary_ric": "META.OQ", "ticker": "META",
                 "historical_rics": ["FB.OQ"]},
    "fb": {"org_perm_id": 4295903669, "primary_ric": "META.OQ", "ticker": "META",
           "historical_rics": ["FB.OQ"]},
    "vodafone": {"org_perm_id": 4295869407, "primary_ric": "VOD.L", "ticker": "VOD"},
    "bmw": {"org_perm_id": 4295868529, "primary_ric": "BMWG.DE", "ticker": "BMW"},
    "toyota": {"org_perm_id": 4295875323, "primary_ric": "7203.T", "ticker": "7203"},
}


# --------------------------------------------------------------------------- #
# Plan dataclasses                                                            #
# --------------------------------------------------------------------------- #


@dataclass
class IdentifierBinding:
    name_in_question: str
    company_key: str
    org_perm_id: int
    primary_ric: str
    historical_rics: list[str] = field(default_factory=list)


@dataclass
class PlanResult:
    question: str
    intent: str  # definitional|sql|refusal
    refusal_reason: str | None = None
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    candidate_tables: list[str] = field(default_factory=list)
    identifiers: list[IdentifierBinding] = field(default_factory=list)
    as_of_ts: str | None = None  # ISO timestamp string, if user asked for PIT
    period_end_date: date | None = None
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Planner                                                                     #
# --------------------------------------------------------------------------- #


_DATE_RE = re.compile(r"\b(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\b")
_AS_OF_RE = re.compile(r"as[ -]of\s+(20\d{2}[/-]\d{1,2}[/-]\d{1,2})", re.IGNORECASE)
_AS_KNOWN_RE = re.compile(
    r"as\s+(?:it\s+was\s+)?known\s+on\s+(20\d{2}[/-]\d{1,2}[/-]\d{1,2})", re.IGNORECASE
)


class Planner:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    # ------------------------------------------------------------------ #
    def plan(
        self,
        question: str,
        retrieved: list[RetrievedChunk],
        *,
        user_entitlements: list[str] | None = None,
    ) -> PlanResult:
        user_entitlements = user_entitlements or []
        plan = PlanResult(question=question, intent="definitional", retrieved=retrieved)

        # 1. Decide intent (very rough): SQL keywords vs. definitional.
        sql_signals = (
            "what was", "list ", "show ", "how many", "average ", "sum ",
            "top ", "rank", "between", "since", "on 20", "close price",
            "volume", "rating", "yield"
        )
        if any(s in question.lower() for s in sql_signals):
            plan.intent = "sql"

        # 2. Candidate tables from the retrieved chunks' symbols.
        candidate_tables: list[str] = []
        for r in retrieved:
            for sym in r.chunk.symbols:
                if "." in sym and sym in {t.fqn for t in self.catalog.tables}:
                    candidate_tables.append(sym)
        # Deduplicate while preserving order.
        seen: set[str] = set()
        plan.candidate_tables = [
            fqn for fqn in candidate_tables if not (fqn in seen or seen.add(fqn))
        ]

        # 3. Identifier resolution.
        plan.identifiers = self._resolve_companies(question)

        # 4. PIT clauses.
        m = _AS_KNOWN_RE.search(question) or _AS_OF_RE.search(question)
        if m:
            plan.as_of_ts = self._normalise_date(m.group(1)) + " 23:59:59"

        # 5. Entitlement refusal — block only when the user's question itself
        #    targets a restricted domain/table. Retrieval can surface nearby
        #    restricted docs accidentally, so candidate-table presence alone is
        #    not enough to refuse.
        for fqn in list(plan.candidate_tables):
            spec = self.catalog.get_table(fqn)
            if not spec:
                continue
            if (spec.restricted or spec.has_restricted_columns) and self._question_targets_table(question, spec) and (
                spec.required_entitlement
                and spec.required_entitlement not in user_entitlements
            ):
                plan.intent = "refusal"
                plan.refusal_reason = (
                    f"Table `{fqn}` requires entitlement "
                    f"`{spec.required_entitlement}` which the user does not hold."
                )
                break

        # 6. Currency-consistency note: if question mentions two ccy codes,
        #    we flag it so the SQL generator (or LLM) inserts an FX join.
        currencies = self._currencies_in_question(question)
        if len(currencies) >= 2:
            plan.notes.append(
                f"Currency mix detected ({', '.join(sorted(currencies))}). "
                "Convert via lseg_fx.fx_rates_eod before any arithmetic."
            )

        return plan

    # ------------------------------------------------------------------ #
    def _resolve_companies(self, question: str) -> list[IdentifierBinding]:
        ql = question.lower()
        out: list[IdentifierBinding] = []
        seen: set[int] = set()
        for alias, payload in COMPANY_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", ql):
                if payload["org_perm_id"] in seen:
                    continue
                seen.add(payload["org_perm_id"])
                out.append(
                    IdentifierBinding(
                        name_in_question=alias,
                        company_key=alias,
                        org_perm_id=payload["org_perm_id"],
                        primary_ric=payload["primary_ric"],
                        historical_rics=payload.get("historical_rics", []),
                    )
                )
        return out

    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalise_date(raw: str) -> str:
        m = re.match(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", raw)
        if not m:
            return raw
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    # ------------------------------------------------------------------ #
    @staticmethod
    def _currencies_in_question(question: str) -> set[str]:
        codes = {"USD", "EUR", "GBP", "JPY", "CHF", "CNY", "MXN", "GBp", "HKD", "AUD", "CAD"}
        tokens = re.findall(r"\b[A-Z]{3}\b", question)
        return {t for t in tokens if t in codes}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _question_targets_table(question: str, spec: TableSpec) -> bool:
        ql = question.lower()
        table_tokens = {
            spec.fqn.lower(),
            spec.table_name.lower(),
            spec.table_name.lower().replace("_", " "),
            spec.domain.lower(),
            spec.domain.lower().replace("_", " "),
        }
        if spec.domain == "world_check":
            table_tokens.update({"world-check", "world check", "ofac", "sanctions", "pep"})
        return any(token and token in ql for token in table_tokens)
