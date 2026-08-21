import re
from urllib.parse import urlparse

from .url_ingestor import ArticleBlock

TOKEN_RE = re.compile(r"[a-z0-9]{3,}", re.I)
GENERIC_ANCHOR = re.compile(r"^(?:here|source|link|read more|more|this|report)$", re.I)
SOCIAL_HOSTS = {
    "facebook.com",
    "www.facebook.com",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "instagram.com",
    "www.instagram.com",
    "linkedin.com",
    "www.linkedin.com",
}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _token_overlap(claim_text: str, block_text: str) -> float:
    claim_tokens = set(TOKEN_RE.findall(claim_text.lower()))
    if not claim_tokens:
        return 0.0
    block_tokens = set(TOKEN_RE.findall(block_text.lower()))
    return len(claim_tokens & block_tokens) / len(claim_tokens)


def _same_passage(claim_text: str, block_text: str) -> bool:
    claim = _normalize(claim_text)
    block = _normalize(block_text)
    if claim in block or block in claim:
        return True
    return _token_overlap(claim, block) >= 0.72


def _evidence_kind(url: str, article_url: str) -> str:
    host = _hostname(url)
    article_host = _hostname(article_url)
    if not host:
        return "context"
    if host == article_host:
        return "context"
    if host.endswith(".gov") or host.endswith(".mil"):
        return "primary"
    return "secondary"


def _label(anchor_text: str, url: str) -> str:
    text = re.sub(r"\s+", " ", anchor_text).strip(" \t\n\r-–—|:;")
    if text and not GENERIC_ANCHOR.match(text):
        return text[:180]
    return _hostname(url) or "Linked source"


def attach_source_link_evidence(
    claims: list[dict],
    blocks: list[ArticleBlock],
    article_url: str,
    *,
    max_per_claim: int = 5,
) -> list[dict]:
    """Attach evidence *candidates* linked by the source article.

    These links are provenance leads, not independent verification. Merely being linked by
    an article does not change a claim's truth status.
    """
    article_host = _hostname(article_url)

    for claim in claims:
        evidence: list[dict] = []
        seen_urls: set[str] = set()

        for block in blocks:
            if not _same_passage(claim["text"], block.text):
                continue

            for link in block.links:
                host = _hostname(link.url)
                if not host or host in SOCIAL_HOSTS:
                    continue
                if link.url in seen_urls:
                    continue

                # Same-site links can still provide useful context, but avoid generic
                # navigation/self links unless the anchor is descriptive.
                if host == article_host and (not link.text or GENERIC_ANCHOR.match(link.text.strip())):
                    continue

                kind = _evidence_kind(link.url, article_url)
                evidence.append(
                    {
                        "kind": kind,
                        "label": _label(link.text, link.url),
                        "url": link.url,
                        "note": (
                            "Linked by the source article in the same passage as this claim. "
                            "American Idea has not yet independently verified what the linked source proves."
                        ),
                    }
                )
                seen_urls.add(link.url)
                if len(evidence) >= max_per_claim:
                    break

            if len(evidence) >= max_per_claim:
                break

        claim["evidence"] = evidence
        # Evidence leads alone do not change the truth status.
        claim["status"] = "unresolved"

    return claims
