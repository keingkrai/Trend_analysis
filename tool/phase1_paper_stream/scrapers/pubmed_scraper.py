"""
pubmed.py
=========

Keyword-driven harvester for PMC (PubMed Central) that builds a research-paper
dataset for Beauty & Personal Care trend forecasting, with the same output
schema and CLI shape as MDPI.py in this folder.

It talks to NCBI's E-utilities rather than scraping HTML:

    esearch.fcgi?db=pmc&term=<keyword>   ->  the PMCIDs a keyword matches
    efetch.fcgi?db=pmc&id=<ids>         ->  those articles as JATS full-text XML

That is NCBI's documented interface, and it is far better than scraping the
`/search/?term=` pages this script used to walk:

  * plain `requests` - no browser, no proof-of-work cookie challenge, no 403
  * 1,000 ids per esearch call, and **100 whole articles per efetch call**
    (measured: 100 articles, 19 MB, 7.9 s - about 20x a page-by-page scrape)
  * JATS XML is the publisher's own structured source, so sections, references,
    captions, affiliations and licences are real elements instead of CSS
    selectors guessed from a handful of sample pages.

Content, in falling order of preference (recorded per record in
`content_source`):

  1. `jats`     - the <body> of the efetch XML. About 89% of PMC records.
  2. `epmc`     - Europe PMC's mirror of the same article, for records PMC
                  returns without a body. Europe PMC 404s anything it has not
                  ingested yet, which tracks deposit date rather than
                  publication date, so it rescues long-settled records only.
  3. `pdf`      - the PDF, read with the extractor in extract.py (pdfplumber,
                  falling back to pypdf), for any record that still has no
                  text but does have a reachable PDF link.
  4. `abstract` - metadata and abstract only; PMC holds no redistributable
                  body for this record and no PDF could be read.

A caution about (3), tested rather than assumed: PMC refuses programmatic PDF
downloads. Its `/articles/PMC*/pdf/` route answers a bare `requests` call with
the challenge page, and answers a warmed, cookie-carrying browser context with
403 - via APIRequestContext, via in-page `fetch()`, and via a download event.
Publisher PDFs are hit-and-miss too (MDPI answers 403). So the PDF stage earns
its keep on links that are actually fetchable - arXiv, direct open-access
publisher URLs, and local files - and it is a no-op for most PMC-only records.
It costs nothing when it cannot run: pass --no-pdf to skip it entirely.

Two limits worth knowing before planning a run:

  * NCBI refuses to page past the 10,000th hit of a search: `retstart` cannot
    exceed 9998, and `usehistory`/WebEnv does not lift that (both tested). A
    keyword over the limit is reported and truncated - narrow the term or the
    date window. The whole corpus is a job for the PMC OA bulk packages.
  * PMC covers the open-access and funder-deposited subset of PubMed, so it
    returns fewer papers than PubMed for the same query - but with full text.
    Every record still carries its PMID and PubMed URL.

Rate limits: NCBI allows 3 requests/second anonymously and 10 with a free API
key (https://account.ncbi.nlm.nih.gov -> API Key Management). Pass the key with
--api-key or put it in NCBI_API_KEY; the script paces itself either way. It
also sends `tool` and `email` on every call, as NCBI asks - set --email or
NCBI_EMAIL so they can reach you instead of just blocking you.

Output (written to ./data, same shape as the MDPI harvest):
    pmc_papers.jsonl        full records, one JSON object per line
    pmc_papers.csv          flattened table for Excel / Power BI
    pmc_timeseries.csv      month x keyword counts - the forecasting input
    pmc_facets.json         run metadata + top-N facets over the harvest
    pmc_papers.partial.jsonl    temp backup, deleted once the run finishes

The temp backup makes a long run safe to interrupt: every efetch batch appends
its finished records, flushed to disk, so a crash or a Ctrl-C costs at most the
batch in flight. The next run reads it back and skips what it already has.
Disable with --no-checkpoint; keep it after a clean run with --keep-partial.

Usage
-----
    python pubmed.py                                 # keywords.txt, 2025-2026
    python pubmed.py --keywords "skin microbiome" "retinol"
    python pubmed.py --since 2024-01-01 --until 2026-12-31
    python pubmed.py --limit 10                      # smoke test
    python pubmed.py --dry-run                       # hit counts per keyword
    python pubmed.py --no-pdf                        # skip the PDF stage
    python pubmed.py --pdf-url https://arxiv.org/pdf/2301.00001.pdf
    python pubmed.py --match all                     # tighten keyword matching

A keyword line is sent to NCBI verbatim, so the full Entrez query language
works: `"skin microbiome"[Title/Abstract]`, `cosmetics AND (probiotic OR
postbiotic)`, `Skin/microbiology[MeSH]`. Unlike MDPI.py the default is
`--match none`, because NCBI's own MeSH expansion is the point of searching it
- word matching on top would throw away the synonyms it just found.

Re-running is incremental: PMCIDs already in data/pmc_papers.jsonl are kept and
not re-fetched unless --refresh is passed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:                          # extract.py lives beside us
    sys.path.insert(0, str(HERE))

try:
    import extract as pdf_extract                     # the PDF reader in extract.py
except Exception as _pdf_exc:                          # noqa: BLE001 - reported on use
    pdf_extract = None
    PDF_IMPORT_ERROR = str(_pdf_exc)
else:
    PDF_IMPORT_ERROR = ""


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PMC_BASE = "https://pmc.ncbi.nlm.nih.gov"
PUBMED_BASE = "https://pubmed.ncbi.nlm.nih.gov"
EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"

TOOL_NAME = "sji-trend-research"

DATA_DIR = HERE / "data"
KEYWORDS_FILE = HERE / "keywords.txt"

USER_AGENT = f"{TOOL_NAME}/2.0 (+https://pmc.ncbi.nlm.nih.gov; python-requests)"

# The brief: Beauty and Personal Care, 2025-2026.
DEFAULT_SINCE = "2025-01-01"
DEFAULT_UNTIL = "2026-12-31"

# esearch will not serve a retstart above 9998, with or without WebEnv, so no
# search yields more than this many records however it is paged.
RESULT_CEILING = 9_999

# Ids per call. esearch tops out at 10,000 but 1,000 keeps responses small;
# efetch at 100 articles is ~20 MB, which is already a big response.
SEARCH_CHUNK = 1_000
FETCH_BATCH = 100

# NCBI's published ceilings: 3 requests/second anonymously, 10 with an API key.
RATE_ANON = 3.0
RATE_KEYED = 10.0

# The date-window clause folded into every term. Entrez field tags, not ours.
DATE_FIELDS = {
    "publication": "pdat",
    "entrez": "edat",
    "create": "crdt",
}

# Fallback keyword pack, used when keywords.txt is missing.
DEFAULT_KEYWORDS = (
    "skin microbiome",
)

MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}

# JATS wrappers whose text is a caption or a float, never body prose.
FLOAT_TAGS = frozenset({
    "fig", "fig-group", "table-wrap", "table-wrap-group", "supplementary-material",
    "boxed-text", "media", "graphic", "inline-formula", "disp-formula",
})

# Body children worth keeping as prose, in the order JATS declares them.
PROSE_TAGS = frozenset({"p", "list", "disp-quote", "statement", "verse-group"})

# Back-matter sections worth a column of their own, matched on their title.
STATEMENT_SECTIONS = {
    "conflict_of_interest": re.compile(
        r"conflicts?\s+of\s+interest|competing\s+interest|^disclosures?$", re.I),
    "funding": re.compile(r"^funding|funding\s+statement|financial\s+support", re.I),
    "data_availability": re.compile(r"data\s+(availability|sharing)", re.I),
}

# Headings that hold the paper's own conclusions. Publishers name it several
# ways and most number it ("5. Conclusions"), so the number is optional and the
# pattern must match the whole heading - a Discussion that merely ends with "in
# conclusion" is not a Conclusions section.
CONCLUSION_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*[.)]?\s*)?"
    r"(?:conclusions?|(?:concluding|final|closing)\s+remarks|"
    r"summary\s+and\s+conclusions?|"
    r"conclusions?\s+and\s+(?:future\s+(?:work|directions?|research|"
    r"perspectives?)|perspectives?|outlook|relevance|recommendations?|"
    r"implications?|limitations?))"
    r"\s*[:.]?$", re.I)

# The stand-in when a paper carries no conclusions of any kind: its Results,
# which is where a paper with no closing section states what it found. Many
# journals run the two together as one "Results and Discussion" heading.
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

# A `##`-style heading line, as set_content writes them into content_paper.
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")

# Words that carry no matching signal, dropped before keyword scoring.
STOPWORDS = frozenset({
    "a", "an", "and", "the", "of", "for", "in", "on", "with", "to", "by",
    "from", "as", "at", "or", "its", "not",
})

# Entrez query operators and field tags: a keyword line may be a real query,
# and none of it should reach the word-level scorer.
QUERY_SYNTAX_RE = re.compile(r"\[[^\]]+\]|[()\"]|\b(AND|OR|NOT)\b")

# Facets: list-valued fields first, then single-valued ones.
FACET_LIST_FIELDS = {
    "author_keywords": "keywords",
    "sections": "sections",
    "authors": "authors",
}
FACET_FIELDS = {
    "journals": "journal",
    "years": "publication_year",
    "months": "publication_month",
    "countries": "country",
    "content_source": "content_source",
    "publication_state": "publication_state",
}

# Long or repeated fields that would make the CSV unusable.
CSV_DROP = frozenset({"references", "figure_captions", "table_captions",
                      "affiliations"})


@dataclass
class Paper:
    """One PMC article, normalised for downstream trend ingestion."""

    id: str = ""                       # the PMCID - PMC's stable key
    keyword_Search: str = ""           # the keyword whose search first found it
    pmcid: str = ""                    # PMC12276923
    pmc_url: str = ""
    pmid: str = ""
    pubmed_url: str = ""
    doi: str = ""
    doi_url: str = ""
    title: str = ""
    abstract: str = ""
    abstract_words: int = 0
    content_paper: str = ""            # full text, headings marked with ##/###
    content_words: int = 0
    content_source: str = ""           # jats | epmc | pdf | abstract
    conclusions: str = ""              # the Conclusions topic out of content_paper
    sections: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    reference_count: int = 0
    figure_captions: list[str] = field(default_factory=list)
    figure_count: int = 0
    table_captions: list[str] = field(default_factory=list)
    table_count: int = 0
    keywords: list[str] = field(default_factory=list)   # the authors' own keywords
    journal: str = ""                  # NLM abbreviation, e.g. "J Invest Dermatol"
    journal_full: str = ""
    issn: str = ""
    publication_state: str = ""        # published article / author manuscript
    publication_date: str = ""         # YYYY-MM-DD
    publication_year: int | None = None
    publication_month: str = ""        # YYYY-MM, the time-series key
    volume: str = ""
    issue: str = ""
    pages: str = ""
    authors: list[str] = field(default_factory=list)
    first_author: str = ""
    last_author: str = ""
    author_count: int = 0
    affiliations: list[str] = field(default_factory=list)
    affiliation_count: int = 0
    country: str = ""                  # from the first affiliation's last segment
    funding: str = ""
    conflict_of_interest: str = ""
    data_availability: str = ""
    license_url: str = ""
    is_oa: bool = False
    pdf_url: str = ""
    pdf_pages: int = 0
    has_full_text: bool = False
    matched_keywords: list[str] = field(default_factory=list)
    match_score: float = 0.0
    deep_scraped: bool = False         # kept for schema parity with MDPI.py
    retrieved_at: str = ""             # when esearch first returned the id
    scraped_at: str = ""               # when the record was built
    error: str = ""


# --------------------------------------------------------------------------- #
# Fetch layer
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    print(msg, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def short(exc: Exception) -> str:
    return str(exc).splitlines()[0][:160] if str(exc) else type(exc).__name__


class Entrez:
    """
    Rate-limited E-utilities client.

    NCBI allows 3 requests a second anonymously and 10 with a free API key, and
    asks every caller to identify itself with `tool` and `email`. Both are sent
    on every call, and the pacing is enforced here rather than trusted to the
    caller - a burst is what gets an IP blocked.
    """

    def __init__(self, api_key: str = "", email: str = "", timeout: int = 120,
                 retries: int = 4, rate: float = 0.0) -> None:
        self.api_key = api_key
        self.email = email
        self.timeout = timeout
        self.retries = retries
        self.calls = 0
        rate = rate or (RATE_KEYED if api_key else RATE_ANON)
        self._interval = 1.0 / rate
        self._next_ok = 0.0

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _params(self, extra: dict[str, Any]) -> dict[str, Any]:
        params = {"tool": TOOL_NAME}
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key
        params.update(extra)
        return params

    def _throttle(self) -> None:
        wait = self._next_ok - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._next_ok = time.monotonic() + self._interval

    def _call(self, endpoint: str, params: dict[str, Any],
              post: bool = False) -> requests.Response:
        url = f"{EUTILS}/{endpoint}"
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self._throttle()
            try:
                payload = self._params(params)
                resp = (self.session.post(url, data=payload, timeout=self.timeout)
                        if post else
                        self.session.get(url, params=payload, timeout=self.timeout))
                if resp.status_code == 429:
                    raise RuntimeError("HTTP 429 - rate limited by NCBI")
                resp.raise_for_status()
                self.calls += 1
                return resp
            except Exception as exc:                   # noqa: BLE001 - retry everything
                last_exc = exc
                if attempt < self.retries:
                    backoff = 2 ** attempt
                    log(f"  retry {attempt}/{self.retries - 1} in {backoff}s "
                        f":: {endpoint} :: {short(exc)}")
                    time.sleep(backoff)
        raise RuntimeError(f"{endpoint} failed after {self.retries} attempts") from last_exc

    def esearch(self, term: str, retstart: int = 0, retmax: int = SEARCH_CHUNK,
                sort: str = "pub_date") -> tuple[int, list[str]]:
        """Return (total hits, this page of PMCIDs as bare numbers)."""
        params: dict[str, Any] = {
            "db": "pmc", "term": term, "retmode": "json",
            "retstart": retstart, "retmax": retmax,
        }
        if sort and sort != "relevance":
            params["sort"] = sort
        resp = self._call("esearch.fcgi", params)
        try:
            result = resp.json().get("esearchresult", {})
        except ValueError:
            # NCBI reports a refused retstart as JSON with a raw newline in it.
            snippet = re.sub(r"\s+", " ", resp.text)[:200]
            raise RuntimeError(f"esearch returned malformed JSON: {snippet}") from None
        if result.get("ERROR"):
            raise RuntimeError(f"esearch: {result['ERROR']}")
        return int(result.get("count", 0)), list(result.get("idlist", []))

    def efetch(self, ids: Sequence[str]) -> str:
        """Fetch a batch of articles as JATS XML. POST - the id list is long."""
        resp = self._call("efetch.fcgi",
                          {"db": "pmc", "id": ",".join(ids), "retmode": "xml"},
                          post=True)
        return resp.text


class Checkpoint:
    """
    Append-only temp backup of the harvest, flushed after every batch.

    The real outputs are only written once the whole run finishes, so without
    this an interrupted run loses everything. Each efetch batch appends its
    finished records, fsynced as it goes, so a crash or a Ctrl-C costs at most
    the batch in flight. On replay later lines win.
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

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def build_term(keyword: str, since: str, until: str, date_field: str) -> str:
    """
    The `term=` value: the keyword as typed, with the date window ANDed on.

    The keyword reaches NCBI verbatim, so a line in keywords.txt can be a plain
    phrase or a full Entrez query - `"skin microbiome"[Title/Abstract]`,
    `cosmetic AND (probiotic OR postbiotic)`.
    """
    if not (since or until):
        return keyword
    tag = DATE_FIELDS[date_field]
    lo = (since or "1800/01/01").replace("-", "/")
    hi = (until or "3000/12/31").replace("-", "/")
    return f'({keyword}) AND ("{lo}"[{tag}] : "{hi}"[{tag}])'


