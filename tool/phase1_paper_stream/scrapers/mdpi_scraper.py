"""
MDPI.py
=======

Keyword-driven scraper for https://www.mdpi.com that builds a research-paper
dataset for Beauty & Personal Care trend forecasting.

How it works
------------
1. Every keyword is run through the site's own search:

       https://www.mdpi.com/search?q=<keyword>

   with sort / paging / year filters appended, and *every* result page is
   walked (`page_no=1..N`) until the "Displaying article X-Y on page P of Q"
   line says there is nothing left.
2. Each hit on a result page is parsed for its bibliographic stub (title, DOI,
   journal, volume/issue, date, authors, cropped abstract, PDF link).
3. Each paper is then opened on its own article page and scraped in full:
   abstract, author keywords, every section of the full-text HTML body,
   figure/table captions, the reference list, affiliations, ORCIDs, licence,
   and the article-view / citation counters.

Two things about MDPI that shape this script:

  * The site sits behind an Akamai bot manager that answers `requests`,
    `httpx` and *headless* Chromium with HTTP 403 - even for robots.txt. A real
    headed browser gets 200. So the fetch layer is Playwright Chromium running
    headed (`--headless` exists but is expected to be blocked). Install the
    browser once with `python -m playwright install chromium`.
  * A result page renders its 50 hits after DOMContentLoaded, so navigation
    waits for `load`; on `domcontentloaded` only the first 15 are in the DOM.

Note on robots.txt: MDPI allows /journal/ and article pages but carries
`Disallow: /search*`. This script uses /search because that is the requested
entry point; the delay defaults are deliberately polite (1.5 s between page
loads, one browser tab, no parallelism). Article pages themselves are allowed.

Output (written to ./data, same schema as the earlier journal-browse harvest):
    mdpi_papers.jsonl     full records, one JSON object per line
    mdpi_papers.csv       flattened table for Excel / Power BI
    mdpi_timeseries.csv   month x keyword counts - the forecasting input
    mdpi_facets.json      run metadata + top-N facets over the harvest
    mdpi_papers.partial.jsonl   temp backup, deleted once the run finishes

The temp backup is what makes a long run safe to interrupt: every search page
appends its stubs to it and every article page appends its finished record, each
write flushed to disk, so a crash or a Ctrl-C costs at most the page in flight.
The next run reads it back and skips the article pages it already has. Disable
with --no-checkpoint; keep the file after a clean run with --keep-partial.

Usage
-----
    python MDPI.py                                   # keywords.txt, 2025-2026
    python MDPI.py --keywords "skin microbiome" "retinol"
    python MDPI.py --keywords-file keywords.txt --max-pages 3
    python MDPI.py --since 2024-01-01 --until 2026-12-31
    python MDPI.py --limit 10                        # smoke test
    python MDPI.py --no-deep                         # search stubs only, no article pages
    python MDPI.py --dry-run                         # hit counts per keyword, scrape nothing
    python MDPI.py --match any                       # loosen keyword matching

Re-running is incremental: DOIs already in data/mdpi_papers.jsonl are kept and
not re-fetched unless --refresh is passed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
except ImportError:                                   # noqa: F401 - reported in main()
    sync_playwright = None


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

BASE_URL = "https://www.mdpi.com"
SEARCH_URL = f"{BASE_URL}/search?q="

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
KEYWORDS_FILE = HERE / "keywords.txt"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# The brief: Beauty and Personal Care, 2025-2026.
DEFAULT_SINCE = "2025-01-01"
DEFAULT_UNTIL = "2026-12-31"

# MDPI's own maximum for the result-page size; anything larger is ignored by
# the site and silently served as 50.
PAGE_COUNT = 100

# Fallback keyword pack, used when keywords.txt is missing.
DEFAULT_KEYWORDS = (
    "skin microbiome",
)

# Search hits whose path does not look like /<eissn>/<vol>/<issue>/<number> are
# books, proceedings landing pages and journal fronts - no article body to scrape.
ARTICLE_PATH_RE = re.compile(r"^/\d{4}-\d{3}[\dxX]/\d+/\d+/\w+/?$")

# "Displaying article 1-50 on page 1 of 13."
PAGING_RE = re.compile(
    r"Displaying\s+articles?\s+([\d,]+)-([\d,]+)\s+on\s+page\s+(\d+)\s+of\s+(\d+)", re.I)

# "Cosmetics 2026, 13(2), 84; https://doi.org/... - 1 Apr 2026"
LISTING_DATE_RE = re.compile(r"-\s*(\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4})\s*$")

# Reference entries end with the site's outbound link chrome.
REF_LINK_LABELS_RE = re.compile(
    r"\[\s*(Google Scholar|CrossRef|PubMed|PubMed/NCBI|Green Version)\s*\]", re.I)

# Headings that hold the paper's own conclusions. MDPI numbers its sections
# ("5. Conclusions"), so the number is optional, and the pattern must match the
# whole heading - a Discussion that merely ends with "in conclusion" is not a
# Conclusions section.
CONCLUSION_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*[.)]?\s*)?"
    r"(?:conclusions?|(?:concluding|final|closing)\s+remarks|"
    r"summary\s+and\s+conclusions?|"
    r"conclusions?\s+and\s+(?:future\s+(?:work|directions?|research|"
    r"perspectives?)|perspectives?|outlook|relevance|recommendations?|"
    r"implications?|limitations?))"
    r"\s*[:.]?$", re.I)

# The stand-in when a paper carries no conclusions of any kind: its Results,
# which is where a paper with no closing section states what it found. MDPI
# authors very often run the two together as "3. Results and Discussion".
RESULTS_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*[.)]?\s*)?"
    r"(?:(?:main|principal|key)\s+)?(?:results?|findings)"
    r"(?:\s+and\s+discussions?)?\s*[:.]?$", re.I)

# Headings that can only follow the conclusions - where a plain-text scan stops.
AFTER_CONCLUSION_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*[.)]?\s*)?"
    r"(?:references?|bibliography|literature\s+cited|acknowledge?ments?|"
    r"funding|author\s+contributions?|conflicts?\s+of\s+interest|"
    r"competing\s+interests?|data\s+availability|supplementary|appendix|"
    r"abbreviations|declarations?|ethics|institutional\s+review)\b", re.I)

# A numbered heading of any name - also a stop for the plain-text scan.
NUMBERED_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+[A-Z][^.]{0,60}$")

# A `##`-style heading line, as extract_content writes them into content_paper.
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")

# Words that carry no matching signal, dropped before keyword scoring.
STOPWORDS = frozenset({
    "a", "an", "and", "the", "of", "for", "in", "on", "with", "to", "by",
    "from", "as", "at", "or", "its",
})

# Body text lives in these; captions and tables are pulled out separately so a
# figure legend does not land in the middle of a paragraph.
BODY_TEXT_SELECTOR = "h2, h3, h4, div.html-p"
CAPTION_SELECTORS = (
    "div.html-fig_description",
    "div.html-table_wrap div.html-caption",
    "div.html-caption",
)

# Which harvested list fields get counted into the facet tables.
FACET_FIELDS = {
    "journals": "journal",
    "article_types": "article_type",
    "years": "publication_year",
}
FACET_LIST_FIELDS = {
    "keywords": "keywords",
    "authors": "authors",
    "matched_keywords": "matched_keywords",
}

# Reference lists and caption blocks blow the 32k-character Excel cell limit,
# so they live in the JSONL only.
CSV_DROP = ("references", "figure_captions")


# --------------------------------------------------------------------------- #
# Record model
# --------------------------------------------------------------------------- #

@dataclass
class Paper:
    """One MDPI article, normalised for downstream trend ingestion."""

    id: str = ""                       # the DOI - MDPI's stable key
    keyword_Search: str = ""           # the keyword whose search first found it
    doi: str = ""
    doi_url: str = ""
    mdpi_url: str = ""
    path: str = ""                     # /2079-9284/13/2/84
    title: str = ""
    abstract: str = ""
    abstract_words: int = 0
    content_paper: str = ""            # full text, headings marked with ##/###
    content_words: int = 0
    conclusions: str = ""              # the Conclusions topic out of content_paper
    sections: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    reference_count: int = 0
    figure_captions: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)   # the authors' own keywords
    journal: str = ""
    journal_slug: str = ""
    eissn: str = ""
    publication_date: str = ""         # YYYY-MM-DD
    publication_year: int | None = None
    publication_month: str = ""        # YYYY-MM, the time-series key
    volume: str = ""
    issue: str = ""
    article_number: str = ""
    article_type: str = ""             # Article, Review, Communication, ...
    language: str = ""
    publisher: str = ""
    authors: list[str] = field(default_factory=list)
    first_author: str = ""
    author_count: int = 0
    orcids: list[str] = field(default_factory=list)
    affiliations: list[str] = field(default_factory=list)
    license_url: str = ""
    is_oa: bool = False
    pdf_url: str = ""
    fulltext_url: str = ""
    xml_url: str = ""
    cited_by_count: int = 0
    views: int = 0
    matched_keywords: list[str] = field(default_factory=list)
    match_score: float = 0.0
    deep_scraped: bool = False
    retrieved_at: str = ""             # when the search listing saw it
    scraped_at: str = ""               # when the article page was scraped
    error: str = ""


# --------------------------------------------------------------------------- #
# Fetch layer
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    print(msg, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Browser:
    """
    Rate-limited page fetcher on top of a single headed Chromium tab.

    Headed, and one tab: MDPI's edge answers headless Chromium with 403, and a
    burst of parallel tabs is what gets an IP challenged. Images, fonts and
    media are dropped at the network layer, which is where nearly all of the
    speed lost to running a real browser comes back.
    """

    BLOCKED_TYPES = frozenset({"image", "media", "font"})

    def __init__(self, headless: bool = False, delay: float = 1.5,
                 timeout: int = 60, retries: int = 3, nav_wait: str = "load",
                 load_images: bool = False) -> None:
        if sync_playwright is None:
            raise SystemExit(
                "Playwright is not installed. Run:\n"
                "    pip install playwright\n"
                "    python -m playwright install chromium"
            )
        self.delay = delay
        self.timeout = timeout * 1000
        self.retries = retries
        self.nav_wait = nav_wait
        self.pages_fetched = 0
        self._next_ok = 0.0

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=headless)
        except Exception as exc:                       # noqa: BLE001
            self._pw.stop()
            raise SystemExit(
                f"Could not start Chromium: {exc}\n"
                "Install it once with: python -m playwright install chromium"
            ) from exc
        self._ctx = self._browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            viewport={"width": 1366, "height": 900},
        )
        if not load_images:
            self._ctx.route("**/*", self._filter)
        self._page = self._ctx.new_page()

    def _filter(self, route: Any, request: Any) -> None:
        if request.resource_type in self.BLOCKED_TYPES:
            route.abort()
        else:
            route.continue_()

    def _throttle(self) -> None:
        wait = self._next_ok - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._next_ok = time.monotonic() + self.delay

    def get(self, url: str) -> str:
        """Navigate and return the settled HTML, or raise after `retries` tries."""
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self._throttle()
            try:
                resp = self._page.goto(url, wait_until=self.nav_wait,
                                       timeout=self.timeout)
                status = resp.status if resp else 0
                if status == 403:
                    raise RuntimeError(
                        "HTTP 403 - MDPI's bot manager refused this request. "
                        "Headless mode and plain HTTP clients are always refused; "
                        "if this happens headed, the IP is being challenged - "
                        "raise --delay and try again later."
                    )
                if status >= 400:
                    raise RuntimeError(f"HTTP {status}")
                self.pages_fetched += 1
                return self._page.content()
            except Exception as exc:                   # noqa: BLE001 - retry everything
                last_exc = exc
                if attempt < self.retries:
                    backoff = 2 ** attempt
                    log(f"  retry {attempt}/{self.retries - 1} in {backoff}s "
                        f":: {url} :: {exc}")
                    time.sleep(backoff)
        raise RuntimeError(f"GET failed after {self.retries} attempts: {url}") from last_exc

    def close(self) -> None:
        for shut in (self._ctx.close, self._browser.close, self._pw.stop):
            try:
                shut()
            except Exception:                          # noqa: BLE001 - teardown is best-effort
                pass


class Checkpoint:
    """
    Append-only temp backup of the harvest, flushed after every page.

    A full run is hundreds of browser navigations at a second and a half each,
    and the real outputs are only written once all of it finishes - so without
    this, an interrupted run loses the lot. Each search page appends its stubs
    and each article page appends its finished record, fsynced as it goes, so a
    crash or a Ctrl-C costs at most the page in flight.

    On replay later lines win, which is exactly the order the writes happen in:
    the stub appended during the search is superseded by the full record
    appended after its article page.
    """

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self.written = 0
        self._fh: Any = None

    def open(self, resume: bool = True) -> dict[str, dict[str, Any]]:
        """Read back an interrupted run, then open the file for appending."""
        if not self.enabled:
            return {}
        prior = load_existing(self.path) if resume else {}
        if prior:
            log(f"[resume] {len(prior)} records recovered from {self.path.name} "
                f"- an earlier run did not finish")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a" if resume else "w", encoding="utf-8",
                                  newline="\n")
        return prior

    def append(self, records: Iterable[dict[str, Any]]) -> None:
        if self._fh is None:
            return
        for rec in records:
            self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.written += 1
        # flush + fsync: a killed process must not take the buffer with it.
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:                          # noqa: BLE001 - teardown is best-effort
                pass
            self._fh = None

    def discard(self) -> None:
        """Drop the backup - only once the real outputs are safely written."""
        self.close()
        if self.path.exists():
            try:
                self.path.unlink()
            except OSError as exc:
                log(f"[write] !! could not remove {self.path.name}: {exc}")


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #

def search_url(keyword: str, page_no: int, since: str, until: str,
               sort: str = "pubdate") -> str:
    """
    Build one result-page URL.

    The base is the requested `https://www.mdpi.com/search?q=<keyword>`; the
    rest are the parameters MDPI's own pager appends to it.
    """
    parts = [
        SEARCH_URL + quote_plus(keyword),
        f"sort={sort}",
        f"page_no={page_no}",
        f"page_count={PAGE_COUNT}",
        f"year_from={since[:4]}",
        f"year_to={until[:4]}",
        "view=default",
    ]
    return "&".join(parts)


def parse_paging(soup: BeautifulSoup) -> tuple[int, int]:
    """(current page, last page) from the 'Displaying article ...' line."""
    m = PAGING_RE.search(soup.get_text(" ", strip=True))
    if not m:
        return (1, 1)
    return (int(m.group(3)), int(m.group(4)))


def result_count(soup: BeautifulSoup) -> int:
    """Upper bound on hits, from the pager - MDPI prints no total of its own."""
    page, last = parse_paging(soup)
    hits = len(soup.select("div.article-content"))
    if last <= 1:
        return hits
    return (last - 1) * PAGE_COUNT + (hits if page == last else 0)


def clean(text: str) -> str:
    return " ".join(unescape(text or "").replace(" ", " ").split())


def parse_results(html: str, keyword: str) -> list[Paper]:
    """Turn one search-result page into bibliographic stubs."""
    soup = BeautifulSoup(html, "lxml")
    out: list[Paper] = []

    for item in soup.select("div.article-content"):
        link = item.select_one("a.title-link")
        if link is None or not link.get("href"):
            continue
        path = link["href"].split("?")[0].rstrip("/")
        if not ARTICLE_PATH_RE.match(path + "/"):
            continue                                  # book, front matter, journal page

        bib = item.select_one("div.color-grey-dark")
        bib_text = clean(bib.get_text(" ", strip=True)) if bib else ""
        doi = ""
        if bib is not None:
            doi_link = bib.select_one("a[href*='doi.org']")
            if doi_link:
                doi = doi_link["href"].split("doi.org/")[-1].strip()

        segments = [s for s in path.split("/") if s]
        paper = Paper(
            id=doi or path,
            keyword_Search=keyword,
            doi=doi,
            doi_url=f"https://doi.org/{doi}" if doi else "",
            mdpi_url=urljoin(BASE_URL, path),
            path=path,
            title=clean(link.get_text(" ", strip=True)),
            eissn=segments[0] if segments else "",
            volume=segments[1] if len(segments) > 1 else "",
            issue=segments[2] if len(segments) > 2 else "",
            article_number=segments[3] if len(segments) > 3 else "",
            matched_keywords=[keyword],
            retrieved_at=now_iso(),
        )

        journal = bib.find("em") if bib is not None else None
        paper.journal = clean(journal.get_text()) if journal else ""

        date_m = LISTING_DATE_RE.search(bib_text)
        if date_m:
            paper.publication_date = parse_display_date(date_m.group(1))

        # The full abstract is in the page already; .abstract-cropped is the
        # same text truncated for display, so prefer the full one.
        abstract = (item.select_one("div.abstract-full")
                    or item.select_one("div.abstract-cropped"))
        if abstract is not None:
            paper.abstract = strip_read_more(abstract.get_text(" ", strip=True))
            paper.abstract_words = len(paper.abstract.split())

        authors = [clean(a.get_text()) for a in item.select("div.authors strong")]
        paper.authors = [a for a in authors if a]
        paper.first_author = paper.authors[0] if paper.authors else ""
        paper.author_count = len(paper.authors)

        atype = item.select_one("span.label.articletype")
        paper.article_type = clean(atype.get_text()) if atype else ""
        paper.is_oa = item.select_one("span.label.openaccess") is not None

        pdf = item.select_one("a.UD_Listings_ArticlePDF[href]")
        if pdf:
            paper.pdf_url = urljoin(BASE_URL, pdf["href"])

        out.append(paper)

    return out


def strip_read_more(text: str) -> str:
    """Drop the listing's '[...] Read more.' / 'Full article' link text."""
    text = clean(text)
    for tail in ("[...] Read more.", "Full article", "Read more."):
        text = text.replace(tail, " ")
    return " ".join(text.split())


