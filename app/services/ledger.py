import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

DDL = """
CREATE TABLE IF NOT EXISTS ledger_story (
    public_id text PRIMARY KEY,
    source_name text,
    url text NOT NULL,
    title text,
    content_sha256 text NOT NULL UNIQUE,
    raw_text text NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ledger_claim (
    public_id text PRIMARY KEY,
    canonical_text text NOT NULL,
    status text NOT NULL DEFAULT 'unresolved',
    extraction_confidence numeric(6,5),
    why_flagged jsonb NOT NULL DEFAULT '[]'::jsonb,
    status_basis text,
    first_observed_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ledger_story_claim (
    story_id text NOT NULL REFERENCES ledger_story(public_id) ON DELETE CASCADE,
    claim_id text NOT NULL REFERENCES ledger_claim(public_id) ON DELETE CASCADE,
    ordinal integer NOT NULL DEFAULT 0,
    PRIMARY KEY (story_id, claim_id)
);

CREATE TABLE IF NOT EXISTS ledger_evidence (
    public_id text PRIMARY KEY,
    claim_id text NOT NULL REFERENCES ledger_claim(public_id) ON DELETE CASCADE,
    kind text NOT NULL,
    label text NOT NULL,
    url text,
    note text,
    relation text NOT NULL DEFAULT 'unverified_lead',
    verification_confidence numeric(6,5) NOT NULL DEFAULT 0,
    fetch_status text NOT NULL DEFAULT 'not_fetched',
    source_title text,
    source_excerpt text,
    source_sha256 text,
    first_observed_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ledger_claim_revision (
    revision_id bigserial PRIMARY KEY,
    claim_id text NOT NULL REFERENCES ledger_claim(public_id) ON DELETE CASCADE,
    previous_status text,
    new_status text NOT NULL,
    reason text NOT NULL,
    methodology_version text NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ledger_story_url ON ledger_story(url);
CREATE INDEX IF NOT EXISTS idx_ledger_claim_status ON ledger_claim(status);
CREATE INDEX IF NOT EXISTS idx_ledger_story_claim_story ON ledger_story_claim(story_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_ledger_evidence_claim ON ledger_evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_ledger_revision_claim ON ledger_claim_revision(claim_id, changed_at DESC);
"""


def enabled() -> bool:
    return bool(DATABASE_URL and psycopg is not None)


def _connect():
    if not enabled():
        raise RuntimeError("Persistent ledger is not configured.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_ledger() -> bool:
    if not enabled():
        return False
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
    return True


def story_public_id(content_sha256: str) -> str:
    return f"ai_{content_sha256[:16]}"


def evidence_public_id(claim_id: str, url: str | None, label: str) -> str:
    material = f"{claim_id}|{url or ''}|{label}".encode("utf-8")
    return f"ev_{hashlib.sha256(material).hexdigest()[:16]}"


def save_story_analysis(*, article: Any, claims: list[dict]) -> str | None:
    """Persist an ingested story and synchronize its active extraction view.

    The content-addressed story snapshot stays stable. Re-analysis replaces only the story-to-claim
    membership for the current extraction methodology; historical claim rows/revisions remain auditable.
    """
    if not enabled():
        return None

    record_id = story_public_id(article.content_sha256)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ledger_story(public_id, source_name, url, title, content_sha256, raw_text)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (public_id) DO UPDATE SET
                    source_name = EXCLUDED.source_name,
                    url = EXCLUDED.url,
                    title = EXCLUDED.title,
                    raw_text = EXCLUDED.raw_text,
                    updated_at = now()
                """,
                (record_id, article.source_name, article.final_url, article.title, article.content_sha256, article.text),
            )

            # A deterministic content snapshot can be re-analyzed by a newer extractor. Keep old
            # claim rows/revisions for audit history, but do not keep stale claims in the active view.
            cur.execute("DELETE FROM ledger_story_claim WHERE story_id = %s", (record_id,))

            for ordinal, claim in enumerate(claims):
                _upsert_claim(cur, claim)
                cur.execute(
                    """
                    INSERT INTO ledger_story_claim(story_id, claim_id, ordinal)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (story_id, claim_id) DO UPDATE SET ordinal = EXCLUDED.ordinal
                    """,
                    (record_id, claim["id"], ordinal),
                )
                _upsert_evidence(cur, claim)
        conn.commit()
    return record_id


def save_verification(*, article_url: str, claims: list[dict], methodology_version: str = "0.8.0") -> int:
    if not enabled():
        return 0

    revisions = 0
    with _connect() as conn:
        with conn.cursor() as cur:
            for claim in claims:
                cur.execute("SELECT status FROM ledger_claim WHERE public_id = %s", (claim["id"],))
                row = cur.fetchone()
                previous_status = row["status"] if row else None
                _upsert_claim(cur, claim)
                _upsert_evidence(cur, claim)
                new_status = claim.get("status", "unresolved")
                if previous_status is not None and previous_status != new_status:
                    cur.execute(
                        """
                        INSERT INTO ledger_claim_revision(
                            claim_id, previous_status, new_status, reason, methodology_version
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            claim["id"], previous_status, new_status,
                            claim.get("status_basis") or "Automated verification changed the claim status.",
                            methodology_version,
                        ),
                    )
                    revisions += 1
        conn.commit()
    return revisions


