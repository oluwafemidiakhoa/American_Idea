import hashlib
import re
from dataclasses import dataclass, asdict
from typing import Literal

AtomicType = Literal[
    "attribution",
    "quote_fidelity",
    "event_fact",
    "numeric_fact",
    "causal_claim",
    "paraphrase",
    "general_fact",
]

QUOTE_RE = re.compile(r"[\"“‘']([^\"”’']{2,220})[\"”’']")
ATTRIBUTION_RE = re.compile(
    r"\b(?:said|says|told|stated|announced|reported|claimed|wrote|posted|testified|argued|acknowledged|admitted)\b",
    re.I,
)
ATTRIBUTION_SPLIT_RE = re.compile(
    r"^(?P<subject>.+?)\s+(?P<verb>said|says|told|stated|announced|reported|claimed|wrote|posted|testified|argued|acknowledged|admitted)\s+(?P<content>.+)$",
    re.I,
)
NUMBER_RE = re.compile(
    r"(?:\$\s?\d[\d,.]*|\b\d+(?:\.\d+)?%\b|\b\d[\d,.]*\s+(?:people|votes|views|points|days|hours|minutes|dollars|jobs|cases|deaths|miles|percent|million|billion|trillion|patients)\b)",
    re.I,
)
CAUSAL_RE = re.compile(r"\b(?:caused|causes|led to|resulted in|because of|due to|drove|triggered|prevented|reduced|increased)\b", re.I)
EVENT_RE = re.compile(r"\b(?:debate|hearing|interview|speech|press conference|meeting|vote|election|trial|filing|ruling|announcement)\b", re.I)
PARAPHRASE_CUES = re.compile(r"\b(?:about whether|meaning that|in other words|effectively|amounted to|which means)\b", re.I)


CONTRACTS = {
    "attribution": {
        "name": "source_of_record_attribution",
        "minimum": "A source-of-record showing the speaker made the attributed statement; independent repetition may corroborate but cannot substitute when a recording/transcript exists.",
        "preferred_sources": ["recording", "official transcript", "event transcript", "first-party written statement"],
        "independent_corroboration_required": False,
    },
    "quote_fidelity": {
        "name": "verbatim_or_faithful_quote",
        "minimum": "The quoted wording must appear verbatim or with only immaterial transcription differences in a source-of-record.",
        "preferred_sources": ["recording", "official transcript", "full interview transcript"],
        "independent_corroboration_required": False,
    },
    "event_fact": {
        "name": "event_occurrence",
        "minimum": "A contemporaneous or authoritative record establishing that the described event occurred, with independent corroboration when material details are disputed.",
        "preferred_sources": ["official event record", "recording", "transcript", "authoritative filing", "independent contemporaneous report"],
        "independent_corroboration_required": True,
    },
    "numeric_fact": {
        "name": "authoritative_numeric_fact",
        "minimum": "A source that directly reports the same quantity, date, denominator, unit, and scope; transformed figures must expose the calculation.",
        "preferred_sources": ["official dataset", "filing", "registry", "audited report", "primary table"],
        "independent_corroboration_required": False,
    },
    "causal_claim": {
        "name": "causal_evidence",
        "minimum": "Evidence must establish causation rather than temporal sequence or correlation. A quotation that asserts causation proves only that the speaker made the assertion.",
        "preferred_sources": ["controlled study", "causal analysis", "adjudicated factual record", "multiple convergent primary sources"],
        "independent_corroboration_required": True,
    },
    "paraphrase": {
        "name": "paraphrase_fidelity",
        "minimum": "The publisher's paraphrase must preserve the meaning, scope, modality, and qualifiers of the source-of-record without adding a stronger proposition.",
        "preferred_sources": ["recording", "transcript", "original statement", "source document"],
        "independent_corroboration_required": False,
    },
    "general_fact": {
        "name": "general_factual_support",
        "minimum": "A directly relevant source must support the proposition; high-impact claims require a primary source plus independent corroboration.",
        "preferred_sources": ["primary source", "authoritative record", "independent report"],
        "independent_corroboration_required": True,
    },
}


@dataclass
class AtomicClaim:
    id: str
    text: str
    atomic_type: AtomicType
    status: str
    evidence_contract: dict
    source_span: str
    subject: str | None = None
    predicate: str | None = None
    quoted_text: str | None = None
    parent_claim_id: str | None = None
    decomposition_reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _stable_id(parent_claim_id: str, atomic_type: str, text: str) -> str:
    material = f"{parent_claim_id}|{atomic_type}|{_normalize(text).lower()}".encode("utf-8")
    return f"atom_{hashlib.sha256(material).hexdigest()[:14]}"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip(" \t\n\r,;:-")