def parse_display_date(text: str) -> str:
    """'1 Apr 2026' -> '2026-04-01'."""
    text = clean(text).replace(".", "")
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def search_keyword(browser: Browser, keyword: str, args: argparse.Namespace,
                   checkpoint: Checkpoint) -> list[Paper]:
    """Walk every result page for one keyword and return its stubs."""
    hits: list[Paper] = []
    seen: set[str] = set()
    page_no = 1
    last = 1

    while True:
        url = search_url(keyword, page_no, args.since, args.until, args.sort)
        try:
            html = browser.get(url)
        except Exception as exc:                       # noqa: BLE001
            log(f"[search] !! {keyword} page {page_no}: {exc}")
            break

        soup = BeautifulSoup(html, "lxml")
        _, last = parse_paging(soup)
        page_hits = parse_results(html, keyword)
        new = [h for h in page_hits if h.path not in seen]
        seen.update(h.path for h in new)
        hits.extend(new)
        checkpoint.append(asdict(h) for h in new)      # backup, one page at a time
        log(f"[search] {keyword:<28} page {page_no}/{last}: "
            f"{len(page_hits)} results, {len(new)} new (total {len(hits)})")

        if not page_hits or page_no >= last:
            break
        if args.max_pages and page_no >= args.max_pages:
            log(f"[search] {keyword:<28} stopping at --max-pages {args.max_pages}")
            break
        if args.max_per_keyword and len(hits) >= args.max_per_keyword:
            hits = hits[:args.max_per_keyword]
            log(f"[search] {keyword:<28} capped at {args.max_per_keyword}")
            break
        page_no += 1

    return hits


