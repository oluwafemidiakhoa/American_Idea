from urllib.parse import urlparse

RESOLVED_STATUSES = {"supported", "partially_supported", "contested", "unsupported"}


def _host(url: str | None) -> str:
    if not url:
        return ""
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _aggregate_atomic_status(claim: dict) -> str:
    atoms = list(claim.get("atomic_claims") or [])
    if not atoms:
        return claim.get("status", "unresolved")
    statuses = [str(atom.get("status") or "unresolved") for atom in atoms]
    resolved = {status for status in statuses if status != "unresolved"}
    if any(status == "unresolved" for status in statuses):
        return "unresolved"
    if len(resolved) == 1:
        return next(iter(resolved))
    return "mixed"


def evaluate_claim_trust(claim: dict) -> dict:
    evidence = claim.get("evidence", []) or []
    verified = [item for item in evidence if item.get("fetch_status") == "verified"]
    failed = [item for item in evidence if item.get("fetch_status") == "fetch_failed"]
    primary = [item for item in verified if item.get("kind") == "primary"]
    secondary = [item for item in verified if item.get("kind") == "secondary"]
    supports = [
        item for item in verified
        if item.get("relation") == "supports" and float(item.get("verification_confidence") or 0) >= 0.78
    ]
    contradicts = [
        item for item in verified
        if item.get("relation") == "contradicts" and float(item.get("verification_confidence") or 0) >= 0.80
    ]

    verified_hosts = {_host(item.get("url")) for item in verified if _host(item.get("url"))}
    support_hosts = {_host(item.get("url")) for item in supports if _host(item.get("url"))}
    contradict_hosts = {_host(item.get("url")) for item in contradicts if _host(item.get("url"))}

    proposed_status = claim.get("status", "unresolved")
    issues: list[str] = []

    atoms = list(claim.get("atomic_claims") or [])
    atomic_status = _aggregate_atomic_status(claim)
    unresolved_atoms = [atom for atom in atoms if atom.get("status", "unresolved") == "unresolved"]
    if atoms and proposed_status in RESOLVED_STATUSES and unresolved_atoms:
        issues.append(
            f"Atomic Claim Provenance blocks parent resolution while {len(unresolved_atoms)} of {len(atoms)} material propositions remain unresolved."
        )

    if proposed_status == "supported":
        if not primary:
            issues.append("Supported status requires at least one verified primary source.")
        if len(support_hosts) < 2:
            issues.append("Supported status requires supporting evidence from at least two independent source hosts.")
        if not any(float(item.get("verification_confidence") or 0) >= 0.84 for item in primary if item.get("relation") == "supports"):
            issues.append("Supported status requires a high-confidence primary-source match.")
        if contradicts:
            issues.append("Strong contradictory evidence is present; status cannot remain simply supported.")

    elif proposed_status == "partially_supported":
        strong_primary = [
            item for item in primary
            if item.get("relation") == "supports" and float(item.get("verification_confidence") or 0) >= 0.86
        ]
        if not strong_primary and len(support_hosts) < 2:
            issues.append("Partially supported requires either a strong verified primary source or two independent strong supporting sources.")
        if contradicts:
            issues.append("Strong contradictory evidence is present; status should be contested rather than partially supported.")

    elif proposed_status == "unsupported":
        primary_contradict = [
            item for item in primary
            if item.get("relation") == "contradicts" and float(item.get("verification_confidence") or 0) >= 0.86
        ]
        if not primary_contradict:
            issues.append("Unsupported status requires a high-confidence verified primary source that contradicts the claim.")
        if len(contradict_hosts) < 2:
            issues.append("Unsupported status requires contradiction from at least two independent source hosts.")
        if supports:
            issues.append("Strong supporting evidence is also present; status should be contested rather than unsupported.")

    elif proposed_status == "contested":
        if not supports or not contradicts:
            issues.append("Contested status requires both strong supporting and strong contradicting evidence.")

    elif proposed_status == "unresolved":
        if not verified:
            issues.append("No evidence source has been successfully fetched and verified yet.")
        elif not supports and not contradicts:
            issues.append("Fetched sources do not yet provide strong support or contradiction.")

    requirements_met = not issues if proposed_status in RESOLVED_STATUSES else True
    public_status = proposed_status if requirements_met else "unresolved"

    if public_status == "unresolved" and proposed_status in RESOLVED_STATUSES:
        basis = "Trust Gate blocked the proposed status because its evidence requirements were not met."
    else:
        basis = "Trust Gate requirements are satisfied for the current public status." if requirements_met else "Claim remains unresolved."

    return {
        "passed": requirements_met,
        "proposed_status": proposed_status,
        "public_status": public_status,
        "aggregate_atomic_status": atomic_status,
        "atomic_claim_count": len(atoms),
        "unresolved_atomic_count": len(unresolved_atoms),
        "verified_source_count": len(verified),
        "verified_primary_count": len(primary),
        "verified_secondary_count": len(secondary),
        "independent_verified_hosts": len(verified_hosts),
        "strong_support_count": len(supports),
        "strong_contradiction_count": len(contradicts),
        "failed_or_blocked_count": len(failed),
        "issues": issues,
        "basis": basis,
        "methodology_version": "trust-gate-2.0-atomic",
    }


def enforce_claim_trust(claim: dict) -> dict:
    claim["aggregate_status"] = _aggregate_atomic_status(claim)
    audit = evaluate_claim_trust(claim)
    claim["trust_gate"] = audit
    if audit["public_status"] != claim.get("status", "unresolved"):
        claim["status"] = audit["public_status"]
        claim["status_basis"] = audit["basis"] + " " + " ".join(audit["issues"])
    return claim
