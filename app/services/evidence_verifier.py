import re
from copy import deepcopy
from dataclasses import dataclass
from urllib.parse import urlparse

from .trust_gate import enforce_claim_trust
from .url_ingestor import IngestionError, IngestedArticle, ingest_article_url

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'’-]*", re.I)
NUMBER_RE = re.compile(
    r"(?:\$\s?\d[\d,.]*|\b\d+(?:\.\d+)?%\b|\b(?:19|20)\d{2}\b|\b\d[\d,.]*\s+(?:million|billion|trillion|people|votes|views|points|days|hours|minutes|jobs|cases|deaths|miles)\b)",
    re.I,
)
NEGATION_RE = re.compile(r"\b(?:no|not|never|none|neither|denied|deny|false|incorrect|didn't|did not|hasn't|has not|won't|will not)\b", re.I)
TEMPORAL_NOT_UNTIL_RE = re.compile(r"\bnot\b.{0,80}\buntil\b", re.I)
STOPWORDS = {
    "the", "and", "that", "with", "from", "this", "they", "their", "there", "have", "has", "had",
    "was", "were", "are", "for", "but", "not", "into", "about", "after", "before", "during", "while",
    "said", "says", "according", "reported", "report", "reports", "would", "could", "should", "will", "been",
    "being", "also", "than", "then", "its", "his", "her", "him", "she", "who", "which", "when", "where",
    "what", "over", "under", "more", "most", "some", "one", "two", "our", "out", "new", "now", "still",
}


@dataclass
class PassageMatch:
    text: str
    overlap: float
    shared_numbers: list[str]
    claim_numbers: list[str]
    source_numbers: list[str]
    relation: str
    confidence: float


def _hostname(url: str | None) -> str:
    if not url:
        return ""
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _tokens(text: str) -> set[str]:
    return {
        token.lower().strip("'’-_")
        for token in TOKEN_RE.findall(text)
        if len(token) >= 3 and token.lower().strip("'’-_") not in STOPWORDS
    }


def _numbers(text: str) -> set[str]:
    return {re.sub(r"\s+", " ", item.lower().replace(",", "")).strip() for item in NUMBER_RE.findall(text)}


def _overlap(claim_text: str, source_text: str) -> float:
    claim = _tokens(claim_text)
    if not claim:
        return 0.0
    source = _tokens(source_text)
    return len(claim & source) / len(claim)


def _semantic_negation(text: str) -> bool:
    scrubbed = TEMPORAL_NOT_UNTIL_RE.sub(" ", text)
    return bool(NEGATION_RE.search(scrubbed))


def classify_evidence_passage(claim_text: str, passage_text: str) -> PassageMatch:
    overlap = _overlap(claim_text, passage_text)
    claim_numbers = _numbers(claim_text)
    source_numbers = _numbers(passage_text)
    shared_numbers = claim_numbers & source_numbers
    claim_negated = _semantic_negation(claim_text)
    source_negated = _semantic_negation(passage_text)

    if overlap >= 0.62 and claim_negated != source_negated:
        relation = "contradicts"
        confidence = min(0.92, 0.68 + overlap * 0.25)
    elif claim_numbers and claim_numbers.issubset(source_numbers) and overlap >= 0.40:
        relation = "supports"
        confidence = min(0.95, 0.66 + overlap * 0.25 + min(0.08, len(shared_numbers) * 0.03))
    elif overlap >= 0.68:
        relation = "supports"
        confidence = min(0.90, 0.62 + overlap * 0.30)
    elif overlap >= 0.38:
        relation = "contextualizes"
        confidence = min(0.82, 0.46 + overlap * 0.35)
    elif overlap >= 0.22 or shared_numbers:
        relation = "mentions"
        confidence = min(0.70, 0.34 + overlap * 0.30)
    else:
        relation = "mentions"
        confidence = max(0.15, overlap)

    return PassageMatch(
        text=passage_text,
        overlap=round(overlap, 4),
        shared_numbers=sorted(shared_numbers),
        claim_numbers=sorted(claim_numbers),
        source_numbers=sorted(source_numbers),
        relation=relation,
        confidence=round(confidence, 4),
    )


def best_passage_match(claim_text: str, article: IngestedArticle) -> PassageMatch:
    candidates = article.blocks or []
    if not candidates:
        return classify_evidence_passage(claim_text, article.text[:1200])

    ranked: list[tuple[float, int, str]] = []
    claim_numbers = _numbers(claim_text)
    for block in candidates:
        overlap = _overlap(claim_text, block.text)
        shared = len(claim_numbers & _numbers(block.text))
        ranked.append((overlap + min(0.18, shared * 0.06), shared, block.text))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return classify_evidence_passage(claim_text, ranked[0][2])


