from typing import Literal
from pydantic import BaseModel, Field, HttpUrl

ClaimStatus = Literal["supported", "partially_supported", "contested", "unsupported", "unresolved"]
EvidenceKind = Literal["primary", "secondary", "counterevidence", "context"]
EvidenceRelation = Literal["supports", "contradicts", "contextualizes", "mentions"]
SourceType = Literal["news", "government", "court", "academic", "official_record", "dataset", "social", "podcast", "video", "other"]


class AnalyzeRequest(BaseModel):
    article_text: str = Field(min_length=20, max_length=100_000)
    article_url: HttpUrl | None = None
    source_name: str | None = Field(default=None, max_length=120)


class EvidenceItem(BaseModel):
    kind: EvidenceKind
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


class EvidenceCandidateRequest(BaseModel):
    claim_id: str = Field(min_length=8, max_length=80)
    label: str = Field(min_length=3, max_length=300)
    url: HttpUrl | None = None
    kind: EvidenceKind
    relation: EvidenceRelation
    source_type: SourceType
    directness: float = Field(ge=0, le=1)
    independence: float = Field(ge=0, le=1)
    has_capture_hash: bool = False
    note: str | None = Field(default=None, max_length=2000)


class EvidenceAssessment(BaseModel):
    evidence_id: str
    claim_id: str
    label: str
    url: str | None
    kind: EvidenceKind
    relation: EvidenceRelation
    source_type: SourceType
    quality_score: float = Field(ge=0, le=1)
    quality_reasons: list[str]
    warnings: list[str]
    review_required: bool
    claim_status: ClaimStatus
    note: str | None = None
    methodology_note: str
