import re
from dataclasses import dataclass, asdict
from urllib.parse import urlparse

import httpx

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.-]*")
NUMBER_RE = re.compile(r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?%?\b")
STOPWORDS = {
    "the", "and", "that", "with", "from", "this", "they", "their", "there", "have", "has", "had",
    "was", "were", "are", "for", "but", "not", "into", "about", "after", "before", "during", "while",
    "said", "says", "according", "reported", "report", "reports", "would", "could", "should", "will", "been",
    "being", "also", "than", "then", "its", "his", "her", "him", "she", "who", "which", "when", "where",
    "what", "over", "under", "more", "most", "some", "one", "two", "our", "out", "new", "now", "still",
}


@dataclass
class DiscoveryLead:
    provider: str
    kind: str
    title: str
    url: str
    source_name: str | None = None
    published_at: str | None = None
    query: str | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _tokens(text: str) -> list[str]:
    values = []
    seen = set()
    for token in TOKEN_RE.findall(text):
        normalized = token.lower().strip(".'’-")
        if len(normalized) < 3 or normalized in STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        values.append(token.strip(".'’-") )
    return values


def build_discovery_queries(claim_text: str, *, max_queries: int = 3) -> list[str]:
    """Create short, inspectable searches from a claim.

    Query generation is deterministic and deliberately avoids hidden rewriting or truth assumptions.
    """
    tokens = _tokens(claim_text)
    numbers = NUMBER_RE.findall(claim_text)

    # Give named/proper-looking terms priority, then preserve a few content terms.
    proper = [token for token in tokens if token[:1].isupper()]
    content = [token for token in tokens if token not in proper]
    base_terms = (proper[:6] + content[:5])[:9]
    if not base_terms:
        base_terms = tokens[:8]

    queries: list[str] = []
    if base_terms:
        queries.append(" ".join(base_terms))
    if numbers and base_terms:
        queries.append(" ".join(base_terms[:6] + numbers[:2]))

    # Exact phrase search is useful for distinctive short claims but avoid huge quoted strings.
    normalized = re.sub(r"\s+", " ", claim_text).strip()
    if 20 <= len(normalized) <= 140:
        queries.append(f'"{normalized}"')

    unique: list[str] = []
    for query in queries:
        query = re.sub(r"\s+", " ", query).strip()
        if query and query not in unique:
            unique.append(query)
        if len(unique) >= max_queries:
            break
    return unique


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _is_same_source(url: str, article_url: str | None) -> bool:
    return bool(article_url and _host(url) and _host(url) == _host(article_url))


def discover_gdelt(
    query: str,
    *,
    article_url: str | None = None,
    max_results: int = 8,
    timeout_seconds: float = 8.0,
) -> list[DiscoveryLead]:
    """Search GDELT DOC 2.0 for independent coverage leads."""
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max(1, min(max_results * 2, 30)),
        "timespan": "3months",
        "sort": "datedesc",
    }
    try:
        response = httpx.get(endpoint, params=params, timeout=timeout_seconds, headers={"User-Agent": "AmericanIdeaEvidence/1.1"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []

    articles = payload.get("articles") or []
    leads: list[DiscoveryLead] = []
    seen: set[str] = set()
    for item in articles:
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title or url in seen or _is_same_source(url, article_url):
            continue
        host = _host(url)
        if not host:
            continue
        seen.add(url)
        leads.append(
            DiscoveryLead(
                provider="gdelt",
                kind="secondary",
                title=title[:300],
                url=url,
                source_name=str(item.get("domain") or host),
                published_at=str(item.get("seendate") or "") or None,
                query=query,
                note="Discovered through GDELT global news search. This is an unverified lead, not corroboration by itself.",
            )
        )
        if len(leads) >= max_results:
            break
    return leads


def discover_federal_register(
    query: str,
    *,
    max_results: int = 6,
    timeout_seconds: float = 8.0,
) -> list[DiscoveryLead]:
    """Search official Federal Register documents for primary-source leads."""
    endpoint = "https://www.federalregister.gov/api/v1/documents.json"
    params = {
        "conditions[term]": query,
        "per_page": max(1, min(max_results, 20)),
        "order": "newest",
    }
    try:
        response = httpx.get(endpoint, params=params, timeout=timeout_seconds, headers={"User-Agent": "AmericanIdeaEvidence/1.1"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []

    leads: list[DiscoveryLead] = []
    seen: set[str] = set()
    for item in payload.get("results") or []:
        url = str(item.get("html_url") or item.get("pdf_url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title or url in seen:
            continue
        seen.add(url)
        agencies = item.get("agencies") or []
        agency_names = [str(agency.get("name")) for agency in agencies if agency.get("name")]
        leads.append(
            DiscoveryLead(
                provider="federal_register",
                kind="primary",
                title=title[:300],
                url=url,
                source_name=", ".join(agency_names[:3]) or "Federal Register",
                published_at=str(item.get("publication_date") or "") or None,
                query=query,
                note="Official Federal Register result. It is still only an evidence lead until the document is fetched and compared with the claim.",
            )
        )
        if len(leads) >= max_results:
            break
    return leads


def discover_evidence_for_claim(
    claim_text: str,
    *,
    article_url: str | None = None,
    max_results: int = 12,
) -> dict:
    queries = build_discovery_queries(claim_text)
    leads: list[DiscoveryLead] = []
    seen_urls: set[str] = set()

    for query in queries[:2]:
        for lead in discover_federal_register(query, max_results=4):
            if lead.url not in seen_urls:
                seen_urls.add(lead.url)
                leads.append(lead)
        for lead in discover_gdelt(query, article_url=article_url, max_results=6):
            if lead.url not in seen_urls:
                seen_urls.add(lead.url)
                leads.append(lead)
        if len(leads) >= max_results:
            break

    # Primary leads first, then newest/available secondary leads. No truth ranking.
    leads.sort(key=lambda item: (0 if item.kind == "primary" else 1, item.provider, item.title.lower()))
    leads = leads[:max_results]

    return {
        "claim_text": claim_text,
        "queries": queries,
        "leads": [lead.to_dict() for lead in leads],
        "lead_count": len(leads),
        "methodology_note": (
            "Evidence Discovery generates transparent searches from the claim and queries public discovery adapters. "
            "Results are leads only. Provider rank, outlet reputation, and search position are not treated as evidence of truth. "
            "Each useful lead must be fetched, fingerprinted, and compared with the claim before it can affect status."
        ),
    }