def search_keyword(api: Entrez, keyword: str,
                   args: argparse.Namespace) -> tuple[int, list[str]]:
    """Page esearch until the keyword is exhausted or a limit is reached."""
    term = build_term(keyword, args.since, args.until, args.date_field)
    total, ids = api.esearch(term, 0, min(SEARCH_CHUNK, args.per_keyword or
                                          SEARCH_CHUNK), args.sort)
    reachable = min(total, RESULT_CEILING)
    if args.per_keyword:
        reachable = min(reachable, args.per_keyword)
    log(f"[search] {keyword!r}: {total} hits"
        + (f", taking {reachable}" if reachable != total else ""))
    if total > RESULT_CEILING:
        log(f"  !! NCBI serves only the first {RESULT_CEILING} hits of a search "
            f"(retstart caps at 9998, WebEnv does not lift it) - narrow the term "
            f"or the date window to reach the rest")

    while len(ids) < reachable:
        retmax = min(SEARCH_CHUNK, reachable - len(ids))
        _, page = api.esearch(term, len(ids), retmax, args.sort)
        if not page:
            break
        before = len(ids)
        ids.extend(page)
        if len(ids) == before:
            break
    return total, ids[:reachable]


# --------------------------------------------------------------------------- #
# JATS parsing
# --------------------------------------------------------------------------- #