# --------------------------------------------------------------------------- #
# Article page
# --------------------------------------------------------------------------- #

def meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = (soup.find("meta", attrs={"name": name})
               or soup.find("meta", attrs={"property": name}))
        if tag and tag.get("content"):
            return clean(tag["content"])
    return ""


def meta_all(soup: BeautifulSoup, name: str) -> list[str]:
    out: list[str] = []
    for tag in soup.find_all("meta", attrs={"name": name}):
        val = clean(tag.get("content") or "")
        if val and val not in out:
            out.append(val)
    return out


def normalise_date(value: str) -> str:
    """MDPI writes citation dates as YYYY/MM/DD; a few carry only YYYY/MM."""
    raw = clean(value).replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return dt.strftime("%Y-%m-%d")
    return ""


def extract_content(body: Any) -> tuple[str, list[str]]:
    """
    Full text of the article body, with headings kept as markdown.

    Returns (text, top-level section titles). Headings become ##/###/#### so a
    downstream reader can still see the structure after the HTML is gone.
    """
    if body is None:
        return "", []

    blocks: list[str] = []
    sections: list[str] = []
    seen: set[str] = set()

    for node in body.select(BODY_TEXT_SELECTOR):
        text = clean(node.get_text(" ", strip=True))
        if not text or text in seen:
            continue
        seen.add(text)
        if node.name == "h2":
            sections.append(text)
            blocks.append(f"## {text}")
        elif node.name == "h3":
            blocks.append(f"### {text}")
        elif node.name == "h4":
            blocks.append(f"#### {text}")
        else:
            blocks.append(text)

    return "\n".join(blocks), sections


