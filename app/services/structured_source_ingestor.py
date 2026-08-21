import hashlib
import re
import xml.etree.ElementTree as ET

import httpx

from .url_ingestor import ArticleBlock, IngestedArticle, IngestionError

NCT_URL_RE = re.compile(r"clinicaltrials\.gov/study/(NCT\d{8})", re.I)
PUBMED_URL_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?", re.I)


def _article(*, url: str, title: str, source_name: str, blocks: list[str], content_type: str) -> IngestedArticle:
    cleaned = [re.sub(r"\s+", " ", value).strip() for value in blocks if value and value.strip()]
    text = "\n\n".join(cleaned)
    if len(text) < 80:
        raise IngestionError("The structured source did not contain enough usable evidence fields.")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return IngestedArticle(
        requested_url=url,
        final_url=url,
        title=title,
        source_name=source_name,
        text=text[:100_000],
        content_sha256=digest,
        content_type=content_type,
        blocks=[ArticleBlock(text=value, links=[]) for value in cleaned],
    )


def ingest_clinical_trial(url: str, *, timeout_seconds: float = 8.0) -> IngestedArticle:
    match = NCT_URL_RE.search(url)
    if not match:
        raise IngestionError("ClinicalTrials.gov URL did not contain an NCT identifier.")
    nct_id = match.group(1).upper()
    endpoint = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    try:
        response = httpx.get(endpoint, timeout=timeout_seconds, headers={"User-Agent": "AmericanIdeaEvidence/1.6"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise IngestionError("ClinicalTrials.gov structured record could not be fetched.") from exc

    protocol = payload.get("protocolSection") or {}
    ident = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    conditions = protocol.get("conditionsModule") or {}
    arms = protocol.get("armsInterventionsModule") or {}
    outcomes = protocol.get("outcomesModule") or {}
    sponsor = protocol.get("sponsorCollaboratorsModule") or {}
    results = payload.get("resultsSection") or {}

    title = str(ident.get("officialTitle") or ident.get("briefTitle") or nct_id)
    sponsor_name = str((sponsor.get("leadSponsor") or {}).get("name") or "ClinicalTrials.gov")
    enrollment = design.get("enrollmentInfo") or {}
    phases = design.get("phases") or []
    interventions = [
        str(item.get("name") or "")
        for item in (arms.get("interventions") or [])
        if item.get("name")
    ]
    collaborators = [
        str(item.get("name") or "")
        for item in (sponsor.get("collaborators") or [])
        if item.get("name")
    ]

    blocks = [
        f"ClinicalTrials.gov identifier: {nct_id}. Title: {title}.",
        f"Lead sponsor: {sponsor_name}. Collaborators: {', '.join(collaborators) or 'not listed'}.",
        f"Study phase: {', '.join(phases) or 'not listed'}. Enrollment: {enrollment.get('count') or 'not listed'} {enrollment.get('type') or ''}.",
        f"Conditions: {', '.join(conditions.get('conditions') or []) or 'not listed'}.",
        f"Interventions: {', '.join(interventions) or 'not listed'}.",
        f"Overall status: {status.get('overallStatus') or 'not listed'}.",
    ]
    for outcome in (outcomes.get("primaryOutcomes") or [])[:4]:
        blocks.append(
            "Primary outcome: "
            + " | ".join(
                str(outcome.get(key) or "")
                for key in ("measure", "description", "timeFrame")
                if outcome.get(key)
            )
        )
    if results:
        blocks.append("ClinicalTrials.gov results section is present for this record.")

    return _article(
        url=f"https://clinicaltrials.gov/study/{nct_id}",
        title=title,
        source_name="ClinicalTrials.gov",
        blocks=blocks,
        content_type="application/json",
    )


def ingest_pubmed(url: str, *, timeout_seconds: float = 8.0) -> IngestedArticle:
    match = PUBMED_URL_RE.search(url)
    if not match:
        raise IngestionError("PubMed URL did not contain a PMID.")
    pmid = match.group(1)
    endpoint = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    try:
        response = httpx.get(
            endpoint,
            params={"db": "pubmed", "id": pmid, "retmode": "xml"},
            timeout=timeout_seconds,
            headers={"User-Agent": "AmericanIdeaEvidence/1.6"},
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except (httpx.HTTPError, ET.ParseError) as exc:
        raise IngestionError("PubMed structured record could not be fetched.") from exc

    article = root.find(".//PubmedArticle")
    if article is None:
        raise IngestionError("PubMed did not return an article record.")

    title_node = article.find(".//ArticleTitle")
    title = "".join(title_node.itertext()).strip() if title_node is not None else f"PubMed {pmid}"
    abstract_parts = []
    for node in article.findall(".//Abstract/AbstractText"):
        text = "".join(node.itertext()).strip()
        label = node.attrib.get("Label")
        if text:
            abstract_parts.append(f"{label}: {text}" if label else text)
    journal_node = article.find(".//Journal/Title")
    journal = "".join(journal_node.itertext()).strip() if journal_node is not None else "PubMed"
    authors = []
    for author in article.findall(".//Author")[:8]:
        family = author.findtext("LastName") or ""
        given = author.findtext("ForeName") or ""
        name = " ".join(part for part in (given, family) if part).strip()
        if name:
            authors.append(name)

    blocks = [
        f"PubMed PMID: {pmid}. Title: {title}.",
        f"Journal: {journal}. Authors: {', '.join(authors) or 'not listed'}.",
    ] + abstract_parts

    return _article(
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        title=title,
        source_name="PubMed",
        blocks=blocks,
        content_type="application/xml",
    )


def ingest_structured_source(url: str, *, timeout_seconds: float = 8.0) -> IngestedArticle | None:
    if NCT_URL_RE.search(url):
        return ingest_clinical_trial(url, timeout_seconds=timeout_seconds)
    if PUBMED_URL_RE.search(url):
        return ingest_pubmed(url, timeout_seconds=timeout_seconds)
    return None
