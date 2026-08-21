import re
from dataclasses import dataclass, asdict
from urllib.parse import urlparse

import httpx

from .source_intelligence import source_profile_for_claim

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
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max(1, min(max_results * 2, 30)),
        "timespan": "3months",
        "sort": "datedesc",
    }
    try:
        response = httpx.get(endpoint, params=params, timeout=timeout_seconds, headers={"User-Agent": "AmericanIdeaEvidence/1.4"})
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
        leads.append(
            DiscoveryLead(
                provider="gdelt",
                kind="secondary",
                title=title[:300],
                url=url,
                source_name=str(item.get("domain") or host),
                published_at=str(item.get("seendate") or "") or None,
                query=query,
                note="Independent-coverage discovery lead from GDELT. Search position and outlet reputation are not treated as evidence of truth.",
            )
        )
        if len(leads) >= max_results:
            break
    return leads


def discover_official_domain(query: str, *, domain: str, max_results: int = 4, timeout_seconds: float = 8.0) -> list[DiscoveryLead]:
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"
    scoped_query = f"({query}) domain:{domain}"
    params = {
        "query": scoped_query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max(1, min(max_results * 2, 20)),
        "timespan": "1year",
        "sort": "datedesc",
    }
    try:
        response = httpx.get(endpoint, params=params, timeout=timeout_seconds, headers={"User-Agent": "AmericanIdeaEvidence/1.4"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []

    leads: list[DiscoveryLead] = []
    seen: set[str] = set()
    expected = domain.removeprefix("www.")
    for item in payload.get("articles") or []:
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title or url in seen or _host(url) != expected:
            continue
        seen.add(url)
        leads.append(
            DiscoveryLead(
                provider="official_domain",
                kind="primary",
                title=title[:300],
                url=url,
                source_name=domain,
                published_at=str(item.get("seendate") or "") or None,
                query=query,
                note=(
                    f"Discovered on the official or entity-controlled domain {domain}. This is primary evidence for what that "
                    "organization publishes, but is not automatically independent corroboration of the underlying claim."
                ),
            )
        )
        if len(leads) >= max_results:
            break
    return leads


def discover_pubmed(query: str, *, max_results: int = 6, timeout_seconds: float = 8.0) -> list[DiscoveryLead]:
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    headers = {"User-Agent": "AmericanIdeaEvidence/1.4"}
    try:
        search = httpx.get(
            search_url,
            params={"db": "pubmed", "term": query, "retmode": "json", "retmax": max(1, min(max_results, 20)), "sort": "relevance"},
            timeout=timeout_seconds,
            headers=headers,
        )
        search.raise_for_status()
        ids = [str(value) for value in (search.json().get("esearchresult", {}).get("idlist") or []) if str(value).isdigit()]
        if not ids:
            return []
        summary = httpx.get(
            summary_url,
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            timeout=timeout_seconds,
            headers=headers,
        )
        summary.raise_for_status()
        payload = summary.json().get("result") or {}
    except (httpx.HTTPError, ValueError):
        return []

    leads: list[DiscoveryLead] = []
    for pmid in ids:
        item = payload.get(pmid) or {}
        title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
        if not title:
            continue
        pubdate = str(item.get("pubdate") or "").strip() or None
        source = str(item.get("source") or "PubMed").strip() or "PubMed"
        leads.append(
            DiscoveryLead(
                provider="pubmed",
                kind="secondary",
                title=title[:300],
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                source_name=source,
                published_at=pubdate,
                query=query,
                note=(
                    "PubMed-indexed research lead. Indexing identifies a scientific publication; the article must still be fetched "
                    "or otherwise inspected and compared with the exact claim before it can affect claim status."
                ),
            )
        )
        if len(leads) >= max_results:
            break
    return leads


def discover_clinical_trials(query: str, *, max_results: int = 6, timeout_seconds: float = 8.0) -> list[DiscoveryLead]:
    endpoint = "https://clinicaltrials.gov/api/v2/studies"
    params = {"query.term": query, "pageSize": max(1, min(max_results, 20)), "format": "json"}
    try:
        response = httpx.get(endpoint, params=params, timeout=timeout_seconds, headers={"User-Agent": "AmericanIdeaEvidence/1.4"})
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
        leads.append(
            DiscoveryLead(
                provider="clinicaltrials_gov",
                kind="primary",
                title=title[:300],
                url=f"https://clinicaltrials.gov/study/{nct_id}",
                source_name=str(lead_sponsor or "ClinicalTrials.gov"),
                published_at=str(status.get("studyFirstPostDateStruct", {}).get("date") or "") or None,
                query=query,
                note=(
                    "ClinicalTrials.gov registered-study record. Useful for study design, enrollment, endpoints, sponsor, status, "
                    "and submitted results when present; registration alone does not prove efficacy."
                ),
            )
        )
        if len(leads) >= max_results:
            break
    return leads


def discover_federal_register(query: str, *, max_results: int = 6, timeout_seconds: float = 8.0) -> list[DiscoveryLead]:
    endpoint = "https://www.federalregister.gov/api/v1/documents.json"
    params = {"conditions[term]": query, "per_page": max(1, min(max_results, 20)), "order": "newest"}
    try:
        response = httpx.get(endpoint, params=params, timeout=timeout_seconds, headers={"User-Agent": "AmericanIdeaEvidence/1.4"})
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
                note="Official Federal Register result. It remains an evidence lead until fetched and compared with the claim.",
            )
        )
        if len(leads) >= max_results:
            break
    return leads