def heading_blocks(text: str) -> list[tuple[int, int, int, str, str]]:
    """
    Every `##` heading in content_paper as (start, end, depth, title, text).

    A block runs to the next heading of the same level or shallower, so the
    `### Limitations` nested under a Conclusions section stays inside it while
    the `## References` after it does not.
    """
    lines = text.splitlines()
    heads = [(i, len(m.group(1)), clean(m.group(2)))
             for i, line in enumerate(lines)
             if (m := HEADING_RE.match(line))]
    out: list[tuple[int, int, int, str, str]] = []
    for n, (start, depth, title) in enumerate(heads):
        end = next((j for j, d, _t in heads[n + 1:] if d <= depth), len(lines))
        out.append((start, end, depth, title,
                    "\n".join(lines[start + 1:end]).strip()))
    return out


def conclusions_from_plain(text: str, max_lines: int = 400) -> str:
    """
    The Conclusions run of text carrying no headings at all.

    MDPI publishes the HTML full text some days after the PDF, so a freshly
    listed paper can arrive with prose but no markup. The last standalone
    "Conclusions" line wins, and the scan stops at the first heading that can
    only follow it.
    """
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines)
              if len(clean(ln)) <= 60 and CONCLUSION_RE.match(clean(ln))]
    if not starts:
        return ""
    kept: list[str] = []
    for line in lines[starts[-1] + 1:starts[-1] + 1 + max_lines]:
        flat = clean(line)
        if AFTER_CONCLUSION_RE.match(flat) or NUMBERED_HEADING_RE.match(flat):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def conclusions_from_label(text: str) -> str:
    """
    A "Conclusions:" run that is a label rather than a heading.

    The label has to open a line or a sentence, so the "In conclusion, ..." that
    ends half of all discussions cannot trigger it.
    """
    m = re.search(r"(?:^|[\n.]\s*)"
                  r"(?:conclusions?(?:\s+and\s+relevance)?|concluding\s+remarks)"
                  r"\s*[:\-–—]\s*", text, re.I)
    if not m:
        return ""
    tail = text[m.end():].strip()
    # The next label ends it. On its own line it may be capitalised any way; run
    # inline on a single line only an ALL-CAPS one is safe to read as a label
    # rather than as the start of a sentence.
    nxt = re.search(r"\n\s*[A-Z][A-Za-z ]{2,30}\s*[:\-–—]"
                    r"|(?<=[.;])\s+[A-Z][A-Z ]{2,30}\s*:", tail)
    return (tail[:nxt.start()] if nxt else tail).strip()


