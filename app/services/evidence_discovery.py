import re
from dataclasses import dataclass, asdict
from urllib.parse import urlparse

import httpx

from .source_intelligence import is_life_science_claim, official_domains_for_claim

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
        values.append(token.strip(".'’-"))
    return values


def build_discovery_queries(claim_text: str, *, max_queries: int = 3) -> list[str]:
    """Create short, inspectable searches from a claim."""
    tokens = _tokens(claim_text)
    numbers = NUMBER_RE.findall(claim_text)
    proper = [token for token in tokens if token[:1].isupper()]
    content = [token for token in tokens if token not in proper]
    base_terms = (proper[:6] + content[:5])[:9] or tokens[:8]

    queries: list[str] = []
    if base_terms:
        queries.append(" ".join(base_terms))
    if numbers and base_terms:
        queries.append(" ".join(base_terms[:6] + numbers[:2]))

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


def discover_gdelt(query: str, *, article_url: str | None = None, max_results: int = 8, timeout_seconds: float = 8.0) -> list[DiscoveryLead]:
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {"query": query, "mode": "artlist", "format": "json", "maxrecords": max(1, min(max_results * 2, 30)), "timespan": "3months", "sort": "datedesc"}
    try:
        response = httpx.get(endpoint, params=params, timeout=timeout_seconds, headers={"User-Agent": "AmericanIdeaEvidence/1.3"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []

    leads: list[DiscoveryLead] = []
    seen: set[str] = set()
    for item in payload.get("articles") or []:
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title or url in seen or _is_same_source(url, article_url):
            continue
        host = _host(url)
        if not host:
            continue
        seen.add(url)
        leads.append(DiscoveryLead(provider="gdelt", kind="secondary", title=title[:300], url=url, source_name=str(item.get("domain") or host), published_at=str(item.get("seendate") or "") or None, query=query, note="Discovered through GDELT global news search. This is an unverified secondary lead, not corroboration by itself."))
        if len(leads) >= max_results:
            break
    return leads


def discover_official_domain(query: str, *, domain: str, max_results: int = 4, timeout_seconds: float = 8.0) -> list[DiscoveryLead]:
    """Use GDELT as an index to locate pages on an explicitly allowed official organization domain."""
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"
    scoped_query = f"({query}) domain:{domain}"
    params = {"query": scoped_query, "mode": "artlist", "format": "json", "maxrecords": max(1, min(max_results * 2, 20)), "timespan": "1year", "sort": "datedesc"}
    try:
        response = httpx.get(endpoint, params=params, timeout=timeout_seconds, headers={"User-Agent": "AmericanIdeaEvidence/1.3"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []

    leads: list[DiscoveryLead] = []
    seen: set[str] = set()
    for item in payload.get("articles") or []:
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title or url in seen or _host(url) != domain.removeprefix("www."):
            continue
        seen.add(url)
        leads.append(DiscoveryLead(provider="official_domain", kind="primary", title=title[:300], url=url, source_name=domain, published_at=str(item.get("seendate") or "") or None, query=query, note="Issuer-controlled primary source discovered on an official organization domain. It can verify what the organization reported, but is not independent corroboration of efficacy or outcome claims."))
        if len(leads) >= max_results:
            break
    return leads


def discover_clinical_trials(query: str, *, max_results: int = 6, timeout_seconds: float = 8.0) -> list[DiscoveryLead]:
    """Search ClinicalTrials.gov v2 for registered-study primary records."""
    endpoint = "https://clinicaltrials.gov/api/v2/studies"
    params = {"query.term": query, "pageSize": max(1, min(max_results, 20)), "format": "json"}
    try:
        response = httpx.get(endpoint, params=params, timeout=timeout_seconds, headers={"User-Agent": "AmericanIdeaEvidence/1.3"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []

    leads: list[DiscoveryLead] = []
    for study in payload.get("studies") or []:
        protocol = study.get("protocolSection") or {}
        ident = protocol.get("identificationModule") or {}
        status = protocol.get("statusModule") or {}
        sponsor = protocol.get("sponsorCollaboratorsModule") or {}
        nct_id = str(ident.get("nctId") or "").strip()
        title = str(ident.get("briefTitle") or ident.get("officialTitle") or "").strip()
        if not nct_id or not title:
            continue
        lead_sponsor = (sponsor.get("leadSponsor") or {}).get("name")
        leads.append(DiscoveryLead(provider="clinicaltrials_gov", kind="primary", title=title[:300], url=f"https://clinicaltrials.gov/study/{nct_id}", source_name=str(lead_sponsor or "ClinicalTrials.gov"), published_at=str(status.get("studyFirstPostDateStruct", {}).get("date") or "") or None, query=query, note="ClinicalTrials.gov registered-study record. Useful for study design, enrollment, endpoints, sponsor, and status; a registry record alone does not prove a reported efficacy result."))
        if len(leads) >= max_results:
            break
    return leads


def discover_federal_register(query: str, *, max_results: int = 6, timeout_seconds: float = 8.0) -> list[DiscoveryLead]:
    endpoint = "https://www.federalregister.gov/api/v1/documents.json"
    params = {"conditions[term]": query, "per_page": max(1, min(max_results, 20)), "order": "newest"}
    try:
        response = httpx.get(endpoint, params=params, timeout=timeout_seconds, headers={"User-Agent": "AmericanIdeaEvidence/1.3"})
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
        leads.append(DiscoveryLead(provider="federal_register", kind="primary", title=title[:300], url=url, source_name=", ".join(agency_names[:3]) or "Federal Register", published_at=str(item.get("publication_date") or "") or None, query=query, note="Official Federal Register result. It remains an evidence lead until fetched and compared with the claim."))
        if len(leads) >= max_results:
            break
    return leads


def discover_evidence_for_claim(claim_text: str, *, article_url: str | None = None, max_results: int = 12) -> dict:
    queries = build_discovery_queries(claim_text)
    leads: list[DiscoveryLead] = []
    seen_urls: set[str] = set()
    life_science = is_life_science_claim(claim_text)
    official_domains = official_domains_for_claim(claim_text) if life_science else []

    def add(items: list[DiscoveryLead]) -> None:
        for lead in items:
            if lead.url not in seen_urls:
                seen_urls.add(lead.url)
                leads.append(lead)

    for query in queries[:2]:
        if life_science:
            add(discover_clinical_trials(query, max_results=4))
            for domain in official_domains:
                add(discover_official_domain(query, domain=domain, max_results=3))
        else:
            add(discover_federal_register(query, max_results=4))
        add(discover_gdelt(query, article_url=article_url, max_results=6))
        if len(leads) >= max_results:
            break

    provider_rank = {"clinicaltrials_gov": 0, "federal_register": 0, "official_domain": 1, "gdelt": 2}
    leads.sort(key=lambda item: (0 if item.kind == "primary" else 1, provider_rank.get(item.provider, 9), item.title.lower()))
    leads = leads[:max_results]

    return {
        "claim_text": claim_text,
        "queries": queries,
        "domain": "life_science" if life_science else "general",
        "providers_used": sorted({lead.provider for lead in leads}),
        "leads": [lead.to_dict() for lead in leads],
        "lead_count": len(leads),
        "methodology_note": (
            "Evidence Discovery routes recognized life-science claims toward ClinicalTrials.gov and relevant official organization domains before general news discovery. "
            "Registry records verify registered study facts; issuer-controlled pages verify what an organization reported; neither is treated as independent proof of efficacy. "
            "All discovery results remain leads until fetched, fingerprinted, and compared with the claim."
        ),
    }
