from fastapi import APIRouter, HTTPException

from .services.autonomous_verification import autonomously_verify_claim
from .services.ledger import enabled as ledger_enabled

router = APIRouter(prefix="/api", tags=["autonomous-verification"])


@router.post("/records/{record_id}/claims/{claim_id}/auto-verify")
def auto_verify_claim(record_id: str, claim_id: str):
    if not ledger_enabled():
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is required for autonomous verification.")

    try:
        return autonomously_verify_claim(
            record_id=record_id,
            claim_id=claim_id,
            discovery_limit=12,
            fetch_limit=8,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Autonomous evidence verification is temporarily unavailable.") from exc