def xml_text(node: Any) -> str:
    return clean(node.get_text(" ", strip=True)) if node is not None else ""


def first_text(parent: Any, *names: str) -> str:
    for name in names:
        el = parent.find(name) if parent is not None else None
        if el is not None:
            return xml_text(el)
    return ""


def article_ids(art: Any) -> dict[str, str]:
    return {str(i.get("pub-id-type") or ""): xml_text(i)
            for i in art.find_all("article-id")}


def jats_authors(meta: Any) -> list[str]:
    """Author display names, in the order the article lists them."""
    out: list[str] = []
    for contrib in meta.find_all("contrib"):
        if (contrib.get("contrib-type") or "author") != "author":
            continue
        name = contrib.find("name")
        if name is not None:
            given = first_text(name, "given-names")
            surname = first_text(name, "surname")
            full = clean(f"{given} {surname}")
        else:
            full = first_text(contrib, "string-name", "collab")
        if full:
            out.append(full)
    return list(dict.fromkeys(out))


def jats_date(meta: Any) -> tuple[str, int | None, str]:
    """
    (YYYY-MM-DD, year, YYYY-MM) from the most specific publication date.

    JATS carries several: electronic publication, print publication and the
    issue collection. Electronic is the one a trend series should key on - it
    is when the paper actually appeared.
    """
    by_type: dict[str, Any] = {}
    for pd in meta.find_all("pub-date"):
        key = str(pd.get("pub-type") or pd.get("date-type") or "unknown")
        by_type.setdefault(key, pd)
    for key in ("epub", "pub", "ppub", "epreprint", "collection", "unknown"):
        pd = by_type.get(key)
        if pd is None:
            continue
        year = first_text(pd, "year")
        if not year.isdigit():
            continue
        raw_month = first_text(pd, "month")
        month = (int(raw_month) if raw_month.isdigit()
                 else MONTHS.get(raw_month[:3].lower(), 0))
        raw_day = first_text(pd, "day")
        day = int(raw_day) if raw_day.isdigit() else 0
        if month:
            date = f"{year}-{month:02d}-{day:02d}" if day else f"{year}-{month:02d}-01"
            return date, int(year), f"{year}-{month:02d}"
        return f"{year}-01-01", int(year), f"{year}-01"
    return "", None, ""