def extract_conclusions(content_paper: str) -> str:
    """
    Pull the Conclusions topic out of the whole-paper text, or its stand-in.

    Among the body's headings the shallowest wins, and the latest of those,
    which is the paper's real closing section rather than a Conclusion
    subsection of the Discussion.

    A paper with no conclusions anywhere falls back to its `## Results`, on the
    grounds that a paper which never writes a closing section still states what
    it found there. That is a stand-in, not a conclusion: the column then holds
    findings rather than the authors' own reading of them.
    """
    if not content_paper.strip():
        return ""
    blocks = heading_blocks(content_paper)

    def best_block(pattern: re.Pattern[str]) -> str:
        """The section this pattern names - shallowest heading, then the latest."""
        hits = [(s, d, b) for s, _e, d, t, b in blocks if b and pattern.match(t)]
        if not hits:
            return ""
        return min(hits, key=lambda h: (h[1], -h[0]))[2]

    text = (best_block(CONCLUSION_RE)
            or conclusions_from_label(content_paper)
            or conclusions_from_plain(content_paper)
            or best_block(RESULTS_RE))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_captions(soup: BeautifulSoup) -> list[str]:
    out: list[str] = []
    for selector in CAPTION_SELECTORS:
        for node in soup.select(selector):
            text = clean(node.get_text(" ", strip=True))
            if text and text not in out:
                out.append(text)
    return out


def extract_references(soup: BeautifulSoup) -> list[str]:
    out: list[str] = []
    for li in soup.select("#html-references_list li, div.html-references_list li"):
        text = REF_LINK_LABELS_RE.sub("", li.get_text(" ", strip=True))
        text = clean(text.replace("[", " ").replace("]", " "))
        if text:
            out.append(text)
    return out


def extract_int(soup: BeautifulSoup, selector: str) -> int:
    node = soup.select_one(selector)
    if node is None:
        return 0
    digits = re.sub(r"[^\d]", "", node.get_text())
    return int(digits) if digits else 0


def parse_article(paper: Paper, html: str) -> Paper:
    """Fill a search stub in with everything the article page carries."""
    soup = BeautifulSoup(html, "lxml")

    paper.title = meta_content(soup, "citation_title") or paper.title
    paper.doi = meta_content(soup, "citation_doi") or paper.doi
    if paper.doi:
        paper.id = paper.doi
        paper.doi_url = f"https://doi.org/{paper.doi}"
    paper.journal = meta_content(soup, "citation_journal_title") or paper.journal
    paper.eissn = meta_content(soup, "citation_issn") or paper.eissn
    paper.volume = meta_content(soup, "citation_volume") or paper.volume
    paper.issue = meta_content(soup, "citation_issue") or paper.issue
    paper.article_number = (meta_content(soup, "citation_firstpage")
                            or paper.article_number)
    paper.publisher = meta_content(soup, "citation_publisher")
    paper.language = meta_content(soup, "dc.language") or "en"
    paper.pdf_url = meta_content(soup, "citation_pdf_url") or paper.pdf_url
    paper.fulltext_url = meta_content(soup, "citation_fulltext_html_url")
    paper.xml_url = meta_content(soup, "citation_xml_url")

    date = (normalise_date(meta_content(soup, "citation_publication_date"))
            or normalise_date(meta_content(soup, "citation_online_date"))
            or paper.publication_date)
    paper.publication_date = date
    if date:
        paper.publication_year = int(date[:4])
        paper.publication_month = date[:7]

    # /journal/cosmetics -> 'cosmetics', the slug MDPI uses in its own URLs.
    slug = soup.select_one("a[href^='/journal/']")
    if slug:
        paper.journal_slug = slug["href"].rstrip("/").rsplit("/", 1)[-1]

    authors = meta_all(soup, "citation_author")
    if authors:
        paper.authors = authors
        paper.first_author = authors[0]
        paper.author_count = len(authors)

    paper.orcids = [a["href"] for a in soup.select("a[href*='orcid.org']")
                    if a.get("href")]
    paper.affiliations = [
        clean(d.get_text(" ", strip=True))
        for d in soup.select("div.art-affiliations div.affiliation-name")
    ] or [
        clean(d.get_text(" ", strip=True))
        for d in soup.select("div.art-affiliations div.affiliation")
    ]

    licence = soup.select_one("a[href*='creativecommons']")
    if licence:
        paper.license_url = licence["href"]
        paper.is_oa = True

    atype = soup.select_one("span.label.articletype")
    if atype:
        paper.article_type = clean(atype.get_text())
    if not paper.article_type:
        paper.article_type = meta_content(soup, "prism.section")

    abstract = soup.select_one("div.art-abstract, div.html-abstract")
    if abstract is not None:
        text = clean(abstract.get_text(" ", strip=True))
        text = re.sub(r"^Abstract[:\s]*", "", text, flags=re.I)
        if len(text) > len(paper.abstract):
            paper.abstract = text
    if not paper.abstract:
        paper.abstract = meta_content(soup, "description", "dc.description")
    paper.abstract_words = len(paper.abstract.split())

    paper.keywords = [clean(a.get_text()) for a in soup.select("div#html-keywords a")]
    if not paper.keywords:
        paper.keywords = [k for k in meta_all(soup, "dc.subject") if k]

    body = soup.select_one("div.html-body")
    paper.content_paper, paper.sections = extract_content(body)
    paper.content_words = len(paper.content_paper.split())
    paper.conclusions = extract_conclusions(paper.content_paper)
    paper.figure_captions = extract_captions(soup)
    paper.references = extract_references(soup)
    paper.reference_count = len(paper.references)

    paper.views = extract_int(soup, "span.view-number")
    paper.cited_by_count = extract_int(soup, "span.citations-number")

    paper.deep_scraped = bool(paper.content_paper or paper.abstract)
    paper.scraped_at = now_iso()
    return paper


