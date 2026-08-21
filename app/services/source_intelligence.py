import re

LIFE_SCIENCE_RE = re.compile(
    r"\b(?:clinical trial|phase\s*[123]|trial|patient|patients|melanoma|cancer|tumou?r|vaccine|therapy|drug|"
    r"medicine|pembrolizumab|keytruda|intismeran|mrna|recurrence|metastasis|survival|endpoint|fda|nih|"
    r"clinicaltrials\.gov|oncology|immunotherapy)\b",
    re.I,
)

# These domains are issuer-controlled sources. They are primary for statements made by the
# named organization, but they are not automatically independent corroboration of efficacy.
ORGANIZATION_DOMAINS = {
    "moderna": ("modernatx.com",),
    "merck": ("merck.com",),
    "msd": ("merck.com",),
}


def is_life_science_claim(text: str) -> bool:
    return bool(LIFE_SCIENCE_RE.search(text or ""))


def official_domains_for_claim(text: str) -> list[str]:
    lowered = (text or "").lower()
    domains: list[str] = []
    for organization, values in ORGANIZATION_DOMAINS.items():
        if re.search(rf"\b{re.escape(organization)}\b", lowered):
            for domain in values:
                if domain not in domains:
                    domains.append(domain)
    return domains
