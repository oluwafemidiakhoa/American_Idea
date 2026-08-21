from typing import Literal
from pydantic import BaseModel, Field, HttpUrl

ClaimStatus = Literal["supported", "partially_supported", "contested", "unsupported", "unresolved"]


class AnalyzeRequest(BaseModel):
    article_text: str = Field(min_length=20, max_length=100_000)
    article_url: HttpUrl | None = None
    source_name: str | None = Field(default=None, max_length=120)


class IngestUrlRequest(BaseModel):
    article_url: HttpUrl


class EvidenceItem(BaseModel):
    kind: Literal["primary", "secondary", "counterevidence", "context"]
    label: str
    url: str | None = None
    note: str | None = None


class Claim(BaseModel):
    id: str
    text: str
    status: ClaimStatus = "unresolved"
    confidence: float = Field(ge=0, le=1)
    why_flagged: list[str] = []
    evidence: list[EvidenceItem] = []


class AnalysisResponse(BaseModel):
    record_id: str
    source_name: str | None
    article_url: str | None
    claims: list[Claim]
    factual_claim_count: int
    methodology_note: str


class IngestUrlResponse(AnalysisResponse):
    requested_url: str
    final_url: str
    title: str | None
    content_sha256: str
    extracted_text_length: int
    snapshot_status: Literal["fingerprinted_not_persisted"] = "fingerprinted_not_persisted"
    evidence_link_count: int = 0
    claims_with_evidence: int = 0
