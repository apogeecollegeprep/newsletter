from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


INOREADER_API = "https://www.inoreader.com/reader/api/0"
INOREADER_TOKEN_URL = "https://www.inoreader.com/oauth2/token"
AIRTABLE_API = "https://api.airtable.com/v0"

DEFAULT_BASE_ID = "appjM2J9lAfpLyfd7"
DEFAULT_CANDIDATES_TABLE_ID = "tblZkI1A7D0Mgz98Y"
DEFAULT_SOURCES_TABLE_ID = "tblrqCsw2hFqXHwgV"

TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}

CATEGORY_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Glimpse / Applicant Video",
        ("glimpse", "initialview", "video introduction", "video supplement", "applicant video"),
    ),
    (
        "Financial Aid",
        (
            "fafsa",
            "financial aid",
            "student aid",
            "state aid",
            "pell grant",
            "scholarship",
            "loan limit",
            "tuition assistance",
            "net price",
        ),
    ),
    (
        "College Financial Health",
        (
            "college closure",
            "university closure",
            "shutting down",
            "financial distress",
            "financial emergency",
            "teach-out",
            "merger",
            "accreditation loss",
            "bankrupt",
            "insolvency",
            "budget deficit",
        ),
    ),
    (
        "Admissions Policy",
        (
            "admissions",
            "admission essay",
            "admissions essay",
            "application essay",
            "admissions policy",
            "admission policy",
            "test optional",
            "test-optional",
            "test required",
            "test-required",
            "standardized test",
            "legacy admission",
            "legacy admissions",
            "affirmative action",
            "common app",
            "early decision",
            "early action",
            "application requirement",
            "application deadline",
            "supplemental essay",
            "supplemental writing",
            "writing supplement",
            "college supplement",
            "school-specific essay",
            "school specific essay",
            "short-answer question",
            "short answer question",
            "essay requirement",
            "application writing requirement",
            "why us essay",
            "why college essay",
            "get admitted",
            "getting admitted",
            "college admission",
            "college admissions",
        ),
    ),
    (
        "Application Trends",
        (
            "application volume",
            "application rate",
            "acceptance rate",
            "admit rate",
            "yield rate",
            "applicant pool",
            "applications rose",
            "applications fell",
            "record applications",
        ),
    ),
)

# Investigative admissions stories often use language about cheating or fraud
# instead of conventional policy terms. These are strong applicant-facing
# signals when they appear alongside an application/admissions reference.
ADMISSIONS_INTEGRITY_TERMS = (
    "admissions fraud",
    "application fraud",
    "fraud squad",
    "application cheating",
    "cheating on applications",
    "dishonest application",
    "dishonest submission",
    "falsified application",
    "false application claim",
    "misrepresented application",
    "application verification",
    "verify applications",
    "vetting applications",
    "vet every admitted student",
    "application accuracy",
    "ai fueled cheating",
    "ai-fueled cheating",
)

# Body matching is deliberately stricter than headline matching. Only the
# first few article paragraphs are inspected, avoiding feed footers, navigation
# and unrelated-story modules that frequently contain generic admissions words.
LEAD_CATEGORY_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Glimpse / Applicant Video", ("glimpse video", "applicant video", "video supplement")),
    (
        "Financial Aid",
        ("fafsa deadline", "pell grant eligibility", "financial aid application", "state grant award", "aid award was reduced"),
    ),
    (
        "College Financial Health",
        ("college will close", "university will close", "teach-out plan", "declared financial emergency", "lost accreditation"),
    ),
    (
        "Admissions Policy",
        (
            "applicants will be required",
            "applicants will no longer be required",
            "applicants must submit",
            "changed its application requirements",
            "changed its admissions policy",
            "application verification",
            "vetting applications",
            "dishonest submissions",
        ),
    ),
    (
        "Application Trends",
        ("applications increased", "applications decreased", "applicant pool grew", "acceptance rate fell", "admitted less than"),
    ),
)

