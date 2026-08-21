from fastapi import APIRouter, HTTPException

from .services.discovery_store import save_discovery_leads
from .services.evidence_discovery import discover_evidence_for_claim
from .services.ledger import enabled as ledger_enabled
from .services.ledger import get_record

router = APIRouter(prefix="/api", tags=["evidence-discovery"])


@router.post("/records/{record_id}/claims/{claim_id}/discover-evidence")
def discover_claim_evidence(record_id: str, claim_id: str):
    if not ledger_enabled():
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is required for evidence discovery.")

    try:
        record = get_record(record_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is temporarily unavailable.") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence record was not found.")

    claim = next((item for item in record.get("claims", []) if item.get("id") == claim_id), None)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim was not found in this evidence record.")

    discovery = discover_evidence_for_claim(
        claim.get("text", ""),
        article_url=record.get("article_url"),
        max_results=12,
    )

    try:
        stored = save_discovery_leads(
            record_id=record_id,
            claim_id=claim_id,
            leads=discovery.get("leads", []),
        )
        updated = get_record(record_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Discovered evidence could not be persisted.") from exc

    return {
        "record_id": record_id,
        "claim_id": claim_id,
        "queries": discovery.get("queries", []),
        "discovered_lead_count": discovery.get("lead_count", 0),
        "stored_lead_count": stored,
        "leads": discovery.get("leads", []),
        "record": updated,
        "methodology_note": discovery.get("methodology_note"),
    }
