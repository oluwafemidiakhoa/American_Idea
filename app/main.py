from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import AnalyzeRequest, AnalysisResponse, IngestUrlRequest, IngestUrlResponse
from .services.claim_extractor import extract_candidate_claims
from .services.evidence_engine import attach_source_link_evidence
from .services.url_ingestor import IngestionError, ingest_article_url

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="American Idea Evidence API",
    version="0.6.0",
    description="Transparent claim extraction, secure URL ingestion, and source-linked evidence leads.",
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


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "american-idea-evidence", "version": "0.6.0"}


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

    return IngestUrlResponse(
        record_id=f"ai_{uuid4().hex[:16]}",
        source_name=article.source_name,
        article_url=article.final_url,
        requested_url=article.requested_url,
        final_url=article.final_url,
        title=article.title,
        content_sha256=article.content_sha256,
        extracted_text_length=len(article.text),
        claims=claims,
        factual_claim_count=len(claims),
        evidence_link_count=evidence_link_count,
        claims_with_evidence=claims_with_evidence,
        methodology_note=(
            "American Idea fetched the public HTML page, extracted readable article text, fingerprinted "
            "that text with SHA-256, identified candidate factual claims, and attached source-linked "
            "evidence leads found in the same article passages. These links are provenance leads, not "
            "independent verification. No claim changes from unresolved merely because the article links to a source."
        ),
    )
