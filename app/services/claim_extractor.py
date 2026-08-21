import hashlib
import re
from dataclasses import dataclass

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“‘])")
MEASURABLE = re.compile(
    r"(?:\$\s?\d[\d,.]*|\b\d+(?:\.\d+)?%\b|\b\d[\d,.]*\s+(?:people|votes|views|points|days|hours|minutes|dollars|jobs|cases|deaths|miles|percent|million|billion|trillion)\b|\b(?:million|billion|trillion)\b)",
    re.I,
)
ATTRIBUTION = re.compile(
    r"\b(?:said|says|reported|according to|announced|claimed|found|shows?|rose|fell|increased|decreased|won|lost|indicates?|identified|held|backed|support(?:ed)?|confirmed|estimated|recorded)\b",
    re.I,
)
DATE_OR_TIME = re.compile(
    r"\b(?:19|20)\d{2}\b|\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b",
    re.I,
)
OPINION_CUES = re.compile(
    r"\b(?:I think|I believe|should|ought to|best|worst|disgraceful|wonderful|dangerous|important|big deal|monumental|"
    r"hope is not lost|values do matter|gratuitous|unnecessary|disgusting|radical|exciting|remarkable|terrible|amazing)\b",
    re.I,
)
BOILERPLATE = re.compile(
    r"\b(?:sign up|newsletter|stay up to date|election hub|power rankings|watch|video|click here|read more|advertisement|sponsored|subscribe|download the app|follow us)\b",
    re.I,
)
CAPTION_CUES = re.compile(
    r"\b(?:Getty Images|Bloomberg via Getty Images|AP Photo|Reuters|Photo by|Image by|file photo|speaks to members of the media|during the opening of|during a press conference)\b",
    re.I,
)
MEDIA_FILENAME = re.compile(
    r"(?:^|\s)[A-Za-z0-9_-]{8,}\.(?:jpe?g|png|gif|webp|mp4|mov)(?:\s|$)",
    re.I,
)
MEDIA_ID_PREFIX = re.compile(r"^\d{12,}_[A-Za-z0-9_-]+\.(?:jpe?g|png|gif|webp)\s*", re.I)
SOCIAL_CREDIT_PREFIX = re.compile(
    r"^(?:[A-Z][A-Za-z.'’-]+(?:\s+[A-Z][A-Za-z.'’-]+){0,3})\s*/\s*(?:Facebook|Instagram|X|Twitter|TikTok)\s+",
    re.I,
)
ALL_CAPS_RUN = re.compile(r"(?:\b[A-Z][A-Z’'\-]{2,}\b(?:\s+|$)){3,}")
ABBREVIATION = re.compile(
    r"\b(?:Dr|Mr|Mrs|Ms|Prof|Sen|Rep|Gov|Gen|Lt|Col|St|No|Inc|Corp|Co|vs|U\.S|U\.K|D\.C)\.$",
    re.I,
)
ATTRIBUTION_TAIL = re.compile(r"\b(?:said|says|told|according to)\s+(?:Dr|Mr|Mrs|Ms|Prof|Sen|Rep|Gov|Gen|Lt|Col)\.?$", re.I)


@dataclass
class Candidate:
    text: str
    score: float
    reasons: list[str]


def _normalize(sentence: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence).strip(" \t\n\r-•")
    sentence = MEDIA_ID_PREFIX.sub("", sentence).strip()
    sentence = SOCIAL_CREDIT_PREFIX.sub("", sentence).strip()
    sentence = re.sub(r"^(?:[A-Z][A-Z0-9’'\-]+\s+){3,}", "", sentence).strip()
    return sentence


def _claim_id(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"claim_{digest}"


def _is_noise(sentence: str) -> bool:
    if BOILERPLATE.search(sentence):
        return True
    if CAPTION_CUES.search(sentence):
        return True
    if MEDIA_FILENAME.search(sentence):
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
    if ATTRIBUTION_TAIL.search(sentence):
        return True
    if sentence.count('"') % 2 == 1 and sentence.count("“") == sentence.count("”"):
        return True
    return False


def _split_block_sentences(block: str) -> list[str]:
    """Split prose without breaking after common abbreviations such as Dr. or U.S."""
    pieces: list[str] = []
    start = 0
    for match in re.finditer(r"[.!?][\"'”’)]*\s+(?=[A-Z\"“‘])", block):
        end = match.end()
        candidate = block[start:match.start() + 1].rstrip()
        if ABBREVIATION.search(candidate):
            continue
        pieces.append(block[start:end].strip())
        start = end
    tail = block[start:].strip()
    if tail:
        pieces.append(tail)
    return pieces


def _split_blocks(text: str) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n+", text) if b.strip()]
    sentences: list[str] = []
    for block in blocks:
        sentences.extend(_split_block_sentences(block))
    return sentences


def extract_candidate_claims(text: str, limit: int = 20) -> list[dict]:
    candidates: list[Candidate] = []

    for raw in _split_blocks(text):
        sentence = _normalize(raw)
        if len(sentence) < 35 or len(sentence) > 420:
            continue
        if _is_noise(sentence) or _looks_like_fragment(sentence):
            continue

        reasons: list[str] = []
        score = 0.10

        has_measure = bool(MEASURABLE.search(sentence))
        has_attribution = bool(ATTRIBUTION.search(sentence))
        has_date = bool(DATE_OR_TIME.search(sentence))
        has_opinion = bool(OPINION_CUES.search(sentence))

        if has_measure:
            reasons.append("contains a measurable quantity")
            score += 0.35
        if has_attribution:
            reasons.append("contains an attributed or externally verifiable assertion")
            score += 0.25
        if has_date:
            reasons.append("contains a date or time-bounded assertion")
            score += 0.10
        if has_measure and has_attribution:
            score += 0.10
        if has_opinion:
            score -= 0.35

        # Attribution alone is not enough for subjective commentary.
        if has_opinion and not has_measure and not has_date:
            continue
        if not has_measure and has_date and not has_attribution:
            continue

        if score >= 0.35 and reasons:
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