def _make_atom(
    parent_claim_id: str,
    text: str,
    atomic_type: AtomicType,
    *,
    source_span: str,
    subject: str | None = None,
    predicate: str | None = None,
    quoted_text: str | None = None,
    reason: str,
) -> AtomicClaim:
    text = _normalize(text)
    return AtomicClaim(
        id=_stable_id(parent_claim_id, atomic_type, text),
        text=text,
        atomic_type=atomic_type,
        status="unresolved",
        evidence_contract=dict(CONTRACTS[atomic_type]),
        source_span=_normalize(source_span),
        subject=_normalize(subject) if subject else None,
        predicate=_normalize(predicate) if predicate else None,
        quoted_text=_normalize(quoted_text) if quoted_text else None,
        parent_claim_id=parent_claim_id,
        decomposition_reason=reason,
    )


def _dedupe(atoms: list[AtomicClaim]) -> list[AtomicClaim]:
    out: list[AtomicClaim] = []
    seen: set[tuple[str, str]] = set()
    for atom in atoms:
        key = (atom.atomic_type, _normalize(atom.text).lower())
        if not atom.text or key in seen:
            continue
        seen.add(key)
        out.append(atom)
    return out


def compile_atomic_claims(parent_claim_id: str, sentence: str) -> dict:
    """Compile one newsroom sentence into independently verifiable propositions.

    This function does not determine truth. It only determines what must be verified and which
    evidence contract applies. The original sentence is always preserved as source_span.
    """
    source = _normalize(sentence)
    atoms: list[AtomicClaim] = []
    integrity_flags: list[str] = []

    quotes = [_normalize(value) for value in QUOTE_RE.findall(source) if _normalize(value)]
    attribution_match = ATTRIBUTION_SPLIT_RE.match(source)

    if attribution_match:
        subject = _normalize(attribution_match.group("subject"))
        verb = _normalize(attribution_match.group("verb"))
        content = _normalize(attribution_match.group("content"))
        attributed_text = quotes[0] if quotes else content
        atoms.append(
            _make_atom(
                parent_claim_id,
                f"{subject} {verb} {attributed_text}",
                "attribution",
                source_span=source,
                subject=subject,
                predicate=verb,
                quoted_text=quotes[0] if quotes else None,
                reason="Separated the speech act from the truth of the attributed content.",
            )
        )

    if quotes:
        for quote in quotes[:3]:
            atoms.append(
                _make_atom(
                    parent_claim_id,
                    quote,
                    "quote_fidelity",
                    source_span=source,
                    quoted_text=quote,
                    reason="Quoted wording requires source-of-record fidelity verification.",
                )
            )
        if len(quotes) > 1:
            integrity_flags.append("multiple_quoted_spans")

    # Publisher wording outside quotes can contain a distinct proposition that must not inherit
    # verification from the quote itself.
    outside_quotes = _normalize(QUOTE_RE.sub(" ", source))
    if quotes and outside_quotes:
        if PARAPHRASE_CUES.search(outside_quotes) or len(outside_quotes.split()) >= 8:
            atoms.append(
                _make_atom(
                    parent_claim_id,
                    outside_quotes,
                    "paraphrase",
                    source_span=source,
                    reason="Publisher wording outside the direct quote is a separate proposition and requires fidelity checking.",
                )
            )
            integrity_flags.append("quote_plus_publisher_paraphrase")

    if NUMBER_RE.search(source):
        atoms.append(
            _make_atom(
                parent_claim_id,
                source,
                "numeric_fact",
                source_span=source,
                reason="Quantitative content requires an authoritative numeric evidence contract.",
            )
        )

    if CAUSAL_RE.search(source):
        atoms.append(
            _make_atom(
                parent_claim_id,
                source,
                "causal_claim",
                source_span=source,
                reason="Causal wording requires evidence stronger than attribution or temporal association.",
            )
        )
        integrity_flags.append("causal_language")

    if EVENT_RE.search(source) and not any(atom.atomic_type == "event_fact" for atom in atoms):
        atoms.append(
            _make_atom(
                parent_claim_id,
                source,
                "event_fact",
                source_span=source,
                reason="The sentence describes an event or event detail that can be verified independently of commentary.",
            )
        )

    if not atoms:
        atom_type: AtomicType = "attribution" if ATTRIBUTION_RE.search(source) else "general_fact"
        atoms.append(
            _make_atom(
                parent_claim_id,
                source,
                atom_type,
                source_span=source,
                reason="Single factual proposition; no safe deterministic split was found.",
            )
        )

    atoms = _dedupe(atoms)
    if len(atoms) > 1:
        integrity_flags.append("compound_claim")

    return {
        "parent_claim_id": parent_claim_id,
        "source_sentence": source,
        "atomic_claims": [atom.to_dict() for atom in atoms],
        "atomic_claim_count": len(atoms),
        "integrity_flags": sorted(set(integrity_flags)),
        "aggregate_status": "unresolved",
        "methodology_note": (
            "Atomic Claim Provenance separates independently verifiable propositions before evidence discovery. "
            "No atomic claim inherits a truth status from another atom or from the parent newsroom sentence."
        ),
    }
