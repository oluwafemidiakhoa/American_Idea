import hashlib
import re
from dataclasses import dataclass

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“‘])")
NUMBERISH = re.compile(r"(?:\$?\d[\d,.]*%?|\b(?:million|billion|trillion)\b)", re.I)
ATTRIBUTION = re.compile(
    r"\b(?:said|says|reported|according to|announced|claimed|found|shows?|rose|fell|increased|decreased|won|lost|indicates?|identified|held|backed|support(?:ed)?)\b",
    re.I,
)
DATE_OR_TIME = re.compile(
    r"\b(?:19|20)\d{2}\b|\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b",
    re.I,
)
OPINION_CUES = re.compile(
    r"\b(?:I think|I believe|should|ought to|best|worst|disgraceful|wonderful|dangerous|important|hope is not lost|values do matter)\b",
    re.I,
)
BOILERPLATE = re.compile(
    r"\b(?:sign up|newsletter|stay up to date|election hub|power rankings|watch|video|click here|read more|advertisement|sponsored|subscribe)\b",
    re.I,
)
ALL_CAPS_RUN = re.compile(r"(?:\b[A-Z][A-Z’'\-]{2,}\b(?:\s+|$)){3,}")

@dataclass
class Candidate:
    text: str
    score: float
    reasons: list[str]


def _normalize(sentence: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence).strip(" \t\n\r-•")
    sentence = re.sub(r"^(?:[A-Z][A-Z0-9’'\-]+\s+){3,}", "", sentence).strip()
    return sentence


def _claim_id(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"claim_{digest}"


def _is_noise(sentence: str) -> bool:
    if BOILERPLATE.search(sentence):
        return True
    if ALL_CAPS_RUN.search(sentence) and len(sentence.split()) < 18:
        return True
    if sentence.count("###") or sentence.startswith(("http://", "https://")):
        return True
    return False


def _looks_like_fragment(sentence: str) -> bool:
    words = sentence.split()
    if len(words) < 7:
        return True
    if re.match(r"^\d{1,2},\s+\d{4},", sentence):
        return True
    if sentence[0].islower():
        return True
    return False


def extract_candidate_claims(text: str, limit: int = 20) -> list[dict]:
    candidates: list[Candidate] = []

    for raw in SENTENCE_SPLIT.split(text):
        sentence = _normalize(raw)
        if len(sentence) < 35 or len(sentence) > 450:
            continue
        if _is_noise(sentence) or _looks_like_fragment(sentence):
            continue

        reasons: list[str] = []
        score = 0.10

        has_number = bool(NUMBERISH.search(sentence))
        has_attribution = bool(ATTRIBUTION.search(sentence))
        has_date = bool(DATE_OR_TIME.search(sentence))
        has_opinion = bool(OPINION_CUES.search(sentence))

        if has_number:
            reasons.append("contains a measurable quantity")
            score += 0.35
        if has_attribution:
            reasons.append("contains an attributed or externally verifiable assertion")
            score += 0.25
        if has_date:
            reasons.append("contains a date or time-bounded assertion")
            score += 0.15
        if has_number and has_attribution:
            score += 0.10
        if has_opinion:
            score -= 0.30

        if score >= 0.35:
            candidates.append(Candidate(sentence, min(max(score, 0.0), 0.95), reasons))

    candidates.sort(key=lambda c: c.score, reverse=True)

    unique: list[dict] = []
    seen = set()
    for candidate in candidates:
        key = re.sub(r"\W+", " ", candidate.text.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(
            {
                "id": _claim_id(candidate.text),
                "text": candidate.text,
                "status": "unresolved",
                "confidence": round(candidate.score, 2),
                "why_flagged": candidate.reasons,
                "evidence": [],
            }
        )
        if len(unique) >= limit:
            break

    return unique
