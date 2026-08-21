import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceProfile:
    name: str
    official_domains: tuple[str, ...] = ()
    use_clinical_trials: bool = False
    use_pubmed: bool = False
    use_federal_register: bool = False


PROFILE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "life_science",
        re.compile(
            r"\b(?:clinical trial|phase\s*[123]|patient|patients|melanoma|cancer|tumou?r|vaccine|therapy|drug|"
            r"medicine|pembrolizumab|keytruda|intismeran|mrna|recurrence|metastasis|survival|endpoint|fda|nih|"
            r"clinicaltrials\.gov|oncology|immunotherapy|disease|pharma|pharmaceutical)\b",
            re.I,
        ),
    ),
    (
        "geopolitics_conflict",
        re.compile(
            r"\b(?:iran|iranian|israel|israeli|ukraine|ukrainian|russia|russian|china|chinese|taiwan|gaza|"
            r"war|ceasefire|hostilities|military|missile|airstrike|strike|invasion|conflict|peace talks|diplomat|"
            r"diplomatic|foreign minister|supreme leader|strait of hormuz|nato|united nations|sanctions?|"
            r"troops?|armed forces|defense ministry|foreign policy)\b",
            re.I,
        ),
    ),
    (
        "finance_business",
        re.compile(
            r"\b(?:earnings|revenue|profit|loss|guidance|shares|stock|securities|merger|acquisition|ipo|"
            r"sec|10-k|10-q|8-k|investor|quarter|fiscal|bankruptcy|bond|debt|dividend|market cap)\b",
            re.I,
        ),
    ),
    (
        "government_policy",
        re.compile(
            r"\b(?:white house|congress|senate|house of representatives|department|agency|federal|"
            r"regulation|rule|executive order|administration|secretary|policy|tariff|budget|government)\b",
            re.I,
        ),
    ),
    (
        "legal_courts",
        re.compile(
            r"\b(?:court|judge|lawsuit|litigation|indictment|charged|convicted|appeal|supreme court|district court|"
            r"attorney general|department of justice|doj|settlement|ruling|verdict|complaint|prosecutor)\b",
            re.I,
        ),
    ),
    (
        "elections",
        re.compile(
            r"\b(?:election|ballot|vote|votes|voter|polling place|primary|runoff|candidate|campaign|electoral|"
            r"secretary of state|election commission|certified results|recount)\b",
            re.I,
        ),
    ),
    (
        "science_environment",
        re.compile(
            r"\b(?:study|research|scientists|climate|weather|hurricane|earthquake|wildfire|temperature|emissions|"
            r"nasa|noaa|usgs|environment|epa|space|satellite|experiment|peer reviewed|journal)\b",
            re.I,
        ),
    ),
)


BASE_PROFILES = {
    "life_science": SourceProfile(
        name="life_science",
        official_domains=("fda.gov", "nih.gov", "cdc.gov"),
        use_clinical_trials=True,
        use_pubmed=True,
        use_federal_register=False,
    ),
    "geopolitics_conflict": SourceProfile(
        name="geopolitics_conflict",
        official_domains=("state.gov", "treasury.gov", "defense.gov", "whitehouse.gov", "un.org", "president.ir"),
        use_federal_register=False,
    ),
    "finance_business": SourceProfile(
        name="finance_business",
        official_domains=("sec.gov", "ftc.gov", "justice.gov"),
        use_federal_register=False,
    ),
    "government_policy": SourceProfile(
        name="government_policy",
        official_domains=("whitehouse.gov", "congress.gov", "govinfo.gov", "gao.gov"),
        use_federal_register=True,
    ),
    "legal_courts": SourceProfile(
        name="legal_courts",
        official_domains=("supremecourt.gov", "uscourts.gov", "justice.gov"),
        use_federal_register=False,
    ),
    "elections": SourceProfile(
        name="elections",
        official_domains=("fec.gov", "eac.gov"),
        use_federal_register=False,
    ),
    "science_environment": SourceProfile(
        name="science_environment",
        official_domains=("nasa.gov", "noaa.gov", "usgs.gov", "epa.gov", "nsf.gov"),
        use_pubmed=True,
        use_federal_register=False,
    ),
    "general": SourceProfile(name="general", official_domains=(), use_federal_register=False),
}

ENTITY_DOMAINS = {
    "moderna": ("modernatx.com",),
    "merck": ("merck.com",),
    "msd": ("merck.com",),
    "pfizer": ("pfizer.com",),
    "johnson & johnson": ("jnj.com",),
    "jpmorgan": ("jpmorganchase.com",),
    "goldman sachs": ("goldmansachs.com",),
    "microsoft": ("microsoft.com",),
    "apple": ("apple.com",),
    "google": ("blog.google", "abc.xyz"),
    "alphabet": ("abc.xyz",),
    "meta": ("about.fb.com",),
    "amazon": ("aboutamazon.com",),
    "tesla": ("tesla.com",),
}

FEDERAL_REGISTER_CUES = re.compile(
    r"\b(?:federal register|final rule|proposed rule|regulation|regulatory|rulemaking|medicare|medicaid|cms|"
    r"federal policy|agency rule|code of federal regulations|cfr)\b",
    re.I,
)


def classify_claim_domain(text: str) -> str:
    value = text or ""
    for name, pattern in PROFILE_PATTERNS:
        if pattern.search(value):
            return name
    return "general"


def source_profile_for_claim(text: str) -> SourceProfile:
    domain = classify_claim_domain(text)
    base = BASE_PROFILES[domain]
    domains = list(base.official_domains)
    lowered = (text or "").lower()

    for entity, values in ENTITY_DOMAINS.items():
        if re.search(rf"\b{re.escape(entity)}\b", lowered):
            for value in values:
                if value not in domains:
                    domains.append(value)

    use_federal_register = base.use_federal_register and bool(FEDERAL_REGISTER_CUES.search(text or ""))

    return SourceProfile(
        name=base.name,
        official_domains=tuple(domains),
        use_clinical_trials=base.use_clinical_trials,
        use_pubmed=base.use_pubmed,
        use_federal_register=use_federal_register,
    )


def is_life_science_claim(text: str) -> bool:
    return classify_claim_domain(text) == "life_science"


def official_domains_for_claim(text: str) -> list[str]:
    return list(source_profile_for_claim(text).official_domains)