EXCLUDED_TERMS = (
    "campus life",
    "student housing",
    "dormitory",
    "faculty hiring",
    "faculty union",
    "campus dining",
    "student retention",
    "graduation rate",
    "study abroad",
)

INTERNATIONAL_ONLY_TERMS = (
    "visa",
    "international student visa",
    "foreign student visa",
    "f-1 visa",
    "international applicants only",
)

GRADUATE_ONLY_TERMS = (
    "mba",
    "law school",
    "duke law",
    "medical school",
    "graduate admission",
    "graduate program",
    "grad school",
    "masters program",
    "doctoral",
    "phd",
    "llm",
)

LOW_ACTIONABILITY_TERMS = (
    "from the archives",
    "historical overview",
    "history of",
    "hidden helpers",
)

# A modest regional tie-breaker based on the application counts supplied by
# Apogee. It never overrides topical relevance; it only separates otherwise
# comparable stories. Higher values represent greater Apogee audience interest.
SOUTHEAST_SCHOOL_PRIORITIES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (3, ("university of georgia", "uga today", "red black", "news uga edu")),
    (3, ("university of south carolina", "daily gamecock", "sc edu uofsc")),
    (3, ("university of alabama", "ua news", "crimson white", "news ua edu")),
    (3, ("georgia institute of technology", "georgia tech", "technique", "gatech edu", "nique net")),
    (2, ("georgia state university", "news gsu edu", "georgiastatesignal com")),
    (2, ("kennesaw state university", "kennesaw edu", "ksusentinel com")),
    (2, ("florida state university", "fsu news", "fsview", "news fsu edu", "fsunews com")),
    (2, ("georgia college state university", "bobcat multimedia", "gcsu edu")),
    (2, ("auburn university", "auburn wire", "auburn plainsman", "theplainsman com")),
    (2, ("university of tennessee knoxville", "ut news", "daily beacon", "news utk edu")),
    (2, ("university of florida", "uf news", "florida alligator", "news ufl edu", "alligator org")),
    (1, ("college of charleston", "college today", "cisternyard", "cofc edu")),
    (1, ("clemson university", "clemson news", "the tiger clemson", "clemson edu", "thetigercu com")),
    (1, ("georgia southern university", "george anne", "georgiasouthern edu")),
    (1, ("university of kentucky", "uknow", "kentucky kernel", "uky edu", "kykernel com")),
    (1, ("university of mississippi", "ole miss", "daily mississippian", "olemiss edu", "thedmonline com")),
    (1, ("emory university", "emory news", "emory wheel", "emory edu", "emorywheel com")),
    (1, ("elon university", "elon news network", "elon edu", "elonnewsnetwork com")),
)


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Source:
    name: str
    tier: str
    website_url: str
    feed_url: str = ""


@dataclass(frozen=True)
class Candidate:
    headline: str
    url: str
    source: str
    published_at: str
    category: str
    relevance_score: int
    source_quality: int


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def extract_lead_text(content: str, *, paragraphs: int = 3, maximum: int = 2400) -> str:
    """Extract a bounded article lead from HTML or plain-text feed content."""
    cleaned = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", content, flags=re.IGNORECASE | re.DOTALL)
    paragraph_html = re.findall(r"<p\b[^>]*>(.*?)</p>", cleaned, flags=re.IGNORECASE | re.DOTALL)
    selected = paragraph_html[:paragraphs] if paragraph_html else [cleaned]
    text = " ".join(re.sub(r"<[^>]+>", " ", value) for value in selected)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:maximum]


def admissions_integrity_priority(title: str, content: str = "") -> int:
    combined = normalize_text(f"{title} {extract_lead_text(content)}")
    has_context = any(term in combined for term in ("admission", "application", "applicant"))
    return int(has_context and any(normalize_text(term) in combined for term in ADMISSIONS_INTEGRITY_TERMS))


def southeast_school_priority(title: str, source: str = "", url: str = "") -> int:
    """Return Apogee's regional tie-break priority for a school-related story."""
    text = normalize_text(f"{title} {source} {url}")
    for priority, aliases in SOUTHEAST_SCHOOL_PRIORITIES:
        if any(alias in text for alias in aliases):
            return priority
    return 0


def canonicalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    host = (parts.hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    if parts.port:
        host = f"{host}:{parts.port}"
    query_pairs = []
    for pair in parts.query.split("&") if parts.query else []:
        key = pair.split("=", 1)[0].casefold()
        if key.startswith("utm_") or key in TRACKING_KEYS:
            continue
        query_pairs.append(pair)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.casefold() or "https", host, path, "&".join(query_pairs), ""))


def classify_category(title: str, content: str = "") -> str | None:
    title_text = normalize_text(title)
    lead_text = normalize_text(extract_lead_text(content))
    combined = f"{title_text} {lead_text}".strip()
    if any(normalize_text(term) in title_text for term in EXCLUDED_TERMS):
        return None
    if any(normalize_text(term) in combined for term in INTERNATIONAL_ONLY_TERMS):
        return None
    if any(normalize_text(term) in combined for term in GRADUATE_ONLY_TERMS):
        return None
    if any(normalize_text(term) in title_text for term in LOW_ACTIONABILITY_TERMS):
        return None
    if admissions_integrity_priority(title, content):
        return "Admissions Policy"
    for category, terms in CATEGORY_TERMS:
        if any(normalize_text(term) in title_text for term in terms):
            return category
    for category, terms in LEAD_CATEGORY_TERMS:
        if any(normalize_text(term) in lead_text for term in terms):
            return category
    return None


def source_matches(origin_title: str, article_url: str, source: Source) -> bool:
    origin = normalize_text(origin_title)
    source_name = normalize_text(source.name)
    name_match = bool(source_name and (source_name in origin or origin in source_name))

    article_host = (urlsplit(article_url).hostname or "").casefold().removeprefix("www.")
    source_host = (urlsplit(source.website_url).hostname or "").casefold().removeprefix("www.")
    host_match = bool(source_host and (article_host == source_host or article_host.endswith(f".{source_host}")))

    feed_parts = urlsplit(source.feed_url)
    feed_query = parse_qs(feed_parts.query).get("q", [""])[0]
    query_match = bool(
        feed_parts.hostname == "news.google.com"
        and feed_query
        and normalize_text(unquote(feed_query)) in origin
    )
    return name_match or host_match or query_match


def source_quality(tier: str) -> int:
    return {"Primary / Official": 5, "Tier 1": 5, "Tier 2": 3}.get(tier, 2)


def monday_for(dt: datetime) -> str:
    return (dt.date() - timedelta(days=dt.weekday())).isoformat()


class RetryingSession:
    def __init__(self) -> None:
        self.user_agent = "Apogee-Admissions-Newsletter/0.1"

    def request(self, method: str, url: str, **kwargs: Any) -> "HttpResponse":
        params = kwargs.pop("params", None)
        if params:
            query = urlencode(params, doseq=True)
            url = f"{url}{'&' if '?' in url else '?'}{query}"
        headers = {"User-Agent": self.user_agent, **kwargs.pop("headers", {})}
        body = None
        if "json" in kwargs:
            body = json.dumps(kwargs.pop("json")).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif "data" in kwargs:
            data = kwargs.pop("data")
            body = urlencode(data).encode("utf-8") if isinstance(data, dict) else data
        if kwargs:
            raise TypeError(f"Unsupported HTTP options: {', '.join(kwargs)}")

        for attempt in range(5):
            request = Request(url, data=body, headers=headers, method=method)
            try:
                with urlopen(request, timeout=30) as response:
                    return HttpResponse(response.status, dict(response.headers), response.read())
            except HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt == 4:
                    detail = error.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"HTTP {error.code} from {url}: {detail}") from error
                delay = float(error.headers.get("Retry-After", 2**attempt))
                time.sleep(min(delay, 30))
        raise AssertionError("unreachable")


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class InoreaderClient:
    def __init__(self, http: RetryingSession) -> None:
        self.http = http
        self.client_id = required_env("INOREADER_CLIENT_ID")
        self.client_secret = required_env("INOREADER_CLIENT_SECRET")
        self.refresh_token = required_env("INOREADER_REFRESH_TOKEN")
        self.access_token = ""

    def refresh_access_token(self) -> None:
        response = self.http.request(
            "POST",
            INOREADER_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        payload = response.json()
        self.access_token = payload["access_token"]

    @property
    def headers(self) -> dict[str, str]:
        if not self.access_token:
            self.refresh_access_token()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "AppId": self.client_id,
            "AppKey": self.client_secret,
        }

    def get_items(self, stream_id: str, lookback_hours: int, maximum: int) -> list[dict[str, Any]]:
        cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
        params: dict[str, str | int] = {
            "n": min(100, maximum),
            "ot": str(int(cutoff.timestamp() * 1_000_000)),
            "output": "json",
        }
        encoded_stream = quote(stream_id, safe="")
        url = f"{INOREADER_API}/stream/contents/{encoded_stream}"
        items: list[dict[str, Any]] = []
        while len(items) < maximum:
            response = self.http.request("GET", url, params=params, headers=self.headers)
            payload = response.json()
            items.extend(payload.get("items", []))
            continuation = payload.get("continuation")
            if not continuation:
                break
            params["c"] = continuation
            params["n"] = min(100, maximum - len(items))
        return items[:maximum]