def deep_scrape(browser: Browser, papers: Sequence[Paper],
                checkpoint: Checkpoint) -> None:
    """Open each paper's article page in turn and fill the record in place."""
    total = len(papers)
    for i, paper in enumerate(papers, 1):
        try:
            html = browser.get(paper.mdpi_url)
            parse_article(paper, html)
        except Exception as exc:                       # noqa: BLE001
            paper.error = f"{type(exc).__name__}: {exc}"
            paper.scraped_at = now_iso()
            log(f"[article] !! {paper.mdpi_url}: {exc}")
        checkpoint.append([asdict(paper)])             # backup, one page at a time
        if i % 10 == 0 or i == total:
            log(f"[article] {i}/{total}")


# --------------------------------------------------------------------------- #
# Keyword matching
# --------------------------------------------------------------------------- #

def significant_words(keyword: str) -> list[str]:
    words = re.findall(r"[\w'-]+", keyword.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def score_keyword(paper: Paper, keyword: str) -> float:
    """Fraction of the keyword's significant words present in the paper's text."""
    words = significant_words(keyword)
    if not words:
        return 0.0
    haystack = " ".join([
        paper.title, paper.abstract, " ".join(paper.keywords),
    ]).lower()
    hit = sum(1 for w in words if w in haystack)
    return round(hit / len(words), 3)


def apply_matching(papers: Sequence[Paper], keywords: Sequence[str],
                   mode: str, drop: bool = True) -> list[Paper]:
    """
    Re-score every paper against every keyword, not just the one that found it.

    MDPI's search ranks loosely - a two-word query returns papers carrying only
    one of the words - so the harvest is filtered here rather than trusted as
    returned. `--match all` keeps papers containing every significant word of at
    least one keyword; `--match any` keeps anything scoring above zero; `--match
    none` keeps the raw search output.

    Run once on the search stubs, where title and abstract are enough to decide
    and nothing has been paid for yet, then again after the article pages are in
    with `drop=False` - the authors' own keywords can only raise a score, and a
    paper already fetched is not worth throwing away.
    """
    kept: list[Paper] = []
    for paper in papers:
        scores = {kw: score_keyword(paper, kw) for kw in keywords}
        best = max(scores.values(), default=0.0)
        paper.match_score = best
        if mode == "all":
            matched = [kw for kw, s in scores.items() if s >= 1.0]
        elif mode == "any":
            matched = [kw for kw, s in scores.items() if s > 0]
        else:
            matched = [kw for kw, s in scores.items() if s > 0] or [paper.keyword_Search]
        # Keep the discovering keyword first so keyword_Search stays meaningful.
        ordered = [paper.keyword_Search] if paper.keyword_Search in matched else []
        ordered += [kw for kw in matched if kw != paper.keyword_Search]
        paper.matched_keywords = ordered

        if not drop or mode == "none" or ordered:
            kept.append(paper)
    return kept


# --------------------------------------------------------------------------- #
# Forecasting inputs
# --------------------------------------------------------------------------- #

def build_timeseries(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    month x keyword counts - the table a forecasting model consumes. Every
    record also lands in the pseudo-keyword `__all__`, so the total is a row
    set of its own rather than a sum the reader has to do.
    """
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for rec in records:
        month = rec.get("publication_month") or ""
        if not month:
            continue
        for kw in list(rec.get("matched_keywords") or []) + ["__all__"]:
            row = buckets.setdefault((month, kw), {
                "month": month, "keyword": kw, "papers": 0,
                "citations": 0, "views": 0,
            })
            row["papers"] += 1
            row["citations"] += int(rec.get("cited_by_count") or 0)
            row["views"] += int(rec.get("views") or 0)

    rows: list[dict[str, Any]] = []
    for (_month, _kw), row in sorted(buckets.items()):
        row["citations_per_paper"] = round(row["citations"] / row["papers"], 2)
        rows.append(row)
    return rows


def midpoint(since: str, until: str) -> str:
    """Month that splits the window, for a before/after momentum comparison."""
    try:
        a = datetime.strptime(since[:10], "%Y-%m-%d")
        b = datetime.strptime(until[:10], "%Y-%m-%d")
    except ValueError:
        return "2026-01"
    return (a + (b - a) / 2).strftime("%Y-%m")


def build_facets(records: Sequence[dict[str, Any]], top: int) -> dict[str, Any]:
    """Top-N counts over the harvest itself."""
    out: dict[str, Any] = {}
    for label, fld in FACET_LIST_FIELDS.items():
        counter: Counter[str] = Counter()
        for rec in records:
            for val in rec.get(fld) or []:
                if isinstance(val, str) and val.strip():
                    counter[val.strip()] += 1
        out[label] = [{"value": k, "papers": v} for k, v in counter.most_common(top)]
    for label, fld in FACET_FIELDS.items():
        counter = Counter(str(rec.get(fld) or "").strip() for rec in records)
        counter.pop("", None)
        counter.pop("None", None)
        out[label] = [{"value": k, "papers": v} for k, v in counter.most_common(top)]
    return out


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #

def load_keywords(path: Path) -> list[str]:
    """One keyword per line; blank lines and # comments ignored."""
    if not path.exists():
        log(f"[run] {path.name} not found - using the built-in keyword pack")
        return list(DEFAULT_KEYWORDS)
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and line not in out:
            out.append(line)
    return out


def load_existing(path: Path, key: str = "id") -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get(key):
                out[rec[key]] = rec
    return out


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    log(f"[write] {path}  ({n} records)")
    return n


def write_csv(path: Path, records: Sequence[dict[str, Any]]) -> int:
    if not records:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for rec in records:
        for k in rec:
            if k not in fields:
                fields.append(k)
    # utf-8-sig so Excel on Windows renders accents correctly
    try:
        fh = path.open("w", encoding="utf-8-sig", newline="")
    except PermissionError:
        # Almost always the file being open in Excel. The JSONL is already
        # written by this point, so side-write and warn rather than lose the run.
        alt = path.with_name(f"{path.stem}.locked{path.suffix}")
        log(f"[write] !! {path.name} is locked (open in Excel?) - "
            f"writing {alt.name} instead")
        try:
            fh = alt.open("w", encoding="utf-8-sig", newline="")
        except PermissionError as exc:
            log(f"[write] !! could not write {alt.name} either: {exc}")
            return 0
        path = alt
    with fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore",
                                quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for rec in records:
            writer.writerow({k: rec.get(k, "") for k in fields})
    log(f"[write] {path}  ({len(records)} rows)")
    return len(records)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    log(f"[write] {path}")


def flatten_for_csv(rec: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in rec.items() if k not in CSV_DROP}
    for key, val in list(out.items()):
        if isinstance(val, list):
            out[key] = " | ".join(str(v) for v in val)
        elif isinstance(val, dict):
            out[key] = json.dumps(val, ensure_ascii=False)
    for key in ("content_paper", "abstract", "conclusions"):
        if isinstance(out.get(key), str) and len(out[key]) > 32000:
            out[key] = out[key][:32000] + " ...[truncated]"
    return out


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def summarise(records: Sequence[dict[str, Any]]) -> None:
    ok = [r for r in records if not r.get("error")]
    log("")
    log("=" * 66)
    log(f"  papers             : {len(records)}  "
        f"(ok {len(ok)}, failed {len(records) - len(ok)})")
    if ok:
        years = Counter(r.get("publication_year") for r in ok
                        if r.get("publication_year"))
        log(f"  by year            : {dict(sorted(years.items()))}")
        journals = Counter(r.get("journal") for r in ok if r.get("journal"))
        log(f"  top journals       : {dict(journals.most_common(6))}")
        kws: Counter[str] = Counter()
        for r in ok:
            for k in r.get("matched_keywords") or []:
                kws[k] += 1
        log(f"  top keywords       : {dict(kws.most_common(6))}")
        deep = sum(1 for r in ok if r.get("deep_scraped"))
        log(f"  deep scraped       : {deep}")
        wc = [r.get("content_words", 0) for r in ok]
        log(f"  body words (avg/max): {sum(wc) // max(len(wc), 1)} / {max(wc, default=0)}")
        thin = sum(1 for r in ok if r.get("content_words", 0) < 200)
        log(f"  thin bodies (<200w): {thin}  (abstract only - MDPI publishes the "
            f"HTML full text some days after the PDF)")
        multi = sum(1 for r in ok if len(r.get("matched_keywords") or []) > 1)
        log(f"  multi-keyword      : {multi}")
    log("=" * 66)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scrape MDPI search results and article pages into a "
                    "trend-forecasting dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Needs a headed browser: python -m playwright install chromium",
    )
    p.add_argument("--keywords", nargs="+", metavar="KEYWORD",
                   help="search keywords (default: read keywords.txt)")
    p.add_argument("--keywords-file", default=str(KEYWORDS_FILE),
                   help="file of keywords, one per line (default keywords.txt)")
    p.add_argument("--since", default=DEFAULT_SINCE, metavar="YYYY-MM-DD",
                   help=f"earliest publication date (default {DEFAULT_SINCE})")
    p.add_argument("--until", default=DEFAULT_UNTIL, metavar="YYYY-MM-DD",
                   help=f"latest publication date (default {DEFAULT_UNTIL})")
    p.add_argument("--sort", default="pubdate",
                   choices=["pubdate", "relevance", "citedby", "viewed"],
                   help="MDPI result ordering (default pubdate)")
    p.add_argument("--match", default="all", choices=["all", "any", "none"],
                   help="keep papers containing every significant word of a "
                        "keyword (all), any of them (any), or keep whatever "
                        "search returned (none). Default: all")
    p.add_argument("--max-pages", type=int, default=0,
                   help="result pages per keyword (default 0 = every page)")
    p.add_argument("--max-per-keyword", type=int, default=0,
                   help="cap hits per keyword (default 0 = no cap)")
    p.add_argument("--limit", type=int,
                   help="cap the article pages actually scraped (smoke tests)")
    p.add_argument("--no-deep", action="store_true",
                   help="stop after the search listings; skip the article pages")
    p.add_argument("--delay", type=float, default=1.5,
                   help="min seconds between page loads (default 1.5)")
    p.add_argument("--timeout", type=int, default=60,
                   help="per-navigation timeout in seconds (default 60)")
    p.add_argument("--headless", action="store_true",
                   help="run Chromium headless - MDPI's bot manager answers "
                        "headless with 403, so expect this to fail")
    p.add_argument("--load-images", action="store_true",
                   help="do not block images/fonts/media (slower)")
    p.add_argument("--out", default=str(DATA_DIR),
                   help="output directory (default ./data)")
    p.add_argument("--top", type=int, default=50,
                   help="rows per facet table (default 50)")
    p.add_argument("--refresh", action="store_true",
                   help="re-scrape papers already present in mdpi_papers.jsonl "
                        "(also ignores and truncates the temp backup)")
    p.add_argument("--no-checkpoint", action="store_true",
                   help="do not keep the mdpi_papers.partial.jsonl temp backup - "
                        "an interrupted run then loses everything")
    p.add_argument("--keep-partial", action="store_true",
                   help="keep the temp backup after a successful run instead of "
                        "deleting it")
    p.add_argument("--dry-run", action="store_true",
                   help="report hits per keyword from page 1 and exit")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    keywords = args.keywords or load_keywords(Path(args.keywords_file))
    if not keywords:
        log("[run] no keywords - nothing to search")
        return 1

    out_dir = Path(args.out)
    papers_jsonl = out_dir / "mdpi_papers.jsonl"
    papers_csv = out_dir / "mdpi_papers.csv"

    started = time.time()
    log(f"[run] {len(keywords)} keywords  window {args.since}..{args.until}  "
        f"sort={args.sort}  match={args.match}")

    # The temp backup is opened before the browser so a recovered run is
    # reported before anything is fetched. --dry-run never writes to it.
    checkpoint = Checkpoint(out_dir / "mdpi_papers.partial.jsonl",
                            enabled=not (args.no_checkpoint or args.dry_run))
    recovered = checkpoint.open(resume=not args.refresh)

    browser = Browser(headless=args.headless, delay=args.delay,
                      timeout=args.timeout, load_images=args.load_images)
    try:
        if args.dry_run:
            for kw in keywords:
                try:
                    html = browser.get(search_url(kw, 1, args.since, args.until,
                                                  args.sort))
                except Exception as exc:               # noqa: BLE001
                    log(f"  {kw:<28} !! {exc}")
                    continue
                soup = BeautifulSoup(html, "lxml")
                _, last = parse_paging(soup)
                log(f"  {kw:<28} ~{result_count(soup):>5} hits "
                    f"over {last} page(s)")
            return 0

        # ---- 1. search -----------------------------------------------------
        found: dict[str, Paper] = {}
        for kw in keywords:
            for paper in search_keyword(browser, kw, args, checkpoint):
                prior = found.get(paper.path)
                if prior is None:
                    found[paper.path] = paper
                elif kw not in prior.matched_keywords:
                    prior.matched_keywords.append(kw)
        log(f"[search] {len(found)} unique papers across {len(keywords)} keywords")

        existing = {} if args.refresh else load_existing(papers_jsonl)
        if existing:
            known = {rec.get("path") for rec in existing.values()}
            before = len(found)
            found = {p: v for p, v in found.items() if p not in known}
            log(f"[run] {len(existing)} papers already in {papers_jsonl.name} - "
                f"{before - len(found)} skipped, {len(found)} new")

        # Article pages an interrupted run already paid for: skip re-fetching
        # them, but keep their records so they still reach the output. Stubs in
        # the backup are not carried over - the search above just re-found them.
        resumed = {rec["path"]: rec for rec in recovered.values()
                   if rec.get("path") and (rec.get("deep_scraped") or args.no_deep)}
        if resumed:
            before = len(found)
            found = {p: v for p, v in found.items() if p not in resumed}
            log(f"[resume] {len(resumed)} article pages already scraped - "
                f"{before - len(found)} skipped, {len(found)} left to fetch")

        # Filter before the article pages are fetched: the listing already
        # carries title and abstract, which is what the score is built from.
        stubs = sorted(found.values(),
                       key=lambda p: (p.publication_date, p.path), reverse=True)
        papers = apply_matching(stubs, keywords, args.match)
        if len(papers) != len(stubs):
            log(f"[match] --match {args.match}: {len(stubs)} -> {len(papers)} papers")

        if args.limit:
            papers = papers[:args.limit]
            log(f"[run] limited to {len(papers)} papers")

        # ---- 2. article pages ----------------------------------------------
        if papers and not args.no_deep:
            log(f"[article] scraping {len(papers)} article pages ...")
            deep_scrape(browser, papers, checkpoint)
        elif args.no_deep:
            log("[article] --no-deep: keeping the search listings only")
    finally:
        browser.close()
        checkpoint.close()

    # ---- 3. re-score, merge, write -----------------------------------------
    # The article pages added the authors' own keywords, which can only raise a
    # score - so refresh matched_keywords, but keep everything already fetched.
    kept = apply_matching(papers, keywords, args.match, drop=False)

    merged: dict[str, dict[str, Any]] = dict(existing)
    for rec in resumed.values():                       # recovered from the backup
        merged[rec.get("id") or rec["path"]] = rec
    for paper in kept:
        rec = asdict(paper)
        prior = merged.get(rec["id"])
        if prior:
            rec["matched_keywords"] = list(dict.fromkeys(
                (prior.get("matched_keywords") or []) + rec["matched_keywords"]))
            rec["keyword_Search"] = prior.get("keyword_Search") or rec["keyword_Search"]
            for k, v in prior.items():                 # keep any LLM fields added later
                if k not in rec:
                    rec[k] = v
        merged[rec["id"]] = rec

    records = sorted(merged.values(),
                     key=lambda r: (r.get("publication_date") or "", r.get("id") or ""),
                     reverse=True)
    if not records:
        log("[run] nothing matched - widen the window, the keywords, or --match")
        return 1

    write_jsonl(papers_jsonl, records)
    write_csv(papers_csv, [flatten_for_csv(r) for r in records])

    # Everything in the backup is now in mdpi_papers.jsonl, so it has done its job.
    if args.keep_partial:
        log(f"[write] --keep-partial: {checkpoint.path.name} left in place "
            f"({checkpoint.written} appends this run)")
    else:
        checkpoint.discard()

    timeseries = build_timeseries(records)
    write_csv(out_dir / "mdpi_timeseries.csv", timeseries)

    write_json(out_dir / "mdpi_facets.json", {
        "generated_at": now_iso(),
        "source": {
            "site": BASE_URL,
            "method": "search keywords + scrape every result page + article pages",
            "search_url": SEARCH_URL + "<keyword>",
            "note": "MDPI robots.txt carries Disallow: /search*; article pages "
                    "are allowed. Fetched with a headed browser - the site "
                    "returns 403 to plain HTTP clients and to headless Chromium.",
        },
        "window": {"since": args.since, "until": args.until,
                   "momentum_split": midpoint(args.since, args.until)},
        "settings": {"sort": args.sort, "match": args.match,
                     "max_pages": args.max_pages,
                     "max_per_keyword": args.max_per_keyword,
                     "deep_scraped": not args.no_deep},
        "keywords": keywords,
        "papers": len(records),
        "facets": build_facets(records, args.top),
    })

    summarise(records)
    log(f"[run] {browser.pages_fetched} page loads, "
        f"{checkpoint.written} checkpoint appends, "
        f"finished in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n[run] interrupted - everything scraped so far is in "
            "data/mdpi_papers.partial.jsonl; re-run to carry on from it")
        sys.exit(130)
