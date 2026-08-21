from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .models import (
    AnalyzeRequest,
    AnalysisResponse,
    IngestUrlRequest,
    IngestUrlResponse,
    VerifyEvidenceRequest,
    VerifyEvidenceResponse,
)
from .services.claim_extractor import extract_candidate_claims
from .services.evidence_engine import attach_source_link_evidence
from .services.evidence_verifier import verify_claim_evidence
from .services.ledger import enabled as ledger_enabled
from .services.ledger import get_record, init_ledger, save_story_analysis, save_verification
from .services.url_ingestor import IngestionError, ingest_article_url

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
PUBLIC_STORYLENS_URL = "https://oluwafemidiakhoa.github.io/American_Idea/"

app = FastAPI(
    title="American Idea Evidence API",
    version="0.8.0",
    description=(
        "Transparent claim extraction, secure URL ingestion, conservative linked-source verification, "
        "and an optional persistent PostgreSQL Claim Ledger."
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


@app.on_event("startup")
def startup() -> None:
    # Persistence is deliberately optional. The API must still start if no database is attached.
    if ledger_enabled():
        try:
            init_ledger()
        except Exception as exc:
            # Do not take the public analysis API down because persistence is temporarily unavailable.
            print(f"American Idea ledger initialization failed: {exc}")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(PUBLIC_STORYLENS_URL, status_code=307)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "american-idea-evidence",
        "version": "0.8.0",
        "ledger_configured": ledger_enabled(),
    }


@app.get("/api/records/{record_id}")
def record(record_id: str):
    if not ledger_enabled():
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is not configured.")
    try:
        data = get_record(record_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Persistent Claim Ledger is temporarily unavailable.") from exc
    if data is None:
        raise HTTPException(status_code=404, detail="Evidence record was not found.")
    return data


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
            "Candidate factual claims are extracted using transparent heuristics. "
            "Extraction confidence estimates whether a statement appears externally verifiable; "
            "it is not a truth score. Claims remain unresolved until evidence is attached and evaluated."
        ),
    )


@app.post("/api/ingest-url", response_model=IngestUrlResponse)
def ingest_url(payload: IngestUrlRequest):
    try:
        article = ingest_article_url(str(payload.article_url))
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    claims = extract_candidate_claims(article.text)
    claims = attach_source_link_evidence(claims, article.blocks, article.final_url)

    evidence_link_count = sum(len(claim.get("evidence", [])) for claim in claims)
    claims_with_evidence = sum(1 for claim in claims if claim.get("evidence"))

    record_id = f"ai_{uuid4().hex[:16]}"
    persisted = False
    if ledger_enabled():
        try:
            stored_id = save_story_analysis(article=article, claims=claims)
            if stored_id:
                record_id = stored_id
                persisted = True
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
            "American Idea fetched the public HTML page, extracted readable article text, fingerprinted "
            "that text with SHA-256, identified candidate factual claims, and attached source-linked "
            "evidence leads found in the same article passages. When the Claim Ledger is configured, the "
            "story snapshot, claims, and evidence leads are persisted under a stable public record ID."
        ),
    )


@app.post("/api/verify-evidence", response_model=VerifyEvidenceResponse)
def verify_evidence(payload: VerifyEvidenceRequest):
    claims_input = [claim.model_dump() for claim in payload.claims]
    claims, fetched_source_count, verified_evidence_count = verify_claim_evidence(
        claims_input,
        max_fetches=payload.max_fetches,
    )

    persisted = False
    revision_count = 0
    if ledger_enabled():
        try:
            revision_count = save_verification(
                article_url=str(payload.article_url),
                claims=claims,
                methodology_version="0.8.0",
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
            "American Idea fetched a limited number of source-linked evidence leads, fingerprinted the "
            "retrieved pages, selected relevant passages, and classified their relationship to each claim. "
            "When the Claim Ledger is configured, verified evidence state and every status transition are "
            "persisted so the public record can be inspected later. Automated verification remains an aid, "
            "not a substitute for human review of consequential claims."
        ),
    )
