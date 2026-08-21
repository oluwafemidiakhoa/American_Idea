from collections import Counter
from urllib.parse import urlparse

from .discovery_store import save_discovery_leads
from .evidence_discovery import discover_evidence_for_claim
from .evidence_verifier import verify_claim_evidence
from .ledger import get_record, save_verification
from .retrieval_anchors import build_anchor_query, extract_retrieval_anchors


def _host(url: str | None) -> str:
    if not url:
        return ""
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _lead_identity(item: dict) -> tuple[str, str]:
    return (str(item.get("url") or "").strip(), str(item.get("label") or "").strip())


def _discovery_context(record: dict, claim_id: str) -> dict:
    claims = record.get("claims", [])
    index = next((i for i, item in enumerate(claims) if item.get("id") == claim_id), None)
    parts: list[str] = []

    title = str(record.get("title") or "").strip()
    if title:
        parts.append(f"Story title: {title[:220]}")
    source_name = str(record.get("source_name") or "").strip()
    if source_name:
        parts.append(f"Story source: {source_name[:80]}")

    if index is not None:
        for neighbour_index in (index - 1, index + 1):
            if 0 <= neighbour_index < len(claims):
                text = str(claims[neighbour_index].get("text") or "").strip()
                if text:
                    parts.append(f"Nearby claim: {text[:260]}")

    return {"text": " ".join(parts), "components": parts}


def _matrix(claim: dict) -> dict:
    evidence = claim.get("evidence", [])
    relations = Counter(str(item.get("relation") or "unverified_lead") for item in evidence)
    fetch_states = Counter(str(item.get("fetch_status") or "not_fetched") for item in evidence)
    verified = [item for item in evidence if item.get("fetch_status") == "verified"]
    verified_hosts = sorted({_host(item.get("url")) for item in verified if _host(item.get("url"))})
    primary_verified = [item for item in verified if item.get("kind") == "primary"]
    secondary_verified = [item for item in verified if item.get("kind") == "secondary"]
    strongest_support = max((float(item.get("verification_confidence") or 0) for item in verified if item.get("relation") == "supports"), default=0.0)
    strongest_contradiction = max((float(item.get("verification_confidence") or 0) for item in verified if item.get("relation") == "contradicts"), default=0.0)

    return {
        "claim_id": claim.get("id"),
        "status": claim.get("status", "unresolved"),
        "status_basis": claim.get("status_basis"),
        "evidence_total": len(evidence),
        "verified_source_count": len(verified_hosts),
        "verified_primary_count": len(primary_verified),
        "verified_secondary_count": len(secondary_verified),
        "relations": dict(sorted(relations.items())),
        "fetch_states": dict(sorted(fetch_states.items())),
        "strongest_support": round(strongest_support, 4),
        "strongest_contradiction": round(strongest_contradiction, 4),
        "blocked_or_failed_count": fetch_states.get("fetch_failed", 0),
        "unverified_lead_count": relations.get("unverified_lead", 0),
        "trust_gate": claim.get("trust_gate"),
    }


def autonomously_verify_claim(*, record_id: str, claim_id: str, discovery_limit: int = 12, fetch_limit: int = 8) -> dict:
    record = get_record(record_id)
    if record is None:
        raise ValueError("Evidence record was not found.")

    claim = next((item for item in record.get("claims", []) if item.get("id") == claim_id), None)
    if claim is None:
        raise ValueError("Claim was not found in this evidence record.")

    exact_claim_text = str(claim.get("text") or "").strip()
    context = _discovery_context(record, claim_id)
    anchors = extract_retrieval_anchors(exact_claim_text, context["text"])
    anchor_query = build_anchor_query(exact_claim_text, context["text"])

    # Retrieval starts with stable entities/identifiers when available, then includes the exact claim
    # and inspectable context. Verification still uses only the exact stored claim.
    discovery_parts = [part for part in (anchor_query, exact_claim_text, context["text"]) if part]
    discovery_text = " ".join(discovery_parts)

    existing_evidence = list(claim.get("evidence", []))
    existing_urls = {str(item.get("url") or "").strip() for item in existing_evidence if item.get("url")}
    failed_urls = {
        str(item.get("url") or "").strip()
        for item in existing_evidence
        if item.get("fetch_status") == "fetch_failed" and item.get("url")
    }

    discovery = discover_evidence_for_claim(
        discovery_text,
        article_url=record.get("article_url"),
        max_results=discovery_limit,
    )
    new_leads = [
        lead for lead in discovery.get("leads", [])
        if str(lead.get("url") or "").strip()
        and str(lead.get("url") or "").strip() not in existing_urls
        and str(lead.get("url") or "").strip() not in failed_urls
    ]
    if new_leads:
        save_discovery_leads(record_id=record_id, claim_id=claim_id, leads=new_leads)

    refreshed = get_record(record_id)
    if refreshed is None:
        raise RuntimeError("Evidence record disappeared during verification.")
    refreshed_claim = next((item for item in refreshed.get("claims", []) if item.get("id") == claim_id), None)
    if refreshed_claim is None:
        raise RuntimeError("Claim disappeared during verification.")

    verification_claim = dict(refreshed_claim)
    verification_claim["text"] = exact_claim_text
    verification_claim["evidence"] = [
        dict(item) for item in refreshed_claim.get("evidence", [])
        if item.get("fetch_status") != "fetch_failed"
    ]

    verified_claims, fetched_source_count, verified_evidence_count = verify_claim_evidence(
        [verification_claim],
        max_fetches=max(1, min(fetch_limit, 12)),
    )
    verified_claim = verified_claims[0]

    verified_identities = {_lead_identity(item) for item in verified_claim.get("evidence", [])}
    for item in refreshed_claim.get("evidence", []):
        if item.get("fetch_status") == "fetch_failed" and _lead_identity(item) not in verified_identities:
            verified_claim.setdefault("evidence", []).append(item)

    revision_count = save_verification(
        article_url=record.get("article_url") or "",
        claims=[verified_claim],
        methodology_version="1.5.0",
    )

    updated_record = get_record(record_id)
    updated_claim = next(
        (item for item in (updated_record or {}).get("claims", []) if item.get("id") == claim_id),
        dict(verified_claim),
    )
    updated_claim["trust_gate"] = verified_claim.get("trust_gate")

    return {
        "record_id": record_id,
        "claim_id": claim_id,
        "domain_profile": discovery.get("domain_profile", "general"),
        "queries": discovery.get("queries", []),
        "retrieval_anchors": anchors,
        "discovery_context": context["components"],
        "providers_used": discovery.get("providers_used", []),
        "provider_diagnostics": discovery.get("provider_diagnostics", {}),
        "new_discovered_lead_count": len(new_leads),
        "fetched_source_count": fetched_source_count,
        "verified_evidence_count": verified_evidence_count,
        "revision_count": revision_count,
        "claim": updated_claim,
        "evidence_matrix": _matrix(updated_claim),
        "methodology_note": (
            "Autonomous verification uses stable retrieval anchors plus inspectable saved-story context to find evidence, but fetched pages "
            "are compared only against the exact stored claim. Retrieval anchors, context, provider rank, and search position never count "
            "as evidence and cannot bypass the Trust Gate."
        ),
    }
