from typing import Any, Literal
from pydantic import BaseModel, Field, HttpUrl

ClaimStatus = Literal["supported", "partially_supported", "contested", "unsupported", "unresolved"]
EvidenceRelation = Literal["supports", "contradicts", "contextualizes", "mentions", "unverified_lead"]
FetchStatus = Literal["verified", "fetch_failed", "not_fetched", "skipped"]
SnapshotStatus = Literal["fingerprinted_not_persisted", "persisted"]


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
    relation: EvidenceRelation = "unverified_lead"
    verification_confidence: float = Field(default=0.0, ge=0, le=1)
    fetch_status: FetchStatus = "not_fetched"
    source_title: str | None = None
    source_excerpt: str | None = None
    source_sha256: str | None = None


class Claim(BaseModel):
    id: str
    text: str
    status: ClaimStatus = "unresolved"
    confidence: float = Field(ge=0, le=1)
    why_flagged: list[str] = []
    evidence: list[EvidenceItem] = []
    status_basis: str | None = None
    trust_gate: dict[str, Any] | None = None


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
    snapshot_status: SnapshotStatus = "fingerprinted_not_persisted"
    ledger_persisted: bool = False
    evidence_link_count: int = 0
    claims_with_evidence: int = 0


class VerifyEvidenceRequest(BaseModel):
    article_url: HttpUrl
    claims: list[Claim]
    max_fetches: int = Field(default=6, ge=1, le=12)


class VerifyEvidenceResponse(BaseModel):
    article_url: str
    claims: list[Claim]
    factual_claim_count: int
    fetched_source_count: int
    verified_evidence_count: int
    ledger_persisted: bool = False
    ledger_revision_count: int = 0
    methodology_note: str


class CompareCoverageRequest(BaseModel):
    record_ids: list[str] = Field(min_length=2, max_length=5)


class CompareCoverageResponse(BaseModel):
    records: list[dict[str, Any]]
    clusters: list[dict[str, Any]]
    shared_cluster_count: int
    source_specific_cluster_count: int
    methodology_note: str