def section_markdown(sec: Any, depth: int = 2) -> str:
    """
    One JATS <sec> as text, with its heading level kept.

    Only known prose children are taken, so figures, tables, formulas and
    supplementary blocks never land in the middle of a paragraph - their
    captions are collected separately.
    """
    parts: list[str] = []
    title = sec.find("title", recursive=False)
    if title is not None:
        heading = xml_text(title)
        if heading:
            parts.append("#" * min(depth, 6) + " " + heading)
    for child in sec.find_all(recursive=False):
        if child.name == "sec":
            nested = section_markdown(child, depth + 1)
            if nested:
                parts.append(nested)
        elif child.name in PROSE_TAGS:
            text = xml_text(child)
            if text:
                parts.append(text)
        # everything else (fig, table-wrap, supplementary-material, ...) is a
        # float and is handled by the caption collectors
    return "\n\n".join(parts)


def jats_body(art: Any) -> tuple[str, list[str]]:
    """The article body as text, plus its top-level section names."""
    body = art.find("body")
    if body is None:
        return "", []
    chunks: list[str] = []
    names: list[str] = []
    for sec in body.find_all("sec", recursive=False):
        title = sec.find("title", recursive=False)
        if title is not None and xml_text(title):
            names.append(xml_text(title))
        text = section_markdown(sec)
        if text:
            chunks.append(text)
    if not chunks:
        # a few articles put their prose straight into <body> with no <sec>
        loose = "\n\n".join(xml_text(p) for p in body.find_all("p", recursive=False))
        if loose.strip():
            chunks.append(loose)
    return "\n\n".join(chunks), names


def jats_abstract(meta: Any) -> str:
    """The abstract, structured parts kept as `### ` headings."""
    chosen = None
    for ab in meta.find_all("abstract"):
        kind = str(ab.get("abstract-type") or "")
        if kind in ("graphical", "teaser", "précis", "precis"):
            continue
        chosen = ab
        break
    if chosen is None:
        return ""
    secs = chosen.find_all("sec", recursive=False)
    if secs:
        return "\n\n".join(section_markdown(s, depth=3) for s in secs).strip()
    return "\n\n".join(xml_text(p) for p in chosen.find_all("p") if xml_text(p))


def jats_captions(art: Any, tag: str) -> list[str]:
    """"Figure 1." + its caption, one line per float."""
    out: list[str] = []
    for node in art.find_all(tag):
        label = first_text(node, "label")
        caption = xml_text(node.find("caption"))
        line = clean(f"{label} {caption}")
        if line:
            out.append(line)
    return list(dict.fromkeys(out))


def tidy_citation(text: str) -> str:
    """
    JATS puts every part of a citation in its own element, so joining them on
    spaces leaves "Rocha MA , Bagatin E ." - pull the punctuation back in.
    """
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    return re.sub(r"\s+\)", ")", text).strip()


def jats_references(art: Any) -> list[str]:
    out: list[str] = []
    for ref in art.find_all("ref"):
        text = xml_text(ref.find("mixed-citation") or ref.find("element-citation")
                        or ref)
        text = tidy_citation(re.sub(r"^\d+\.\s*", "", text))
        if text:
            out.append(text)
    return list(dict.fromkeys(out))


def jats_statements(art: Any) -> dict[str, str]:
    """
    Funding / conflict-of-interest / data-availability statements.

    Publishers disagree about where these live: some put them in <back>, others
    as ordinary trailing sections of <body> (MDPI and Wiley both do), so both
    are searched.
    """
    out: dict[str, str] = {}
    containers = [c for c in (art.find("back"), art.find("body")) if c is not None]
    for container in containers:
        for sec in container.find_all(["sec", "fn", "ack", "notes"]):
            title = first_text(sec, "title", "label")
            text = xml_text(sec)
            if not text:
                continue
            for name, pattern in STATEMENT_SECTIONS.items():
                if name in out:
                    continue
                if pattern.search(title) or (not title and pattern.search(text[:60])):
                    # Drop the heading only when it really is the prefix -
                    # slicing blind on its length can cut a word in half.
                    body = (text[len(title):] if title and text.startswith(title)
                            else text)
                    out[name] = clean(body) or text
    return out


def country_of(affiliations: Sequence[str]) -> str:
    """Last comma-separated segment of the first affiliation, minus any postcode."""
    if not affiliations:
        return ""
    tail = affiliations[0].rstrip(".").split(",")[-1]
    return clean(re.sub(r"[\d.]+", " ", tail))


def pdf_href(art: Any, pmcid: str) -> str:
    """The PDF this article says it has, as an absolute URL."""
    for uri in art.find_all("self-uri"):
        href = str(uri.get("xlink:href") or uri.get("href") or "")
        if href.lower().endswith(".pdf"):
            if href.startswith("http"):
                return href
            return f"{PMC_BASE}/articles/{pmcid}/pdf/{href}"
    return ""


