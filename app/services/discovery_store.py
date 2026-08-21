from . import ledger


def save_discovery_leads(*, record_id: str, claim_id: str, leads: list[dict]) -> int:
    """Persist unverified discovery leads only when the claim belongs to the saved record."""
    if not ledger.enabled():
        return 0

    inserted = 0
    with ledger._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM ledger_story_claim WHERE story_id = %s AND claim_id = %s",
                (record_id, claim_id),
            )
            if cur.fetchone() is None:
                raise ValueError("Claim does not belong to the saved record.")

            for lead in leads:
                url = str(lead.get("url") or "").strip()
                label = str(lead.get("title") or lead.get("source_name") or url or "Discovered evidence").strip()
                if not url:
                    continue
                evidence_id = ledger.evidence_public_id(claim_id, url, label)
                note = str(lead.get("note") or "").strip()
                provider = str(lead.get("provider") or "discovery").strip()
                query = str(lead.get("query") or "").strip()
                if provider or query:
                    suffix = f"Discovery provider: {provider}."
                    if query:
                        suffix += f" Query: {query}."
                    note = f"{note} {suffix}".strip()

                cur.execute(
                    """
                    INSERT INTO ledger_evidence(
                        public_id, claim_id, kind, label, url, note, relation,
                        verification_confidence, fetch_status, source_title, source_excerpt, source_sha256
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'unverified_lead', 0, 'not_fetched', %s, NULL, NULL)
                    ON CONFLICT (public_id) DO UPDATE SET
                        kind = EXCLUDED.kind,
                        label = EXCLUDED.label,
                        url = EXCLUDED.url,
                        note = EXCLUDED.note,
                        relation = 'unverified_lead',
                        verification_confidence = 0,
                        fetch_status = CASE
                            WHEN ledger_evidence.fetch_status = 'verified' THEN ledger_evidence.fetch_status
                            ELSE 'not_fetched'
                        END,
                        source_title = COALESCE(ledger_evidence.source_title, EXCLUDED.source_title),
                        updated_at = now()
                    """,
                    (
                        evidence_id,
                        claim_id,
                        lead.get("kind") or "secondary",
                        label[:300],
                        url,
                        note[:1500] if note else None,
                        lead.get("source_name") or label[:300],
                    ),
                )
                inserted += 1
        conn.commit()
    return inserted
