"""LSEG Support Article Scraper.

Fetches Q&A articles from support.lseg.com and community.developers.lseg.com,
filters for schema/query-relevant content, normalises to markdown, and saves
to the knowledge/ directory.

Usage:
    python -m lseg_copilot.scraper.lseg_support_scraper --urls urls.txt --out knowledge/
    python -m lseg_copilot.scraper.lseg_support_scraper --article-ids 649377,650000 --out knowledge/

NOTE: LSEG support articles require authentication. This scraper is designed to
work with pre-downloaded HTML files or with authenticated sessions. For
production use, configure LSEG_SESSION_COOKIE in environment.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .content_filter import clean_html_text, is_relevant
from .normalizer import (
    detect_dataset,
    detect_domain,
    extract_tags,
    to_markdown_doc,
)

LOGGER = logging.getLogger(__name__)

LSEG_SUPPORT_BASE = "https://support.lseg.com/s/article"
LSEG_COMMUNITY_BASE = "https://community.developers.lseg.com"

# Known article URL patterns.
_ARTICLE_ID_RE = re.compile(r"(?:article/|id=)(\d+|[A-Za-z0-9-]+)")


def scrape_from_files(
    html_dir: Path,
    out_dir: Path,
    *,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """Scrape pre-downloaded HTML files from a directory."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for html_path in sorted(html_dir.glob("*.html")):
        raw = html_path.read_text(encoding="utf-8", errors="replace")
        text = clean_html_text(raw)

        if not is_relevant(text):
            if verbose:
                LOGGER.info("Skipped (not relevant): %s", html_path.name)
            continue

        title = _extract_title(raw) or html_path.stem
        dataset = detect_dataset(text)
        domain = detect_domain(dataset)
        tags = extract_tags(text)

        md = to_markdown_doc(
            title=title,
            body=text,
            source_url=f"file://{html_path}",
            dataset=dataset,
            domain=domain,
            tags=tags,
        )

        slug = _slugify(title)[:80]
        md_path = out_dir / f"{slug}.md"
        md_path.write_text(md, encoding="utf-8")
        results.append({
            "file": str(md_path),
            "title": title,
            "dataset": dataset,
            "domain": domain,
            "tags": tags,
            "source": str(html_path),
        })
        if verbose:
            LOGGER.info("Saved: %s -> %s", html_path.name, md_path.name)

    return results


def scrape_urls(
    urls: list[str],
    out_dir: Path,
    *,
    session_cookie: str | None = None,
    delay: float = 1.0,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """Fetch and process a list of LSEG article URLs.

    Requires `requests` library. Uses session_cookie for authentication
    if provided.
    """
    try:
        import requests
    except ImportError:
        LOGGER.error("requests library not installed. Run: pip install requests")
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    session = requests.Session()
    if session_cookie:
        session.cookies.set("sid", session_cookie, domain=".lseg.com")

    for url in urls:
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            LOGGER.warning("Failed to fetch %s: %s", url, exc)
            continue

        raw = resp.text
        text = clean_html_text(raw)

        if not is_relevant(text):
            if verbose:
                LOGGER.info("Skipped (not relevant): %s", url)
            continue

        title = _extract_title(raw) or _url_to_title(url)
        dataset = detect_dataset(text)
        domain = detect_domain(dataset)
        tags = extract_tags(text)

        md = to_markdown_doc(
            title=title,
            body=text,
            source_url=url,
            dataset=dataset,
            domain=domain,
            tags=tags,
        )

        slug = _slugify(title)[:80]
        md_path = out_dir / f"{slug}.md"
        md_path.write_text(md, encoding="utf-8")
        results.append({
            "file": str(md_path),
            "title": title,
            "dataset": dataset,
            "domain": domain,
            "tags": tags,
            "source": url,
        })

        time.sleep(delay)

    return results


def build_article_url(article_id: str) -> str:
    """Construct a support.lseg.com article URL from an article ID."""
    return f"{LSEG_SUPPORT_BASE}/{article_id}"


def _extract_title(html: str) -> str | None:
    """Pull <title> from raw HTML."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if match:
        title = clean_html_text(match.group(1))
        title = re.sub(r"\s*[-|–]\s*LSEG.*$", "", title).strip()
        return title if title else None
    return None


def _url_to_title(url: str) -> str:
    """Derive a readable title from a URL path."""
    path = urlparse(url).path
    slug = path.rstrip("/").split("/")[-1]
    return slug.replace("-", " ").replace("_", " ").title()


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return slug or "untitled"


# ── CLI entry point ────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Scrape LSEG support articles.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--html-dir", help="Directory of pre-downloaded HTML files.")
    group.add_argument("--urls", help="File with one URL per line.")
    group.add_argument("--article-ids", help="Comma-separated article IDs.")
    parser.add_argument("--out", default="knowledge/lseg-support-qa", help="Output dir.")
    parser.add_argument("--cookie", default=None, help="LSEG session cookie for auth.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)

    if args.html_dir:
        results = scrape_from_files(Path(args.html_dir), out_dir, verbose=args.verbose)
    elif args.urls:
        urls = [line.strip() for line in Path(args.urls).read_text().splitlines() if line.strip()]
        results = scrape_urls(urls, out_dir, session_cookie=args.cookie, delay=args.delay, verbose=args.verbose)
    else:
        ids = [i.strip() for i in args.article_ids.split(",")]
        urls = [build_article_url(aid) for aid in ids]
        results = scrape_urls(urls, out_dir, session_cookie=args.cookie, delay=args.delay, verbose=args.verbose)

    print(json.dumps({"scraped": len(results), "articles": results}, indent=2))


if __name__ == "__main__":
    main()