def discover_evidence_for_claim(claim_text: str, *, article_url: str | None = None, max_results: int = 12) -> dict:
    queries = build_discovery_queries(claim_text)
    profile = source_profile_for_claim(claim_text)
    leads: list[DiscoveryLead] = []
    seen_urls: set[str] = set()
    diagnostics: dict[str, dict] = {}

    def record(provider: str, attempted: bool, items: list[DiscoveryLead] | None = None, note: str | None = None) -> None:
        count = len(items or [])
        diagnostics[provider] = {
            "attempted": attempted,
            "result_count": count,
            "status": "results" if count else ("no_results_or_unavailable" if attempted else "not_routed"),
            "note": note,
        }

    def add(items: list[DiscoveryLead]) -> None:
        for lead in items:
            if lead.url and lead.url not in seen_urls:
                seen_urls.add(lead.url)
                leads.append(lead)

    aggregate_counts = {"clinicaltrials_gov": 0, "pubmed": 0, "federal_register": 0, "official_domain": 0, "gdelt": 0}
    attempted = {key: False for key in aggregate_counts}

    for query in queries[:2]:
        if profile.use_clinical_trials:
            attempted["clinicaltrials_gov"] = True
            items = discover_clinical_trials(query, max_results=4)
            aggregate_counts["clinicaltrials_gov"] += len(items)
            add(items)
        if profile.use_pubmed:
            attempted["pubmed"] = True
            items = discover_pubmed(query, max_results=5)
            aggregate_counts["pubmed"] += len(items)
            add(items)
        if profile.use_federal_register:
            attempted["federal_register"] = True
            items = discover_federal_register(query, max_results=4)
            aggregate_counts["federal_register"] += len(items)
            add(items)
        if profile.official_domains:
            attempted["official_domain"] = True
        for domain in profile.official_domains[:5]:
            items = discover_official_domain(query, domain=domain, max_results=2)
            aggregate_counts["official_domain"] += len(items)
            add(items)
        attempted["gdelt"] = True
        items = discover_gdelt(query, article_url=article_url, max_results=7)
        aggregate_counts["gdelt"] += len(items)
        add(items)
        if len(leads) >= max_results * 2:
            break

    for provider, was_attempted in attempted.items():
        synthetic = [None] * aggregate_counts[provider]
        record(provider, was_attempted, synthetic, "Provider diagnostics report discovery output before URL deduplication.")

    provider_rank = {"clinicaltrials_gov": 0, "federal_register": 0, "official_domain": 1, "pubmed": 2, "gdelt": 3}
    leads.sort(key=lambda item: (0 if item.kind == "primary" else 1, provider_rank.get(item.provider, 9), item.title.lower()))
    leads = leads[:max_results]

    return {
        "claim_text": claim_text,
        "domain_profile": profile.name,
        "queries": queries,
        "official_domains": list(profile.official_domains),
        "providers_used": sorted({lead.provider for lead in leads}),
        "provider_diagnostics": diagnostics,
        "leads": [lead.to_dict() for lead in leads],
        "lead_count": len(leads),
        "methodology_note": (
            "Evidence Discovery combines direct public-data adapters with broad independent discovery. Provider diagnostics reveal which "
            "source systems were routed and whether they produced candidate leads. All results remain unverified until fetched or otherwise "
            "inspected, fingerprinted when possible, compared with the exact claim, and passed through the Trust Gate."
        ),
    }
