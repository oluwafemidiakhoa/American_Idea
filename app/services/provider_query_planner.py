import re

NOISE_TERMS = {
    "story", "title", "source", "nearby", "claim", "cnn", "reuters", "fox", "news", "digital", "live", "updates",
    "said", "says", "wednesday", "monday", "tuesday", "thursday", "friday", "saturday", "sunday", "helped",
    "prevent", "return", "spread", "large", "more", "than", "people", "patients", "appearing", "take",
}

PROFILE_TERMS = {
    "life_science": (
        "melanoma", "cancer", "vaccine", "trial", "clinical trial", "phase 3", "phase 2", "pembrolizumab",
        "keytruda", "intismeran", "mrna", "recurrence", "metastasis", "survival", "tumor", "oncology",
    ),
    "geopolitics_conflict": (
        "iran", "iranian", "israel", "ukraine", "russia", "china", "taiwan", "gaza", "war", "ceasefire",
        "military", "missile", "airstrike", "conflict", "peace talks", "sanction", "sanctions", "strait of hormuz",
        "nato", "united nations", "foreign minister", "supreme leader",
    ),
    "finance_business": (
        "revenue", "earnings", "profit", "guidance", "shares", "stock", "securities", "merger", "acquisition",
        "10-k", "10-q", "8-k", "debt", "bankruptcy", "dividend",
    ),
    "government_policy": (
        "executive order", "rule", "regulation", "policy", "tariff", "budget", "agency", "congress",
    ),
    "legal_courts": (
        "lawsuit", "court", "ruling", "indictment", "complaint", "appeal", "settlement", "verdict", "justice",
    ),
    "elections": (
        "election", "ballot", "vote", "results", "recount", "primary", "candidate", "electoral", "certified",
    ),
    "science_environment": (
        "study", "research", "climate", "hurricane", "earthquake", "wildfire", "emissions", "temperature", "satellite",
    ),
}

IDENTIFIER_RE = re.compile(r"\b(?:NCT\d{8}|mRNA-?\d+[A-Za-z0-9-]*|V\d{2,4}|KEYNOTE-?\d+|[A-Z]{2,}-\d{2,})\b", re.I)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’.-]{2,}")


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = re.sub(r"\s+", " ", value).strip(" ,.;:()[]{}\"'")
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


def _clean_anchor(value: str) -> str:
    """Remove UI/outlet/context-label noise from multi-word context anchors."""
    kept: list[str] = []
    for token in WORD_RE.findall(value or ""):
        normalized = token.lower().strip(".'’-")
        if normalized in NOISE_TERMS:
            continue
        kept.append(token.strip(".'’-"))
    return " ".join(kept)


def _profile_terms(text: str, profile_name: str) -> list[str]:
    lowered = text.lower()
    return [term for term in PROFILE_TERMS.get(profile_name, ()) if term in lowered]


def _fallback_terms(text: str) -> list[str]:
    terms: list[str] = []
    for token in WORD_RE.findall(text):
        lowered = token.lower().strip(".'’-")
        if lowered in NOISE_TERMS or len(lowered) < 4:
            continue
        if token[:1].isupper() or lowered not in {"with", "from", "that", "this", "their", "about"}:
            terms.append(token.strip(".'’-"))
    return _unique(terms)[:8]


def build_provider_query_plan(
    claim_text: str,
    *,
    profile_name: str,
    retrieval_anchors: list[str] | None = None,
    max_queries: int = 3,
) -> dict[str, list[str]]:
    anchors = _unique([cleaned for value in (retrieval_anchors or []) if (cleaned := _clean_anchor(value))])
    identifiers = _unique(IDENTIFIER_RE.findall(" ".join([claim_text] + anchors)))
    entities = [
        value for value in anchors
        if value.lower() not in NOISE_TERMS
        and not IDENTIFIER_RE.fullmatch(value)
        and not re.fullmatch(r"\d+(?:\.\d+)?%?", value)
    ]
    domain_terms = _profile_terms(claim_text + " " + " ".join(anchors), profile_name)
    fallback = _fallback_terms(claim_text)

    def q(*parts: str) -> str:
        return " ".join(_unique([part for part in parts if part]))

    base_entities = entities[:3]
    base_domain = domain_terms[:4]
    base = q(*(base_entities + base_domain)) or q(*fallback[:6])

    plans: dict[str, list[str]] = {}
    generic = _unique([
        q(*(identifiers[:1] + base_domain[:2])),
        base,
        q(*(base_entities[:2] + base_domain[:2])),
        q(*fallback[:6]),
    ])[:max_queries]

    if profile_name == "life_science":
        disease = next((term for term in domain_terms if term in {"melanoma", "cancer", "tumor", "oncology"}), "")
        therapy = next((term for term in domain_terms if term in {"vaccine", "pembrolizumab", "keytruda", "intismeran", "mrna"}), "")
        orgs = base_entities[:2]
        clinical = _unique([
            q(*identifiers[:1], disease),
            q(*orgs, disease),
            q(disease, therapy, "trial"),
        ])[:max_queries]
        pubmed = _unique([
            q(*identifiers[:1], disease),
            q(*orgs, disease, therapy),
            q(disease, therapy, "trial"),
        ])[:max_queries]
        broad = _unique([
            q(*orgs, disease, therapy, "trial"),
            q(*identifiers[:1], disease),
            base,
        ])[:max_queries]
        plans["clinicaltrials_gov"] = clinical or generic
        plans["pubmed"] = pubmed or generic
        plans["official_domain"] = broad or generic
        plans["gdelt"] = broad or generic
        plans["federal_register"] = generic
    elif profile_name == "geopolitics_conflict":
        exact_terms = _unique(_profile_terms(claim_text, profile_name))
        broad = _unique([
            q(*exact_terms[:4]),
            q(*fallback[:6]),
            q(*(base_entities[:2] + exact_terms[:3])),
        ])[:max_queries]
        plans["official_domain"] = broad or generic
        plans["gdelt"] = broad or generic
        plans["federal_register"] = []
        plans["clinicaltrials_gov"] = []
        plans["pubmed"] = []
    else:
        for provider in ("clinicaltrials_gov", "pubmed", "federal_register", "official_domain", "gdelt"):
            plans[provider] = generic

    return plans
