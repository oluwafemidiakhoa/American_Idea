from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import AnalyzeRequest, AnalysisResponse
from .services.claim_extractor import extract_candidate_claims

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="American Idea Evidence API",
    version="0.1.0",
    description="Transparent claim extraction and evidence-led news analysis MVP.",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "american-idea-evidence", "version": "0.1.0"}

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
            "MVP mode extracts candidate factual claims using transparent heuristics. "
            "It does not label claims true or false without evidence. Evidence retrieval, "
            "cross-source comparison, provenance, and human review are the next layers."
        ),
    )