def parse_jats(art: Any, keyword: str = "") -> Paper:
    """Build one record from a single <article> element of an efetch response."""
    front = art.find("front") or art
    meta = front.find("article-meta") or front
    journal = front.find("journal-meta")

    ids = article_ids(art)
    pmcid = ids.get("pmcid") or ids.get("pmc") or ""
    if pmcid and not pmcid.upper().startswith("PMC"):
        pmcid = f"PMC{pmcid}"

    paper = Paper(
        id=pmcid,
        pmcid=pmcid,
        keyword_Search=keyword,
        pmc_url=f"{PMC_BASE}/articles/{pmcid}/" if pmcid else "",
        pmid=ids.get("pmid", ""),
        doi=ids.get("doi", ""),
        matched_keywords=[keyword] if keyword else [],
        retrieved_at=now_iso(),
    )
    paper.pubmed_url = f"{PUBMED_BASE}/{paper.pmid}/" if paper.pmid else ""
    paper.doi_url = f"https://doi.org/{paper.doi}" if paper.doi else ""

    title_group = meta.find("title-group")
    paper.title = first_text(title_group or meta, "article-title")

    if journal is not None:
        paper.journal_full = first_text(journal, "journal-title")
        abbrev = next((xml_text(j) for j in journal.find_all("journal-id")
                       if j.get("journal-id-type") == "nlm-ta"), "")
        paper.journal = abbrev or paper.journal_full
        paper.issn = first_text(journal, "issn")

    paper.volume = first_text(meta, "volume")
    paper.issue = first_text(meta, "issue")
    fpage, lpage = first_text(meta, "fpage"), first_text(meta, "lpage")
    paper.pages = f"{fpage}-{lpage}" if fpage and lpage else (fpage or
                                                              first_text(meta, "elocation-id"))
    paper.publication_date, paper.publication_year, paper.publication_month = \
        jats_date(meta)
    paper.publication_state = ("author manuscript"
                               if art.find("author-comment") is not None
                               or ids.get("manuscript") else "published article")

    paper.authors = jats_authors(meta)
    paper.first_author = paper.authors[0] if paper.authors else ""
    paper.last_author = paper.authors[-1] if paper.authors else ""
    paper.author_count = len(paper.authors)
    paper.affiliations = [re.sub(r"^\s*\d+\s*", "", xml_text(a))
                          for a in meta.find_all("aff")]
    paper.affiliations = [a for a in dict.fromkeys(paper.affiliations) if a]
    paper.affiliation_count = len(paper.affiliations)
    paper.country = country_of(paper.affiliations)

    paper.abstract = jats_abstract(meta)
    paper.abstract_words = len(paper.abstract.split())
    paper.keywords = [xml_text(k) for k in meta.find_all("kwd") if xml_text(k)]

    body_text, paper.sections = jats_body(art)
    paper.references = jats_references(art)
    paper.reference_count = len(paper.references)
    paper.figure_captions = jats_captions(art, "fig")
    paper.figure_count = len(art.find_all("fig"))
    paper.table_captions = jats_captions(art, "table-wrap")
    paper.table_count = len(art.find_all("table-wrap"))

    for name, value in jats_statements(art).items():
        setattr(paper, name, value)

    licence = meta.find("license")
    if licence is not None:
        href = str(licence.get("xlink:href") or "")
        if not href:
            link = next((a for a in licence.find_all("ext-link")
                         if "creativecommons.org" in str(a.get("xlink:href") or "")),
                        None)
            href = str(link.get("xlink:href")) if link is not None else ""
        paper.license_url = href
    paper.is_oa = bool(paper.license_url)
    paper.pdf_url = pdf_href(art, pmcid)

    set_content(paper, body_text, "jats")
    paper.deep_scraped = True
    paper.scraped_at = now_iso()
    return paper


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
    The Conclusions run of text carrying no headings at all - i.e. from a PDF.

    The last standalone "Conclusions" line wins: a structured abstract printed
    on page one carries the word too, and the section wanted is the late one.
    The scan stops at the first heading that can only follow it.
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
    A structured abstract's "Conclusions:" run, which is a label, not a heading.

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
    # inline on a single line - PubMed's own style - only an ALL-CAPS one is
    # safe to read as a label rather than as the start of a sentence.
    nxt = re.search(r"\n\s*[A-Z][A-Za-z ]{2,30}\s*[:\-–—]"
                    r"|(?<=[.;])\s+[A-Z][A-Z ]{2,30}\s*:", tail)
    return (tail[:nxt.start()] if nxt else tail).strip()


