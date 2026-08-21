import re

KNOWN_ENTITIES = (
    "Moderna", "Merck", "MSD", "Pfizer", "Keytruda", "pembrolizumab", "V940", "mRNA-4157",
    "FDA", "NIH", "CDC", "SEC", "DOJ", "EPA", "NASA", "NOAA", "USGS", "Congress",
)
IDENTIFIER_RE = re.compile(r"\b(?:NCT\d{8}|mRNA-?\d+[A-Za-z0-9-]*|V\d{2,4}|KEYNOTE-?\d+|[A-Z]{2,}-\d{2,})\b", re.I)
PROPER_PAIR_RE = re.compile(r"\b(?:[A-Z][A-Za-z'’-]{2,})(?:\s+[A-Z][A-Za-z'’-]{2,}){1,2}\b")
NUMBER_RE = re.compile(r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?%\b")


def extract_retrieval_anchors(*texts: str, limit: int = 14) -> list[str]:
    combined = " ".join(text for text in texts if text)
    anchors: list[str] = []

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", value).strip(" ,.;:()[]{}\"'")
        if value and value.lower() not in {item.lower() for item in anchors}:
            anchors.append(value)

    for entity in KNOWN_ENTITIES:
        if re.search(rf"\b{re.escape(entity)}\b", combined, re.I):
            add(entity)
    for value in IDENTIFIER_RE.findall(combined):
        add(value)
    for value in PROPER_PAIR_RE.findall(combined):
        if value.lower() not in {"Story Title", "Story Source", "Nearby Claim"}:
            add(value)
    for value in NUMBER_RE.findall(combined):
        add(value)

    return anchors[:limit]


def build_anchor_query(*texts: str) -> str:
    anchors = extract_retrieval_anchors(*texts)
    return " ".join(anchors[:10])
