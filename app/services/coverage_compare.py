import hashlib
import math
import re
from collections import Counter
from typing import Any

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'’-]*", re.I)
NUMBER_RE = re.compile(
    r"(?:\$\s?\d[\d,.]*|\b\d+(?:\.\d+)?%\b|\b(?:19|20)\d{2}\b|"
    r"\b\d[\d,.]*\s+(?:million|billion|trillion|people|votes|views|points|days|hours|minutes|jobs|cases|deaths|miles)\b)",
    re.I,
)
STOPWORDS = {
    "the", "and", "that", "with", "from", "this", "they", "their", "there", "have", "has", "had",
    "was", "were", "are", "for", "but", "not", "into", "about", "after", "before", "during", "while",
    "said", "says", "according", "reported", "report", "reports", "would", "could", "should", "will", "been",
    "being", "also", "than", "then", "its", "his", "her", "him", "she", "who", "which", "when", "where",
    "what", "over", "under", "more", "most", "some", "one", "two", "our", "out", "new", "now", "still",
    "news", "article", "story", "officials", "official", "spokesperson", "statement",
}


def _tokens(text: str) -> set[str]:
    return {
        token.lower().strip("'’-_")
        for token in TOKEN_RE.findall(text)
        if len(token) >= 3 and token.lower().strip("'’-_") not in STOPWORDS
    }


def _numbers(text: str) -> set[str]:
    return {
        re.sub(r"\s+", " ", value.lower().replace(",", "")).strip()
        for value in NUMBER_RE.findall(text)
    }


def claim_similarity(left: str, right: str) -> float:
    """Return a conservative lexical similarity score from 0 to 1.

    Numeric disagreement is deliberately penalized because two otherwise similar statements
    with incompatible dates or quantities should not be merged into one coverage cluster.
    """
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0

    shared = left_tokens & right_tokens
    if len(shared) < 3:
        return 0.0

    union = left_tokens | right_tokens
    overlap = len(shared) / min(len(left_tokens), len(right_tokens))
    jaccard = len(shared) / len(union)
    score = (0.62 * overlap) + (0.38 * jaccard)

    left_numbers = _numbers(left)
    right_numbers = _numbers(right)
    if left_numbers and right_numbers:
        shared_numbers = left_numbers & right_numbers
        if shared_numbers:
            score += min(0.16, 0.05 * len(shared_numbers) + 0.06)
        else:
            score -= 0.28

    return round(max(0.0, min(1.0, score)), 4)


def _member(record: dict[str, Any], claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": record["record_id"],
        "source_name": record.get("source_name"),
        "article_url": record.get("article_url"),
        "claim_id": claim["id"],
        "text": claim["text"],
        "status": claim.get("status", "unresolved"),
    }


def _cluster_id(members: list[dict[str, Any]]) -> str:
    material = "|".join(sorted(member["claim_id"] for member in members)).encode("utf-8")
    return f"cov_{hashlib.sha256(material).hexdigest()[:16]}"


def _classification(source_count: int, source_total: int) -> str:
    if source_count == source_total:
        return "shared"
    if source_count == 1:
        return "source_specific"
    if source_count >= math.ceil(source_total / 2):
        return "majority"
    return "partial"


def _representative(members: list[dict[str, Any]]) -> str:
    # Prefer the member that most resembles the rest, then the more complete phrasing.
    if len(members) == 1:
        return members[0]["text"]

    ranked: list[tuple[float, int, str]] = []
    for member in members:
        score = sum(
            claim_similarity(member["text"], other["text"])
            for other in members
            if other is not member
        )
        ranked.append((score, len(member["text"]), member["text"]))
    ranked.sort(reverse=True)
    return ranked[0][2]


def compare_records(records: list[dict[str, Any]], *, threshold: float = 0.56) -> dict[str, Any]:
    """Cluster substantially similar claims across saved story records.

    A record may contribute at most one claim to a cluster. The result describes coverage
    similarity; it does not infer motive, bias, importance, or whether a source 'omitted' a fact.
    """
    if len(records) < 2:
        raise ValueError("At least two saved records are required for coverage comparison.")

    source_total = len(records)
    clusters: list[dict[str, Any]] = []

    flattened: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for record in records:
        for claim in record.get("claims", []):
            flattened.append((record, claim))

    # Put higher-information claims first so they become stable cluster anchors.
    flattened.sort(
        key=lambda pair: (
            len(_tokens(pair[1].get("text", ""))),
            float(pair[1].get("confidence") or 0),
            len(pair[1].get("text", "")),
        ),
        reverse=True,
    )

    for record, claim in flattened:
        claim_text = claim.get("text", "")
        best_index: int | None = None
        best_score = 0.0

        for index, cluster in enumerate(clusters):
            if record["record_id"] in cluster["record_ids"]:
                continue
            score = claim_similarity(claim_text, cluster["anchor_text"])
            if score >= threshold and score > best_score:
                best_index = index
                best_score = score

        member = _member(record, claim)
        if best_index is None:
            clusters.append(
                {
                    "anchor_text": claim_text,
                    "members": [member],
                    "record_ids": {record["record_id"]},
                }
            )
        else:
            clusters[best_index]["members"].append(member)
            clusters[best_index]["record_ids"].add(record["record_id"])
            # Re-center the anchor as the cluster grows.
            clusters[best_index]["anchor_text"] = _representative(clusters[best_index]["members"])

    output_clusters: list[dict[str, Any]] = []
    for cluster in clusters:
        members = sorted(cluster["members"], key=lambda item: (item.get("source_name") or "", item["record_id"]))
        source_count = len(cluster["record_ids"])
        status_counts = Counter(member.get("status", "unresolved") for member in members)
        resolved_statuses = {
            status for status in status_counts
            if status not in {"unresolved"}
        }
        status_disagreement = len(resolved_statuses) > 1 or "contested" in resolved_statuses

        output_clusters.append(
            {
                "cluster_id": _cluster_id(members),
                "representative_claim": _representative(members),
                "classification": _classification(source_count, source_total),
                "source_count": source_count,
                "source_total": source_total,
                "coverage_ratio": round(source_count / source_total, 4),
                "status_summary": dict(sorted(status_counts.items())),
                "status_disagreement": status_disagreement,
                "members": members,
            }
        )

    classification_rank = {"shared": 0, "majority": 1, "partial": 2, "source_specific": 3}
    output_clusters.sort(
        key=lambda item: (
            classification_rank[item["classification"]],
            -item["source_count"],
            item["representative_claim"].lower(),
        )
    )

    record_summaries = [
        {
            "record_id": record["record_id"],
            "source_name": record.get("source_name"),
            "article_url": record.get("article_url"),
            "title": record.get("title"),
            "content_sha256": record.get("content_sha256"),
            "captured_at": record.get("captured_at"),
        }
        for record in records
    ]

    return {
        "records": record_summaries,
        "clusters": output_clusters,
        "shared_cluster_count": sum(1 for item in output_clusters if item["classification"] == "shared"),
        "source_specific_cluster_count": sum(1 for item in output_clusters if item["classification"] == "source_specific"),
        "methodology_note": (
            "Compare Coverage groups substantially similar saved claims using transparent lexical and numeric matching. "
            "A cluster shows that multiple records made similar assertions; it does not prove the assertion true. "
            "A source-specific cluster means the current comparison set did not contain a sufficiently similar claim "
            "from the other records. American Idea does not infer motive or call that an omission from this signal alone."
        ),
    }