def extract_conclusions(content_paper: str) -> str:
    """
    Pull the Conclusions topic out of the whole-paper text, or its stand-in.

    content_paper opens with the title, the abstract and the keyword list before
    the body starts, and a structured abstract has a `### Conclusions` part of
    its own - so a heading inside the `## Abstract` block is used only when the
    body offers nothing. Among body headings the shallowest wins, and the latest
    of those, which is the paper's real closing section rather than a Conclusion
    subsection of the Discussion.

    A paper with no conclusions anywhere falls back to its `## Results`, on the
    grounds that a paper which never writes a closing section still states what
    it found there. That is a stand-in, not a conclusion: the column then holds
    findings rather than the authors' own reading of them.
    """
    if not content_paper.strip():
        return ""
    blocks = heading_blocks(content_paper)
    abstract = next(((s, e, b) for s, e, d, t, b in blocks
                     if d <= 2 and t.lower().startswith("abstract")), None)

    def inside_abstract(start: int) -> bool:
        return abstract is not None and abstract[0] <= start < abstract[1]

    def best_block(pattern: re.Pattern[str]) -> str:
        """The section this pattern names - preferring the body's over the abstract's."""
        hits = [(s, d, b) for s, _e, d, t, b in blocks if b and pattern.match(t)]
        for group in ([h for h in hits if not inside_abstract(h[0])],
                      [h for h in hits if inside_abstract(h[0])]):
            if group:
                return min(group, key=lambda h: (h[1], -h[0]))[2]
        return ""

    text = best_block(CONCLUSION_RE)
    if not text:
        # No heading said "Conclusions": try the abstract's inline label, then a
        # plain-text scan for content that came from a PDF with no headings.
        text = (conclusions_from_label(abstract[2]) if abstract else "") \
            or conclusions_from_plain(content_paper) \
            or best_block(RESULTS_RE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def set_content(paper: Paper, body_text: str, source: str) -> None:
    """Assemble content_paper from whatever body text we managed to get."""
    paper.has_full_text = bool(body_text.strip())
    paper.content_source = source if paper.has_full_text else "abstract"

    parts = [f"# {paper.title}"] if paper.title else []
    if paper.abstract:
        parts.append("## Abstract\n" + paper.abstract)
    if paper.keywords:
        parts.append("## Keywords\n" + "; ".join(paper.keywords))
    if body_text.strip():
        parts.append(body_text.strip())
    paper.content_paper = "\n\n".join(parts)
    paper.content_words = len(paper.content_paper.split())
    paper.conclusions = extract_conclusions(paper.content_paper)


def parse_batch(xml: str, keyword: str = "") -> list[Paper]:
    soup = BeautifulSoup(xml, "lxml-xml")
    return [parse_jats(art, keyword) for art in soup.find_all("article")]


# --------------------------------------------------------------------------- #
# Fallbacks: Europe PMC, then the PDF reader in extract.py
# --------------------------------------------------------------------------- #

def europepmc_body(session: requests.Session, pmcid: str,
                   timeout: int = 60) -> tuple[str, list[str]]:
    """
    Europe PMC's copy of the same JATS, for records PMC returns without a body.

    Europe PMC mirrors on its own schedule and 404s anything it has not ingested
    yet - which tracks how recently the article was *deposited*, not when it was
    published: a 2018 paper deposited last month (a high PMCID) 404s just like a
    2026 one. So this rescues long-settled records and quietly finds nothing for
    fresh deposits. It costs one request and is skipped with --no-epmc.
    """
    try:
        resp = session.get(f"{EPMC_BASE}/{pmcid}/fullTextXML", timeout=timeout)
    except Exception:                                  # noqa: BLE001 - a fallback may fail
        return "", []
    if resp.status_code != 200 or not resp.content.startswith(b"<"):
        return "", []
    art = BeautifulSoup(resp.text, "lxml-xml").find("article")
    return jats_body(art) if art is not None else ("", [])


def download_pdf(session: requests.Session, url: str, dest: Path,
                 timeout: int = 90) -> Path | None:
    """
    Fetch a PDF, refusing anything that is not one.

    NCBI answers its own `/articles/PMC*/pdf/` route with an HTML challenge
    page rather than the file, and some publishers answer 403, so the magic
    bytes are checked before the file is handed to a parser.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/131.0.0.0 Safari/537.36"),
            "Accept": "application/pdf,*/*",
        })
    except Exception:                                  # noqa: BLE001 - a fallback may fail
        return None
    if resp.status_code != 200 or not resp.content.startswith(b"%PDF-"):
        return None
    dest.write_bytes(resp.content)
    return dest


def spacing_ratio(text: str) -> float:
    """
    Spaces per character - a cheap test for PDF text that lost its word breaks.

    Running English sits near 0.15; a PDF whose font declares no space glyph
    comes back as one long run of letters and scores under 0.02.
    """
    return text.count(" ") / len(text) if text else 0.0


def pdf_body(session: requests.Session, paper: Paper,
             cache_dir: Path) -> tuple[str, list[str]]:
    """
    Read the article's PDF with the extractor in extract.py.

    extract.py does the actual work - pdfplumber for layout-aware text, pypdf
    as the fallback, plus its abstract and reference heuristics. This only
    finds the file and maps its output onto the record.
    """
    if pdf_extract is None:
        return "", []
    source = paper.pdf_url
    if not source:
        return "", []

    if pdf_extract.is_url(source):
        name = Path(urlparse(source).path).name or f"{paper.pmcid or 'paper'}.pdf"
        path = download_pdf(session, source, cache_dir / name)
    else:
        path = Path(source)
        path = path if path.exists() else None
    if path is None:
        return "", []

    try:
        pages = pdf_extract.extract_pages_text(path)
        text = "\n".join(pages)
        # pdfplumber is layout-aware but loses the spaces between words on some
        # font encodings - "NFTrigisaweb-basedapplication". pypdf reads those
        # correctly, so when the spacing looks wrong, take whichever is better.
        if len(text.strip()) < 50 or spacing_ratio(text) < 0.08:
            other = pdf_extract.extract_full_text_fallback(path)
            if len(other.split()) > len(text.split()):
                text = other
        if len(text.strip()) < 50:                     # scanned PDF - needs OCR
            return "", []
        if spacing_ratio(text) < 0.08:
            paper.error = paper.error or ("pdf text has no word spacing - the "
                                          "font carries no space glyphs")
        paper.pdf_pages = len(pages) or pdf_extract.get_pdf_properties(path)["num_pages"]
        if not paper.abstract:
            paper.abstract = clean(pdf_extract.extract_abstract(text))
            paper.abstract_words = len(paper.abstract.split())
        if not paper.references:
            paper.references = pdf_extract.extract_references(text)
            paper.reference_count = len(paper.references)
        if not paper.title:
            paper.title = pdf_extract.guess_title_and_authors(path)[0]
    except Exception as exc:                           # noqa: BLE001 - a fallback may fail
        paper.error = paper.error or f"pdf: {short(exc)}"
        return "", []
    return text.strip(), []


def fill_missing_content(api_session: requests.Session, papers: Sequence[Paper],
                         args: argparse.Namespace) -> None:
    """Run the Europe PMC and PDF stages over records with no body text."""
    missing = [p for p in papers if not p.has_full_text and not p.error]
    if not missing:
        return
    log(f"[fallback] {len(missing)} records have no full text in the PMC XML")

    cache = Path(args.out) / "pdf_cache"
    rescued_epmc = rescued_pdf = 0
    for paper in missing:
        if not args.no_epmc:
            body, names = europepmc_body(api_session, paper.pmcid, args.timeout)
            if body:
                paper.sections = paper.sections or names
                set_content(paper, body, "epmc")
                rescued_epmc += 1
                continue
        if not args.no_pdf:
            body, _ = pdf_body(api_session, paper, cache)
            if body:
                set_content(paper, body, "pdf")
                rescued_pdf += 1

    still = sum(1 for p in missing if not p.has_full_text)
    log(f"[fallback] Europe PMC recovered {rescued_epmc}, "
        f"PDF recovered {rescued_pdf}, {still} left abstract-only")


# --------------------------------------------------------------------------- #
# Keyword matching
# --------------------------------------------------------------------------- #

def significant_words(keyword: str) -> list[str]:
    """Words a paper must contain - query operators and field tags stripped."""
    plain = QUERY_SYNTAX_RE.sub(" ", keyword)
    return [w for w in re.findall(r"[a-z0-9]+", plain.lower())
            if w not in STOPWORDS and len(w) > 2]


def score_keyword(paper: Paper, keyword: str) -> float:
    """
    Share of a keyword's significant words present in the record's own text.

    The whole body counts, which is the only fair test against a full-text
    search: PMC will return a paper whose match is in the Methods, and scoring
    it on the abstract alone would call that a miss.
    """
    words = significant_words(keyword)
    if not words:
        return 1.0
    haystack = " ".join([
        paper.title, paper.abstract, " ".join(paper.keywords),
        " ".join(paper.sections), paper.content_paper,
    ]).lower()
    hits = sum(1 for w in words if w in haystack)
    return hits / len(words)


def apply_matching(papers: Sequence[Paper], keywords: Sequence[str],
                   mode: str, drop: bool = True) -> list[Paper]:
    """
    Re-derive matched_keywords, and with `drop` also filter on them.

    `none` keeps whatever NCBI returned - the default, because Entrez already
    expands a term through MeSH and word matching would undo that.
    """
    kept: list[Paper] = []
    for paper in papers:
        ordered: list[str] = []
        best = 0.0
        for kw in keywords:
            score = score_keyword(paper, kw)
            best = max(best, score)
            if (mode == "all" and score >= 1.0) or (mode == "any" and score > 0):
                ordered.append(kw)
        if mode == "none":
            ordered = list(dict.fromkeys(paper.matched_keywords
                                         or [paper.keyword_Search]))
        else:
            ordered = list(dict.fromkeys(ordered))
        paper.match_score = round(best, 3)
        paper.matched_keywords = [k for k in ordered if k]

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
                "full_text": 0, "words": 0, "references": 0, "authors": 0,
            })
            row["papers"] += 1
            row["full_text"] += 1 if rec.get("has_full_text") else 0
            row["words"] += int(rec.get("content_words") or 0)
            row["references"] += int(rec.get("reference_count") or 0)
            row["authors"] += int(rec.get("author_count") or 0)

    rows: list[dict[str, Any]] = []
    for (_month, _kw), row in sorted(buckets.items()):
        row["words_per_paper"] = row["words"] // row["papers"]
        row["authors_per_paper"] = round(row["authors"] / row["papers"], 2)
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
    # Excel drops a cell over 32767 characters, and a full text easily passes it.
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
        sources = Counter(r.get("content_source") for r in ok)
        log(f"  content source     : {dict(sources.most_common())}")
        full = sum(1 for r in ok if r.get("has_full_text"))
        log(f"  with full text     : {full} / {len(ok)}")
        wc = [r.get("content_words", 0) for r in ok]
        log(f"  body words (avg/max): {sum(wc) // max(len(wc), 1)} / "
            f"{max(wc, default=0)}")
        refs = [r.get("reference_count", 0) for r in ok]
        log(f"  references (avg)   : {sum(refs) // max(len(refs), 1)}")
        log(f"  open licence       : {sum(1 for r in ok if r.get('is_oa'))}")
    log("=" * 66)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Harvest PMC through NCBI E-utilities into a "
                    "trend-forecasting dataset, with full text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="A free NCBI API key raises the rate limit from 3 to 10 req/s: "
               "--api-key or NCBI_API_KEY.",
    )
    p.add_argument("--keywords", nargs="+", metavar="KEYWORD",
                   help="search terms - Entrez query syntax allowed "
                        "(default: read keywords.txt)")
    p.add_argument("--keywords-file", default=str(KEYWORDS_FILE),
                   help="file of keywords, one per line (default keywords.txt)")
    p.add_argument("--since", default=DEFAULT_SINCE, metavar="YYYY-MM-DD",
                   help=f"earliest publication date (default {DEFAULT_SINCE}; "
                        f"empty string for no lower bound)")
    p.add_argument("--until", default=DEFAULT_UNTIL, metavar="YYYY-MM-DD",
                   help=f"latest publication date (default {DEFAULT_UNTIL})")
    p.add_argument("--date-field", default="publication",
                   choices=sorted(DATE_FIELDS),
                   help="which NCBI date the window filters on "
                        "(default publication)")
    p.add_argument("--sort", default="pub_date",
                   choices=["pub_date", "relevance"],
                   help="esearch ordering (default pub_date = most recent)")
    p.add_argument("--match", default="none", choices=["none", "all", "any"],
                   help="keep whatever NCBI returned (none - the default, since "
                        "Entrez already expands terms through MeSH), or "
                        "re-filter on every (all) / any significant word")
    p.add_argument("--per-keyword", type=int, default=0, metavar="N",
                   help="cap hits per keyword (default 0 = every reachable hit)")
    p.add_argument("--limit", type=int,
                   help="cap the articles actually fetched (smoke tests)")
    p.add_argument("--batch", type=int, default=FETCH_BATCH,
                   help=f"articles per efetch call (default {FETCH_BATCH})")
    p.add_argument("--api-key", default=os.environ.get("NCBI_API_KEY", ""),
                   help="NCBI API key (or set NCBI_API_KEY) - raises the rate "
                        "limit from 3 to 10 requests/second")
    p.add_argument("--email", default=os.environ.get("NCBI_EMAIL", ""),
                   help="contact address sent with every call, as NCBI asks "
                        "(or set NCBI_EMAIL)")
    p.add_argument("--timeout", type=int, default=120,
                   help="per-request timeout in seconds (default 120)")
    p.add_argument("--rate", type=float, default=0.0,
                   help="override requests/second (default 3, or 10 with a key)")
    p.add_argument("--no-epmc", action="store_true",
                   help="skip the Europe PMC fallback for records PMC returns "
                        "without a body")
    p.add_argument("--no-pdf", action="store_true",
                   help="skip the PDF fallback (extract.py) entirely")
    p.add_argument("--pdf-url", nargs="+", metavar="URL",
                   help="read these PDFs with extract.py and add them as "
                        "records - URLs or local paths, no search involved")
    p.add_argument("--out", default=str(DATA_DIR),
                   help="output directory (default ./data)")
    p.add_argument("--top", type=int, default=50,
                   help="rows per facet table (default 50)")
    p.add_argument("--refresh", action="store_true",
                   help="re-fetch papers already present in pmc_papers.jsonl "
                        "(also ignores and truncates the temp backup)")
    p.add_argument("--no-checkpoint", action="store_true",
                   help="do not keep the pmc_papers.partial.jsonl temp backup - "
                        "an interrupted run then loses everything")
    p.add_argument("--keep-partial", action="store_true",
                   help="keep the temp backup after a successful run instead of "
                        "deleting it")
    p.add_argument("--dry-run", action="store_true",
                   help="report hits per keyword and exit")
    return p


def papers_from_pdfs(session: requests.Session, sources: Sequence[str],
                     out_dir: Path) -> list[Paper]:
    """--pdf-url: build records straight from PDFs, using extract.py."""
    if pdf_extract is None:
        log(f"[pdf] extract.py could not be imported ({PDF_IMPORT_ERROR}) - "
            f"install its dependencies: pip install pdfplumber pypdf")
        return []
    out: list[Paper] = []
    cache = out_dir / "pdf_cache"
    for src in sources:
        paper = Paper(id=src, pdf_url=src, keyword_Search="--pdf-url",
                      matched_keywords=["--pdf-url"], retrieved_at=now_iso())
        body, _ = pdf_body(session, paper, cache)
        set_content(paper, body, "pdf")
        paper.deep_scraped = True
        paper.scraped_at = now_iso()
        if not body and not paper.error:
            paper.error = "no text extracted (unreachable, or a scanned PDF)"
        log(f"  [pdf] {src[:70]}  "
            f"{paper.content_words}w over {paper.pdf_pages} pages"
            + (f"  !! {paper.error}" if paper.error else ""))
        out.append(paper)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    out_dir = Path(args.out)
    papers_jsonl = out_dir / "pmc_papers.jsonl"
    papers_csv = out_dir / "pmc_papers.csv"
    started = time.time()

    api = Entrez(api_key=args.api_key, email=args.email, timeout=args.timeout,
                 rate=args.rate)

    # --pdf-url is a standalone mode: no search, just read the PDFs given.
    if args.pdf_url:
        log(f"[run] reading {len(args.pdf_url)} PDF(s) with extract.py")
        papers = papers_from_pdfs(api.session, args.pdf_url, out_dir)
        records = [asdict(p) for p in papers]
        if records:
            write_jsonl(out_dir / "pmc_pdf_papers.jsonl", records)
            write_csv(out_dir / "pmc_pdf_papers.csv",
                      [flatten_for_csv(r) for r in records])
        summarise(records)
        return 0 if any(not r.get("error") for r in records) else 1

    keywords = args.keywords or load_keywords(Path(args.keywords_file))
    if not keywords:
        log("[run] no keywords - nothing to search")
        return 1

    log(f"[run] {len(keywords)} keywords  window {args.since or '-'}.."
        f"{args.until or '-'}  sort={args.sort}  match={args.match}  "
        f"rate={'10/s (api key)' if args.api_key else '3/s (anonymous)'}")
    if not args.email:
        log("[run] no --email / NCBI_EMAIL set - NCBI asks callers to identify "
            "themselves so they can warn you before blocking you")

    checkpoint = Checkpoint(out_dir / "pmc_papers.partial.jsonl",
                            enabled=not (args.no_checkpoint or args.dry_run))
    recovered = checkpoint.open(resume=not args.refresh)

    existing: dict[str, dict[str, Any]] = {}
    resumed: dict[str, dict[str, Any]] = {}
    papers: list[Paper] = []

    try:
        # ---- 1. search -----------------------------------------------------
        if args.dry_run:
            for kw in keywords:
                term = build_term(kw, args.since, args.until, args.date_field)
                try:
                    total, _ = api.esearch(term, 0, 1, args.sort)
                except Exception as exc:               # noqa: BLE001
                    log(f"  {kw:<40} !! {short(exc)}")
                    continue
                reach = min(total, RESULT_CEILING)
                log(f"  {kw:<40} ~{total:>7} hits"
                    + (f"  ({reach} reachable)" if reach != total else ""))
            return 0

        wanted: dict[str, str] = {}                    # pmcid (bare) -> keyword
        for kw in keywords:
            _, ids = search_keyword(api, kw, args)
            for uid in ids:
                wanted.setdefault(uid, kw)
        log(f"[search] {len(wanted)} unique papers across {len(keywords)} keywords")

        existing = {} if args.refresh else load_existing(papers_jsonl)
        if existing:
            done = {k for k, rec in existing.items() if rec.get("deep_scraped")}
            before = len(wanted)
            wanted = {u: kw for u, kw in wanted.items() if f"PMC{u}" not in done}
            log(f"[run] {len(existing)} papers already in {papers_jsonl.name} - "
                f"{before - len(wanted)} skipped, {len(wanted)} to fetch")

        resumed = {pid: rec for pid, rec in recovered.items()
                   if rec.get("deep_scraped")}
        if resumed:
            before = len(wanted)
            wanted = {u: kw for u, kw in wanted.items() if f"PMC{u}" not in resumed}
            log(f"[resume] {len(resumed)} records already fetched - "
                f"{before - len(wanted)} skipped, {len(wanted)} left")

        uids = list(wanted)
        if args.limit:
            uids = uids[:args.limit]
            log(f"[run] limited to {len(uids)} papers")

        # ---- 2. fetch full text in batches ---------------------------------
        for start in range(0, len(uids), args.batch):
            chunk = uids[start:start + args.batch]
            try:
                batch = parse_batch(api.efetch(chunk))
            except Exception as exc:                   # noqa: BLE001
                log(f"  [{start + 1}-{start + len(chunk)}] !! {short(exc)}")
                continue
            for paper in batch:
                paper.keyword_Search = wanted.get(paper.pmcid.removeprefix("PMC"), "")
                paper.matched_keywords = ([paper.keyword_Search]
                                          if paper.keyword_Search else [])
            fill_missing_content(api.session, batch, args)
            papers.extend(batch)
            checkpoint.append([asdict(p) for p in batch])
            got = sum(1 for p in batch if p.has_full_text)
            log(f"  [{start + len(chunk)}/{len(uids)}] {len(batch)} articles, "
                f"{got} with full text, "
                f"{sum(p.content_words for p in batch):,} words")
    finally:
        checkpoint.close()

    # ---- 3. score, merge, write --------------------------------------------
    kept = apply_matching(papers, keywords, args.match, drop=(args.match != "none"))
    if len(kept) != len(papers):
        log(f"[match] --match {args.match}: {len(papers)} -> {len(kept)} papers")

    merged: dict[str, dict[str, Any]] = dict(existing)
    for rec in resumed.values():                       # recovered from the backup
        merged[rec["id"]] = rec
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

    if args.keep_partial:
        log(f"[write] --keep-partial: {checkpoint.path.name} left in place "
            f"({checkpoint.written} appends this run)")
    else:
        checkpoint.discard()

    write_csv(out_dir / "pmc_timeseries.csv", build_timeseries(records))

    write_json(out_dir / "pmc_facets.json", {
        "generated_at": now_iso(),
        "source": {
            "site": PMC_BASE,
            "method": "NCBI E-utilities: esearch db=pmc + efetch JATS full text",
            "esearch": f"{EUTILS}/esearch.fcgi?db=pmc&term=<keyword>",
            "efetch": f"{EUTILS}/efetch.fcgi?db=pmc&id=<ids>&retmode=xml",
            "fallbacks": "Europe PMC fullTextXML, then the PDF reader in extract.py",
            "note": "PMC covers the open-access and funder-deposited subset of "
                    "PubMed, with full text. NCBI serves at most the first "
                    "10,000 hits of any search.",
        },
        "run": {
            "keywords": keywords,
            "since": args.since,
            "until": args.until,
            "date_field": DATE_FIELDS[args.date_field],
            "sort": args.sort,
            "match": args.match,
            "midpoint_month": midpoint(args.since or DEFAULT_SINCE,
                                       args.until or DEFAULT_UNTIL),
            "api_calls": api.calls,
            "seconds": round(time.time() - started, 1),
        },
        "totals": {
            "papers": len(records),
            "with_full_text": sum(1 for r in records if r.get("has_full_text")),
            "by_content_source": dict(Counter(r.get("content_source")
                                              for r in records)),
            "failed": sum(1 for r in records if r.get("error")),
            "months": len({r.get("publication_month") for r in records
                           if r.get("publication_month")}),
        },
        "facets": build_facets(records, args.top),
    })

    summarise(records)
    log(f"[run] done in {time.time() - started:.1f}s, {api.calls} API calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
