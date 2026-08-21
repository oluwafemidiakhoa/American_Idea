import hashlib
from urllib.parse import urlparse

PRIMARY_SOURCE_TYPES = {"government", "court", "academic", "official_record", "dataset"}


def _evidence_id(claim_id: str, url: str | None, label: str) -> str:
    raw = f"{claim_id}|{url or ''}|{label.strip()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"evidence_{digest}"


def _valid_public_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def assess_evidence_candidate(
    *,
    claim_id: str,
    label: str,
    url: str | None,
    kind: str,
    relation: str,
    source_type: str,
    directness: float,
    independence: float,
    has_capture_hash: bool,
    note: str | None = None,
) -> dict:
    """Score evidence quality only. This function does not decide whether a claim is true."""
    score = 0.0
    warnings: list[str] = []
    reasons: list[str] = []

    if _valid_public_url(url):
        score += 0.15
        reasons.append("has a resolvable source URL")
    else:
        warnings.append("evidence has no valid public URL")

    if source_type in PRIMARY_SOURCE_TYPES or kind == "primary":
        score += 0.25
        reasons.append("identified as a primary or authoritative source type")

    score += max(0.0, min(directness, 1.0)) * 0.25
    reasons.append("directness contributes to evidence quality")

    score += max(0.0, min(independence, 1.0)) * 0.20
    reasons.append("source independence contributes to evidence quality")

    if has_capture_hash:
        score += 0.15
        reasons.append("captured content has a cryptographic fingerprint")
    else:
        warnings.append("source content has not yet been cryptographically fingerprinted")

    if relation == "mentions":
        score = min(score, 0.60)
        warnings.append("a mention alone is weak evidence for or against a claim")

    score = round(min(score, 1.0), 2)

    return {
        "evidence_id": _evidence_id(claim_id, url, label),
        "claim_id": claim_id,
        "label": label.strip(),
        "url": url,
        "kind": kind,
        "relation": relation,
        "source_type": source_type,
        "quality_score": score,
        "quality_reasons": reasons,
        "warnings": warnings,
        "review_required": True,
        "claim_status": "unresolved",
        "note": note,
        "methodology_note": (
            "Evidence quality is not claim truth. This score measures provenance, source type, "
            "directness, independence, and capture integrity. A consequential claim remains "
            "unresolved until evidence is reviewed in context."
        ),
    }
