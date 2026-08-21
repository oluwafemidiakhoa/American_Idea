from .evidence_discovery import (
    discover_clinical_trials,
    discover_federal_register,
    discover_gdelt,
    discover_official_domain,
    discover_pubmed,
)
from .provider_query_planner import build_provider_query_plan
from .source_intelligence import source_profile_for_claim


def discover_with_provider_plans(
    claim_text: str,
    *,
    retrieval_anchors: list[str] | None = None,
    article_url: str | None = None,
    max_results: int = 12,
) -> dict:
    profile = source_profile_for_claim(claim_text + " " + " ".join(retrieval_anchors or []))
    plans = build_provider_query_plan(
        claim_text,
        profile_name=profile.name,
        retrieval_anchors=retrieval_anchors or [],
        max_queries=3,
    )

    leads = []
    seen_urls: set[str] = set()
    diagnostics: dict[str, dict] = {}

    def add(items):
        for lead in items:
            if lead.url and lead.url not in seen_urls:
                seen_urls.add(lead.url)
                leads.append(lead)

    def run(provider: str, routed: bool, runner) -> None:
        queries = [query for query in plans.get(provider, []) if query]
        if not routed:
            diagnostics[provider] = {
                "attempted": False,
                "status": "not_routed",
                "result_count": 0,
                "queries": queries,
            }
            return

        count = 0
        attempted_queries = []
        for query in queries[:3]:
            attempted_queries.append(query)
            items = runner(query)
            count += len(items)
            add(items)
            if len(leads) >= max_results * 2:
                break
        diagnostics[provider] = {
            "attempted": True,
            "status": "results" if count else "no_results",
            "result_count": count,
            "queries": attempted_queries,
        }

    run(
        "clinicaltrials_gov",
        profile.use_clinical_trials,
        lambda query: discover_clinical_trials(query, max_results=4),
    )
    run(
        "pubmed",
        profile.use_pubmed,
        lambda query: discover_pubmed(query, max_results=5),
    )
    run(
        "federal_register",
        profile.use_federal_register,
        lambda query: discover_federal_register(query, max_results=4),
    )

    official_queries = [query for query in plans.get("official_domain", []) if query]
    official_count = 0
    attempted_official = bool(profile.official_domains)
    attempted_pairs = []
    if attempted_official:
        for domain in profile.official_domains[:6]:
            for query in official_queries[:2]:
                attempted_pairs.append({"domain": domain, "query": query})
                items = discover_official_domain(query, domain=domain, max_results=2)
                official_count += len(items)
                add(items)
                if len(leads) >= max_results * 2:
                    break
            if len(leads) >= max_results * 2:
                break
    diagnostics["official_domain"] = {
        "attempted": attempted_official,
        "status": "results" if official_count else ("no_results" if attempted_official else "not_routed"),
        "result_count": official_count,
        "queries": attempted_pairs,
    }

    run(
        "gdelt",
        True,
        lambda query: discover_gdelt(query, article_url=article_url, max_results=7),
    )

    provider_rank = {
        "clinicaltrials_gov": 0,
        "federal_register": 0,
        "official_domain": 1,
        "pubmed": 2,
        "gdelt": 3,
    }
    leads.sort(
        key=lambda item: (
            0 if item.kind == "primary" else 1,
            provider_rank.get(item.provider, 9),
            item.title.lower(),
        )
    )
    leads = leads[:max_results]

    flat_queries = []
    for provider, values in plans.items():
        for query in values:
            if query and query not in flat_queries:
                flat_queries.append(query)

    return {
        "claim_text": claim_text,
        "domain_profile": profile.name,
        "queries": flat_queries,
        "provider_query_plan": plans,
        "official_domains": list(profile.official_domains),
        "providers_used": sorted({lead.provider for lead in leads}),
        "provider_diagnostics": diagnostics,
        "leads": [lead.to_dict() for lead in leads],
        "lead_count": len(leads),
        "methodology_note": (
            "Each discovery provider receives a compact provider-specific query plan derived from stable entities, identifiers, "
            "and domain terms. Search context helps locate candidates but never counts as evidence."
        ),
    }
