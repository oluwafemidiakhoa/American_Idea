import hashlib
import re
from dataclasses import dataclass

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
NUMBERISH = re.compile(r"(?:\$?\d[\d,.]*%?|\b(?:million|billion|trillion)\b)", re.I)
ATTRIBUTION = re.compile(r"\b(?:said|says|reported|according to|announced|claimed|found|shows?|rose|fell|increased|decreased|won|lost)\b", re.I)
DATE_OR_TIME = re.compile(r"\b(?:19|20)\d{2}\b|\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", re.I)
OPINION_CUES = re.compile(r"\b(?:I think|I believe|should|ought to|best|worst|disgraceful|wonderful)\b", re.I)

@dataclass
class Candidate:
    text: str
    score: float
    reasons: list[str]


def _normalize(sentence: str) -> str:
    return re.sub(r"\s+", " ", sentence).strip(" \t\n\r-•")


def _claim_id(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"claim_{digest}"


def extract_candidate_claims(text: str, limit: int = 20) -> list[dict]:
    candidates: list[Candidate] = []
    for raw in SENTENCE_SPLIT.split(text):
        sentence = _normalize(raw)
        if len(sentence) < 35 or len(sentence) > 450:
            continue
        reasons: list[str] = []
        score = 0.15
        if NUMBERISH.search(sentence):
            reasons.append("contains a measurable quantity")
            score += 0.35
        if ATTRIBUTION.search(sentence):
            reasons.append("contains an attributed or externally verifiable assertion")
            score += 0.25
        if DATE_OR_TIME.search(sentence):
            reasons.append("contains a date or time-bounded assertion")
            score += 0.15
        if OPINION_CUES.search(sentence):
            score -= 0.25
        if score >= 0.35:
            candidates.append(Candidate(sentence, min(score, 0.95), reasons))

    candidates.sort(key=lambda c: c.score, reverse=True)
    unique: list[dict] = []
    seen = set()
    for candidate in candidates:
        key = candidate.text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append({
            "id": _claim_id(candidate.text),
            "text": candidate.text,
            "status": "unresolved",
            "confidence": round(candidate.score, 2),
            "why_flagged": candidate.reasons,
            "evidence": [],
        })
        if len(unique) >= limit:
            break
    return unique