class AirtableClient:
    def __init__(self, http: RetryingSession) -> None:
        self.http = http
        self.token = required_env("AIRTABLE_TOKEN")
        self.base_id = os.getenv("AIRTABLE_BASE_ID", DEFAULT_BASE_ID)
        self.candidates_table = os.getenv("AIRTABLE_CANDIDATES_TABLE_ID", DEFAULT_CANDIDATES_TABLE_ID)
        self.sources_table = os.getenv("AIRTABLE_SOURCES_TABLE_ID", DEFAULT_SOURCES_TABLE_ID)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _table_url(self, table_id: str) -> str:
        return f"{AIRTABLE_API}/{self.base_id}/{quote(table_id, safe='')}"

    def list_records(self, table_id: str, fields: Iterable[str]) -> list[dict[str, Any]]:
        params: list[tuple[str, str]] = [("pageSize", "100")]
        params.extend(("fields[]", field) for field in fields)
        records: list[dict[str, Any]] = []
        offset: str | None = None
        while True:
            page_params = [*params]
            if offset:
                page_params.append(("offset", offset))
            response = self.http.request("GET", self._table_url(table_id), params=page_params, headers=self.headers)
            payload = response.json()
            records.extend(payload.get("records", []))
            offset = payload.get("offset")
            if not offset:
                return records

    def active_sources(self) -> list[Source]:
        records = self.list_records(
            self.sources_table,
            ("Source Name", "Tier", "Website URL", "Feed URL", "Active"),
        )
        result = []
        for record in records:
            fields = record.get("fields", {})
            if fields.get("Active") and fields.get("Source Name"):
                result.append(
                    Source(
                        name=fields["Source Name"],
                        tier=fields.get("Tier", "Tier 2"),
                        website_url=fields.get("Website URL", ""),
                        feed_url=fields.get("Feed URL", ""),
                    )
                )
        return result

    def existing_urls(self) -> set[str]:
        records = self.list_records(self.candidates_table, ("URL",))
        return {
            canonicalize_url(record["fields"]["URL"])
            for record in records
            if record.get("fields", {}).get("URL")
        }

    def create_candidates(self, candidates: list[Candidate]) -> int:
        created = 0
        for start in range(0, len(candidates), 10):
            batch = candidates[start : start + 10]
            records = []
            for candidate in batch:
                records.append(
                    {
                        "fields": {
                            "Headline": candidate.headline,
                            "URL": candidate.url,
                            "Source": candidate.source,
                            "Published At": candidate.published_at,
                            "Category": candidate.category,
                            "Status": "New",
                            "Relevance Score": candidate.relevance_score,
                            "Source Quality": candidate.source_quality,
                            "Issue Week": monday_for(datetime.fromisoformat(candidate.published_at)),
                            "Editorial Notes": (
                                "Queued automatically from an approved Inoreader source. "
                                "Open and review the full accessible article before publication; "
                                "add a 2–4 sentence neutral summary and applicant impact."
                            ),
                        }
                    }
                )
            self.http.request(
                "POST",
                self._table_url(self.candidates_table),
                headers=self.headers,
                json={"records": records, "typecast": False},
            )
            created += len(batch)
        return created