def _upsert_claim(cur, claim: dict) -> None:
    cur.execute(
        """
        INSERT INTO ledger_claim(
            public_id, canonical_text, status, extraction_confidence, why_flagged, status_basis
        ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (public_id) DO UPDATE SET
            canonical_text = EXCLUDED.canonical_text,
            status = EXCLUDED.status,
            extraction_confidence = EXCLUDED.extraction_confidence,
            why_flagged = EXCLUDED.why_flagged,
            status_basis = EXCLUDED.status_basis,
            updated_at = now()
        """,
        (
            claim["id"], claim["text"], claim.get("status", "unresolved"),
            claim.get("confidence"), json.dumps(claim.get("why_flagged", [])), claim.get("status_basis"),
        ),
    )


def _upsert_evidence(cur, claim: dict) -> None:
    for item in claim.get("evidence", []):
        eid = evidence_public_id(claim["id"], item.get("url"), item.get("label", ""))
        cur.execute(
            """
            INSERT INTO ledger_evidence(
                public_id, claim_id, kind, label, url, note, relation,
                verification_confidence, fetch_status, source_title, source_excerpt, source_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (public_id) DO UPDATE SET
                kind = EXCLUDED.kind,
                label = EXCLUDED.label,
                url = EXCLUDED.url,
                note = EXCLUDED.note,
                relation = EXCLUDED.relation,
                verification_confidence = EXCLUDED.verification_confidence,
                fetch_status = EXCLUDED.fetch_status,
                source_title = EXCLUDED.source_title,
                source_excerpt = EXCLUDED.source_excerpt,
                source_sha256 = EXCLUDED.source_sha256,
                updated_at = now()
            """,
            (
                eid, claim["id"], item.get("kind", "context"),
                item.get("label") or item.get("url") or "Evidence", item.get("url"), item.get("note"),
                item.get("relation", "unverified_lead"), item.get("verification_confidence", 0.0),
                item.get("fetch_status", "not_fetched"), item.get("source_title"), item.get("source_excerpt"),
                item.get("source_sha256"),
            ),
        )


def get_record(record_id: str) -> dict | None:
    if not enabled():
        return None

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT public_id, source_name, url, title, content_sha256, captured_at, updated_at
                FROM ledger_story WHERE public_id = %s
                """,
                (record_id,),
            )
            story = cur.fetchone()
            if not story:
                return None

            cur.execute(
                """
                SELECT c.public_id, c.canonical_text, c.status, c.extraction_confidence,
                       c.why_flagged, c.status_basis, sc.ordinal
                FROM ledger_story_claim sc
                JOIN ledger_claim c ON c.public_id = sc.claim_id
                WHERE sc.story_id = %s
                ORDER BY sc.ordinal, c.public_id
                """,
                (record_id,),
            )
            claims = []
            for row in cur.fetchall():
                claim = {
                    "id": row["public_id"], "text": row["canonical_text"], "status": row["status"],
                    "confidence": float(row["extraction_confidence"] or 0), "why_flagged": row["why_flagged"] or [],
                    "status_basis": row["status_basis"], "evidence": [], "revisions": [],
                }
                cur.execute(
                    """
                    SELECT kind, label, url, note, relation, verification_confidence,
                           fetch_status, source_title, source_excerpt, source_sha256
                    FROM ledger_evidence WHERE claim_id = %s ORDER BY first_observed_at
                    """,
                    (claim["id"],),
                )
                for item in cur.fetchall():
                    item = dict(item)
                    item["verification_confidence"] = float(item["verification_confidence"] or 0)
                    claim["evidence"].append(item)
                cur.execute(
                    """
                    SELECT previous_status, new_status, reason, methodology_version, changed_at
                    FROM ledger_claim_revision WHERE claim_id = %s ORDER BY changed_at
                    """,
                    (claim["id"],),
                )
                claim["revisions"] = [dict(item) for item in cur.fetchall()]
                claims.append(claim)

    return {
        "record_id": story["public_id"],
        "source_name": story["source_name"],
        "article_url": story["url"],
        "title": story["title"],
        "content_sha256": story["content_sha256"],
        "captured_at": _iso(story["captured_at"]),
        "updated_at": _iso(story["updated_at"]),
        "claims": claims,
        "factual_claim_count": len(claims),
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)
