from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .autonomous_routes import router as autonomous_router
from .discovery_routes import router as discovery_router
from .models import (
    AnalyzeRequest,
    AnalysisResponse,
    CompareCoverageRequest,
    CompareCoverageResponse,
    IngestUrlRequest,
    IngestUrlResponse,
    VerifyEvidenceRequest,
    VerifyEvidenceResponse,
)
from .services.atomic_ledger import hydrate_atomic_claims, init_atomic_ledger, save_atomic_claims
from .services.claim_extractor import extract_candidate_claims
from .services.coverage_compare import compare_records
from .services.evidence_engine import attach_source_link_evidence
from .services.evidence_verifier import verify_claim_evidence
from .services.ledger import enabled as ledger_enabled
from .services.ledger import get_record, init_ledger, save_story_analysis, save_verification
from .services.story_timeline import get_timeline, init_timeline, latest_record_for_url, record_observation
from .services.url_ingestor import IngestionError, ingest_article_url

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
PUBLIC_STORYLENS_URL = "https://oluwafemidiakhoa.github.io/American_Idea/"

app = FastAPI(
    title="American Idea Evidence API",
    version="2.0.0",
    description=(
        "Evidence-first news analysis with Atomic Claim Provenance, evidence contracts, direct public-data adapters, "
        "domain-aware discovery, an auditable Trust Gate, a persistent Claim Ledger, Compare Coverage, and Story Timeline."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://oluwafemidiakhoa.github.io",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(discovery_router)
app.include_router(autonomous_router)


@app.on_event("startup")
def startup() -> None:
    if ledger_enabled():
        try:
            init_ledger()
            init_timeline()
            init_atomic_ledger()
        except Exception as exc:
            print(f"American Idea persistence initialization failed: {exc}")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(PUBLIC_STORYLENS_URL, status_code=307)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "american-idea-evidence",
        "version": "2.0.0",
        "ledger_configured": ledger_enabled(),
        "story_timeline": True,
        "evidence_discovery": True,
        "autonomous_verification": True,
        "trust_gate": True,
        "provider_diagnostics": True,
        "atomic_claim_provenance": True,
        "evidence_contracts": True,
        "record_scoped_atomic_ledger": True,
        "source_profiles": [
            "general",
            "life_science",
            "geopolitics_conflict",
            "finance_business",
            "government_policy",
            "legal_courts",
            "elections",
            "science_environment",
        ],
        "discovery_providers": ["clinicaltrials_gov", "pubmed", "federal_register", "official_domain", "gdelt"],
    }


@app.get("/api/records/{record_id}")
def record(record_id: str):
    if not ledger_enabled():
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is not configured.")
    try:
        data = hydrate_atomic_claims(get_record(record_id))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is temporarily unavailable.") from exc
    if data is None:
        raise HTTPException(status_code=404, detail="Evidence record was not found.")
    return data


@app.get("/api/records/{record_id}/timeline")
def record_timeline(record_id: str):
    if not ledger_enabled():
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is not configured.")
    try:
        data = get_timeline(record_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Story Timeline is temporarily unavailable.") from exc
    if data is None:
        raise HTTPException(status_code=404, detail="Evidence record was not found.")
    return data


@app.post("/api/records/{record_id}/refresh")
def refresh_record(record_id: str):
    if not ledger_enabled():
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is required for Story Timeline refresh.")
    try:
        seed = get_record(record_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is temporarily unavailable.") from exc
    if seed is None:
        raise HTTPException(status_code=404, detail="Evidence record was not found.")

    try:
        previous = latest_record_for_url(seed["article_url"])
        article = ingest_article_url(seed["article_url"])
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Story refresh is temporarily unavailable.") from exc

    claims = attach_source_link_evidence(extract_candidate_claims(article.text), article.blocks, article.final_url)
    changed = previous is None or previous.get("content_sha256") != article.content_sha256

    try:
        new_record_id = save_story_analysis(article=article, claims=claims)
        if new_record_id:
            save_atomic_claims(record_id=new_record_id, claims=claims)
        record_observation(
            record_id=new_record_id,
            article_url=article.final_url,
            content_sha256=article.content_sha256,
            changed=changed,
            text=article.text,
        )
        timeline = get_timeline(new_record_id or record_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Story Timeline persistence is temporarily unavailable.") from exc

    return {
        "changed": changed,
        "previous_record_id": previous.get("public_id") if previous else None,
        "record_id": new_record_id or record_id,
        "content_sha256": article.content_sha256,
        "title": article.title,
        "article_url": article.final_url,
        "timeline": timeline,
        "methodology_note": (
            "Refresh re-fetches the same public URL and compares the extracted article fingerprint with the latest saved snapshot. "
            "Atomic Claim Provenance is recompiled and stored per immutable story snapshot."
        ),
    }


@app.post("/api/compare-coverage", response_model=CompareCoverageResponse)
def compare_coverage(payload: CompareCoverageRequest):
    if not ledger_enabled():
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is required for saved-record comparison.")
    unique_ids = list(dict.fromkeys(record_id.strip() for record_id in payload.record_ids if record_id.strip()))
    if len(unique_ids) < 2:
        raise HTTPException(status_code=422, detail="Provide at least two different saved record IDs.")

    records = []
    missing = []
    try:
        for record_id in unique_ids:
            data = hydrate_atomic_claims(get_record(record_id))
            if data is None:
                missing.append(record_id)
            else:
                records.append(data)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is temporarily unavailable.") from exc

    if missing:
        raise HTTPException(status_code=404, detail={"message": "One or more saved records were not found.", "record_ids": missing})
    try:
        return compare_records(records)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze(payload: AnalyzeRequest):
    claims = extract_candidate_claims(payload.article_text)
    return AnalysisResponse(
        record_id=f"ai_{uuid4().hex[:16]}",
        source_name=payload.source_name,
        article_url=str(payload.article_url) if payload.article_url else None,
        claims=claims,
        factual_claim_count=len(claims),
        methodology_note=(
            "Candidate newsroom sentences are extracted using transparent heuristics and compiled into atomic propositions. "
            "Extraction confidence estimates external verifiability; it is not a truth score."
        ),
    )


@app.post("/api/ingest-url", response_model=IngestUrlResponse)
def ingest_url(payload: IngestUrlRequest):
    try:
        article = ingest_article_url(str(payload.article_url))
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    claims = attach_source_link_evidence(extract_candidate_claims(article.text), article.blocks, article.final_url)
    evidence_link_count = sum(len(claim.get("evidence", [])) for claim in claims)
    claims_with_evidence = sum(1 for claim in claims if claim.get("evidence"))
    record_id = f"ai_{uuid4().hex[:16]}"
    persisted = False
    if ledger_enabled():
        try:
            previous = latest_record_for_url(article.final_url)
            stored_id = save_story_analysis(article=article, claims=claims)
            if stored_id:
                save_atomic_claims(record_id=stored_id, claims=claims)
                record_id = stored_id
                persisted = True
                record_observation(
                    record_id=stored_id,
                    article_url=article.final_url,
                    content_sha256=article.content_sha256,
                    changed=previous is None or previous.get("content_sha256") != article.content_sha256,
                    text=article.text,
                )
        except Exception as exc:
            print(f"American Idea ledger write failed: {exc}")

    return IngestUrlResponse(
        record_id=record_id,
        source_name=article.source_name,
        article_url=article.final_url,
        requested_url=article.requested_url,
        final_url=article.final_url,
        title=article.title,
        content_sha256=article.content_sha256,
        extracted_text_length=len(article.text),
        snapshot_status="persisted" if persisted else "fingerprinted_not_persisted",
        ledger_persisted=persisted,
        claims=claims,
        factual_claim_count=len(claims),
        evidence_link_count=evidence_link_count,
        claims_with_evidence=claims_with_evidence,
        methodology_note=(
            "American Idea fetched and fingerprinted the article, extracted candidate newsroom sentences, compiled each into atomic "
            "propositions with explicit evidence contracts, attached source-linked leads, and persisted the decomposition per story snapshot."
        ),
    )


@app.post("/api/verify-evidence", response_model=VerifyEvidenceResponse)
def verify_evidence(payload: VerifyEvidenceRequest):
    claims_input = [claim.model_dump() for claim in payload.claims]
    claims, fetched_source_count, verified_evidence_count = verify_claim_evidence(claims_input, max_fetches=payload.max_fetches)
    persisted = False
    revision_count = 0
    if ledger_enabled():
        try:
            revision_count = save_verification(
                article_url=str(payload.article_url), claims=claims, methodology_version="2.0.0"
            )
            persisted = True
        except Exception as exc:
            print(f"American Idea ledger verification write failed: {exc}")

    return VerifyEvidenceResponse(
        article_url=str(payload.article_url),
        claims=claims,
        factual_claim_count=len(claims),
        fetched_source_count=fetched_source_count,
        verified_evidence_count=verified_evidence_count,
        ledger_persisted=persisted,
        ledger_revision_count=revision_count,
        methodology_note=(
            "American Idea fetched a bounded evidence set, fingerprinted retrieved sources, classified relevant passages, "
            "and passed every proposed resolved status through an auditable Trust Gate. Compound newsroom sentences remain "
            "conservative until their material atomic propositions can be evaluated independently."
        ),
    )