def candidate_from_item(item: dict[str, Any], sources: list[Source]) -> Candidate | None:
    canonical = item.get("canonical") or []
    alternate = item.get("alternate") or []
    links = canonical or alternate
    if not links or not links[0].get("href"):
        return None

    url = canonicalize_url(links[0]["href"])
    title = re.sub(r"\s+", " ", item.get("title", "")).strip()
    title_and_url = normalize_text(f"{title} {url}")
    if any(normalize_text(term) in title_and_url for term in GRADUATE_ONLY_TERMS):
        return None
    summary = item.get("summary", {}).get("content", "")
    category = classify_category(title, summary)
    if not title or not category:
        return None

    origin = item.get("origin", {})
    origin_title = origin.get("title", "")
    matched = next((source for source in sources if source_matches(origin_title, url, source)), None)
    if not matched:
        return None

    published_epoch = item.get("published") or item.get("updated")
    if not published_epoch:
        return None
    published = datetime.fromtimestamp(int(published_epoch), UTC)
    relevance = {
        "Admissions Policy": 5,
        "Glimpse / Applicant Video": 5,
        "Application Trends": 4,
        "Financial Aid": 4,
        "College Financial Health": 4,
    }.get(category, 3)
    if admissions_integrity_priority(title, summary):
        relevance = 6
    return Candidate(
        headline=title,
        url=url,
        source=matched.name,
        published_at=published.isoformat(),
        category=category,
        relevance_score=relevance,
        source_quality=source_quality(matched.tier),
    )


def sync(*, dry_run: bool = False) -> dict[str, int]:
    http = RetryingSession()
    airtable = AirtableClient(http)
    inoreader = InoreaderClient(http)
    stream_id = os.getenv("INOREADER_STREAM_ID", "user/-/state/com.google/reading-list")
    lookback_hours = int(os.getenv("LOOKBACK_HOURS", "28"))
    maximum = int(os.getenv("MAX_INOREADER_ITEMS", "500"))
    candidate_limit = int(os.getenv("MAX_CANDIDATES", "10"))

    sources = airtable.active_sources()
    if not sources:
        raise ConfigurationError("No active sources are configured in Airtable")

    items = inoreader.get_items(stream_id, lookback_hours, maximum)
    existing = airtable.existing_urls()
    candidates: list[Candidate] = []
    seen = set(existing)
    cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
    for item in items:
        candidate = candidate_from_item(item, sources)
        if (
            candidate
            and datetime.fromisoformat(candidate.published_at) >= cutoff
            and candidate.url not in seen
        ):
            candidates.append(candidate)
            seen.add(candidate.url)

    candidates.sort(
        key=lambda candidate: (
            candidate.relevance_score,
            southeast_school_priority(candidate.headline, candidate.source, candidate.url),
            candidate.source_quality,
            candidate.published_at,
        ),
        reverse=True,
    )
    candidates = candidates[:candidate_limit]

    created = 0 if dry_run else airtable.create_candidates(candidates)
    return {"items_read": len(items), "qualified": len(candidates), "created": created}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync approved Inoreader stories into Airtable")
    parser.add_argument("--dry-run", action="store_true", help="Read and qualify items without writing candidates")
    args = parser.parse_args()
    result = sync(dry_run=args.dry_run)
    print(
        f"Read {result['items_read']} Inoreader items; "
        f"{result['qualified']} new candidates qualified; {result['created']} created in Airtable."
    )


if __name__ == "__main__":
    main()