def derive_claim_status(claim: dict) -> tuple[str, str]:
    verified = [
        item for item in claim.get("evidence", [])
        if item.get("fetch_status") == "verified" and item.get("relation") in {"supports", "contradicts"}
    ]
    supports = [item for item in verified if item.get("relation") == "supports" and item.get("verification_confidence", 0) >= 0.78]
    contradicts = [item for item in verified if item.get("relation") == "contradicts" and item.get("verification_confidence", 0) >= 0.80]

    support_hosts = {_hostname(item.get("url")) for item in supports if _hostname(item.get("url"))}
    contradict_hosts = {_hostname(item.get("url")) for item in contradicts if _hostname(item.get("url"))}
    primary_support = [item for item in supports if item.get("kind") == "primary"]
    primary_contradict = [item for item in contradicts if item.get("kind") == "primary"]

    if supports and contradicts:
        return "contested", "Strong fetched evidence points in both supporting and contradicting directions."

    if len(support_hosts) >= 2 and primary_support and max(item.get("verification_confidence", 0) for item in primary_support) >= 0.84:
        return "supported", "At least two independent fetched sources support the claim, including a high-confidence primary-source match."

    if primary_support and max(item.get("verification_confidence", 0) for item in primary_support) >= 0.86:
        return "partially_supported", "A fetched primary source strongly matches the claim, but independent corroboration is still limited."

    if len(support_hosts) >= 2 and all(item.get("verification_confidence", 0) >= 0.82 for item in supports[:2]):
        return "partially_supported", "Multiple independent fetched sources strongly match the claim, but no qualifying primary source has been verified yet."

    if len(contradict_hosts) >= 2 and primary_contradict and max(item.get("verification_confidence", 0) for item in primary_contradict) >= 0.86:
        return "unsupported", "Multiple independent fetched sources contradict the claim, including a high-confidence primary-source match."

    return "unresolved", "Available fetched evidence is not strong or independent enough to change the claim status."


def verify_claim_evidence(
    claims: list[dict],
    *,
    max_fetches: int = 6,
    timeout_seconds: float = 7.0,
) -> tuple[list[dict], int, int]:
    output = deepcopy(claims)
    cache: dict[str, IngestedArticle | Exception] = {}
    fetch_budget = max(0, max_fetches)

    unique_urls: list[tuple[int, str]] = []
    seen: set[str] = set()
    for claim in output:
        for item in claim.get("evidence", []):
            url = item.get("url")
            if not url or url in seen or item.get("kind") == "context":
                continue
            priority = 0 if item.get("kind") == "primary" else 1
            unique_urls.append((priority, url))
            seen.add(url)
    unique_urls.sort(key=lambda pair: pair[0])

    for _, url in unique_urls[:fetch_budget]:
        try:
            cache[url] = ingest_article_url(url, timeout_seconds=timeout_seconds, max_redirects=4)
        except (IngestionError, ValueError) as exc:
            cache[url] = exc

    verified_count = 0
    for claim in output:
        for item in claim.get("evidence", []):
            item.setdefault("relation", "unverified_lead")
            item.setdefault("verification_confidence", 0.0)
            item.setdefault("fetch_status", "not_fetched")
            url = item.get("url")

            if item.get("kind") == "context":
                item["relation"] = "contextualizes"
                item["fetch_status"] = "skipped"
                item["note"] = "Same-site context lead; not used to change claim status."
                continue

            if not url or url not in cache:
                item["fetch_status"] = "not_fetched"
                item["note"] = "Evidence lead was not fetched in this verification pass because of the source limit."
                continue

            fetched = cache[url]
            if isinstance(fetched, Exception):
                item["fetch_status"] = "fetch_failed"
                item["note"] = f"American Idea could not fetch this evidence lead: {fetched}"
                continue

            match = best_passage_match(claim["text"], fetched)
            item["fetch_status"] = "verified"
            item["relation"] = match.relation
            item["verification_confidence"] = match.confidence
            item["source_title"] = fetched.title
            item["source_excerpt"] = match.text[:700]
            item["source_sha256"] = fetched.content_sha256
            item["url"] = fetched.final_url
            item["note"] = (
                "Fetched and fingerprinted by American Idea. Relation is based on transparent lexical, numeric, "
                "and negation matching; inspect the source passage before relying on the classification."
            )
            verified_count += 1

        status, basis = derive_claim_status(claim)
        claim["status"] = status
        claim["status_basis"] = basis
        enforce_claim_trust(claim)

    fetched_count = sum(1 for value in cache.values() if not isinstance(value, Exception))
    return output, fetched_count, verified_count
