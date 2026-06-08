"""Filter LSEG content: keep query/schema/field-specific material, discard
UI navigation, account management, and generic marketing pages."""
from __future__ import annotations

import re

# Phrases that indicate schema/query/data-specific content we WANT.
_KEEP_SIGNALS: list[str] = [
    "table",
    "column",
    "field",
    "schema",
    "database",
    "query",
    "select",
    "join",
    "where",
    "sql",
    "data type",
    "nullable",
    "index",
    "primary key",
    "foreign key",
    "cross-reference",
    "permid",
    "perm_id",
    "ric",
    "isin",
    "cusip",
    "ticker",
    "sedol",
    "datastream",
    "worldscope",
    "i/b/e/s",
    "ibes",
    "starmine",
    "compustat",
    "tick history",
    "quantitative analytics",
    "content set",
    "update cycle",
    "point-in-time",
    "scd",
    "temporal",
    "snowflake",
    "oracle",
    "dbo.",
    "varchar",
    "datetime",
    "bigint",
    "float",
    "int",
]

# Phrases that indicate navigation/marketing content we want to DISCARD.
_DISCARD_SIGNALS: list[str] = [
    "click here to navigate",
    "how to log in",
    "reset your password",
    "contact support",
    "submit a ticket",
    "cookie policy",
    "privacy notice",
    "terms of use",
    "subscribe to newsletter",
    "follow us on",
    "social media",
    "webinar registration",
    "pricing plans",
    "request a demo",
    "sign up for free",
    "browser compatibility",
    "system requirements for the portal",
]


def is_relevant(text: str, *, threshold: float = 0.15) -> bool:
    """Return True if the text is data/schema-relevant (not UI/navigation).

    Uses a simple signal-ratio heuristic: count keep-signal hits vs
    discard-signal hits. If the keep ratio exceeds *threshold*, the
    content passes.
    """
    lower = text.lower()
    if len(lower) < 50:
        return False

    keep_hits = sum(1 for sig in _KEEP_SIGNALS if sig in lower)
    discard_hits = sum(1 for sig in _DISCARD_SIGNALS if sig in lower)

    if discard_hits > 0 and keep_hits == 0:
        return False
    if keep_hits == 0:
        return False

    total = keep_hits + discard_hits
    return (keep_hits / total) >= threshold


def extract_qa_pair(text: str) -> dict[str, str] | None:
    """Try to extract a question/answer pair from article text."""
    question_match = re.search(
        r"(?:^|\n)\s*(?:Q(?:uestion)?[:.]?\s*|How\s+|What\s+|Where\s+|Which\s+|Can\s+I\s+)(.+?)(?:\n|$)",
        text,
        re.IGNORECASE,
    )
    if not question_match:
        return None

    question = question_match.group(0).strip()
    answer_start = question_match.end()
    answer = text[answer_start:].strip()

    if len(answer) < 20:
        return None

    return {"question": question, "answer": answer[:5000]}


def clean_html_text(raw_html: str) -> str:
    """Strip HTML tags and normalise whitespace. Lightweight — no lxml dep."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", raw_html, flags=re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
