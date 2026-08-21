import json

from . import ledger

ATOMIC_DDL = """
CREATE TABLE IF NOT EXISTS ledger_atomic_claim (
    story_id text NOT NULL REFERENCES ledger_story(public_id) ON DELETE CASCADE,
    parent_claim_id text NOT NULL REFERENCES ledger_claim(public_id) ON DELETE CASCADE,
    atomic_id text NOT NULL,
    ordinal integer NOT NULL DEFAULT 0,
    atomic_type text NOT NULL,
    atomic_text text NOT NULL,
    status text NOT NULL DEFAULT 'unresolved',
    evidence_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_span text NOT NULL,
    subject text,
    predicate text,
    quoted_text text,
    decomposition_reason text,
    first_observed_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (story_id, parent_claim_id, atomic_id)
);

CREATE TABLE IF NOT EXISTS ledger_claim_integrity (
    story_id text NOT NULL REFERENCES ledger_story(public_id) ON DELETE CASCADE,
    parent_claim_id text NOT NULL REFERENCES ledger_claim(public_id) ON DELETE CASCADE,
    aggregate_status text NOT NULL DEFAULT 'unresolved',
    integrity_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
    atomic_claim_count integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (story_id, parent_claim_id)
);

CREATE INDEX IF NOT EXISTS idx_atomic_story_claim ON ledger_atomic_claim(story_id, parent_claim_id, ordinal);
"""


def init_atomic_ledger() -> bool:
    if not ledger.enabled():
        return False
    with ledger._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(ATOMIC_DDL)
        conn.commit()
    return True


def save_atomic_claims(*, record_id: str, claims: list[dict]) -> int:
    if not ledger.enabled():
        return 0
    saved = 0
    with ledger._connect() as conn:
        with conn.cursor() as cur:
            for claim in claims:
                claim_id = str(claim.get("id") or "")
                if not claim_id:
                    continue
                cur.execute(
                    "DELETE FROM ledger_atomic_claim WHERE story_id = %s AND parent_claim_id = %s",
                    (record_id, claim_id),
                )
                atoms = list(claim.get("atomic_claims") or [])
                for ordinal, atom in enumerate(atoms):
                    cur.execute(
                        """
                        INSERT INTO ledger_atomic_claim(
                            story_id, parent_claim_id, atomic_id, ordinal, atomic_type, atomic_text, status,
                            evidence_contract, source_span, subject, predicate, quoted_text, decomposition_reason
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                        """,
                        (
                            record_id,
                            claim_id,
                            atom.get("id"),
                            ordinal,
                            atom.get("atomic_type") or "general_fact",
                            atom.get("text") or "",
                            atom.get("status") or "unresolved",
                            json.dumps(atom.get("evidence_contract") or {}),
                            atom.get("source_span") or claim.get("text") or "",
                            atom.get("subject"),
                            atom.get("predicate"),
                            atom.get("quoted_text"),
                            atom.get("decomposition_reason"),
                        ),
                    )
                    saved += 1
                cur.execute(
                    """
                    INSERT INTO ledger_claim_integrity(
                        story_id, parent_claim_id, aggregate_status, integrity_flags, atomic_claim_count
                    ) VALUES (%s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (story_id, parent_claim_id) DO UPDATE SET
                        aggregate_status = EXCLUDED.aggregate_status,
                        integrity_flags = EXCLUDED.integrity_flags,
                        atomic_claim_count = EXCLUDED.atomic_claim_count,
                        updated_at = now()
                    """,
                    (
                        record_id,
                        claim_id,
                        claim.get("aggregate_status") or "unresolved",
                        json.dumps(claim.get("integrity_flags") or []),
                        len(atoms),
                    ),
                )
        conn.commit()
    return saved


def hydrate_atomic_claims(record: dict | None) -> dict | None:
    if record is None or not ledger.enabled():
        return record
    record_id = str(record.get("record_id") or "")
    if not record_id:
        return record

    by_claim: dict[str, list[dict]] = {}
    integrity: dict[str, dict] = {}
    with ledger._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT parent_claim_id, atomic_id, atomic_type, atomic_text, status, evidence_contract,
                       source_span, subject, predicate, quoted_text, decomposition_reason
                FROM ledger_atomic_claim
                WHERE story_id = %s
                ORDER BY parent_claim_id, ordinal
                """,
                (record_id,),
            )
            for row in cur.fetchall():
                by_claim.setdefault(row["parent_claim_id"], []).append(
                    {
                        "id": row["atomic_id"],
                        "text": row["atomic_text"],
                        "atomic_type": row["atomic_type"],
                        "status": row["status"],
                        "evidence_contract": row["evidence_contract"] or {},
                        "source_span": row["source_span"],
                        "subject": row["subject"],
                        "predicate": row["predicate"],
                        "quoted_text": row["quoted_text"],
                        "parent_claim_id": row["parent_claim_id"],
                        "decomposition_reason": row["decomposition_reason"],
                    }
                )
            cur.execute(
                """
                SELECT parent_claim_id, aggregate_status, integrity_flags, atomic_claim_count
                FROM ledger_claim_integrity WHERE story_id = %s
                """,
                (record_id,),
            )
            for row in cur.fetchall():
                integrity[row["parent_claim_id"]] = dict(row)

    for claim in record.get("claims", []):
        claim_id = claim.get("id")
        claim["atomic_claims"] = by_claim.get(claim_id, [])
        meta = integrity.get(claim_id, {})
        claim["atomic_claim_count"] = int(meta.get("atomic_claim_count") or len(claim["atomic_claims"]))
        claim["integrity_flags"] = meta.get("integrity_flags") or []
        claim["aggregate_status"] = meta.get("aggregate_status") or "unresolved"
    return record
