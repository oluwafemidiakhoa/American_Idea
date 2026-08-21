import difflib
import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

CORRECTION_RE = re.compile(
    r"\b(?:correction|corrected|updated|update:|editor(?:'s)? note|clarification|clarified|"
    r"an earlier version|previous version|this story has been updated|we regret the error)\b",
    re.I,
)

DDL = """
CREATE TABLE IF NOT EXISTS ledger_story_observation (
    observation_id bigserial PRIMARY KEY,
    record_id text REFERENCES ledger_story(public_id) ON DELETE SET NULL,
    article_url text NOT NULL,
    observed_sha256 text,
    changed boolean NOT NULL DEFAULT false,
    correction_language_detected boolean NOT NULL DEFAULT false,
    correction_excerpt text,
    observed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_story_observation_url
    ON ledger_story_observation(article_url, observed_at DESC);
"""


def enabled() -> bool:
    return bool(DATABASE_URL and psycopg is not None)


def _connect():
    if not enabled():
        raise RuntimeError("Persistent timeline is not configured.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_timeline() -> bool:
    if not enabled():
        return False
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
    return True


def detect_correction_language(text: str) -> tuple[bool, str | None]:
    match = CORRECTION_RE.search(text or "")
    if not match:
        return False, None
    start = max(0, match.start() - 180)
    end = min(len(text), match.end() + 320)
    excerpt = re.sub(r"\s+", " ", text[start:end]).strip()
    return True, excerpt[:600]


def record_observation(*, record_id: str | None, article_url: str, content_sha256: str | None, changed: bool, text: str) -> None:
    if not enabled():
        return
    correction_detected, correction_excerpt = detect_correction_language(text)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ledger_story_observation(
                    record_id, article_url, observed_sha256, changed,
                    correction_language_detected, correction_excerpt
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (record_id, article_url, content_sha256, changed, correction_detected, correction_excerpt),
            )
        conn.commit()


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def _sentence_chunks(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [re.sub(r"\s+", " ", chunk).strip() for chunk in chunks if len(chunk.strip()) >= 20]


def text_delta(previous: str, current: str, *, limit: int = 8) -> dict[str, Any]:
    before = _sentence_chunks(previous)
    after = _sentence_chunks(current)
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    added: list[str] = []
    removed: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            removed.extend(before[i1:i2])
        if tag in {"replace", "insert"}:
            added.extend(after[j1:j2])

    ratio = matcher.ratio()
    return {
        "similarity": round(ratio, 4),
        "changed": ratio < 0.9999,
        "added_count": len(added),
        "removed_count": len(removed),
        "added": added[:limit],
        "removed": removed[:limit],
    }


def get_timeline(record_id: str) -> dict[str, Any] | None:
    if not enabled():
        return None

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT public_id, url FROM ledger_story WHERE public_id = %s",
                (record_id,),
            )
            seed = cur.fetchone()
            if not seed:
                return None

            normalized = _normalize_url(seed["url"])
            cur.execute(
                """
                SELECT public_id, source_name, url, title, content_sha256, raw_text,
                       captured_at, updated_at
                FROM ledger_story
                WHERE RTRIM(url, '/') = %s
                ORDER BY captured_at ASC, public_id ASC
                """,
                (normalized,),
            )
            versions = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT observation_id, record_id, observed_sha256, changed,
                       correction_language_detected, correction_excerpt, observed_at
                FROM ledger_story_observation
                WHERE RTRIM(article_url, '/') = %s
                ORDER BY observed_at ASC, observation_id ASC
                """,
                (normalized,),
            )
            observations = [dict(row) for row in cur.fetchall()]

    timeline_versions: list[dict[str, Any]] = []
    previous_text: str | None = None
    for index, version in enumerate(versions, start=1):
        correction_detected, correction_excerpt = detect_correction_language(version["raw_text"])
        delta = None if previous_text is None else text_delta(previous_text, version["raw_text"])
        timeline_versions.append(
            {
                "version": index,
                "record_id": version["public_id"],
                "source_name": version["source_name"],
                "article_url": version["url"],
                "title": version["title"],
                "content_sha256": version["content_sha256"],
                "captured_at": _iso(version["captured_at"]),
                "updated_at": _iso(version["updated_at"]),
                "correction_language_detected": correction_detected,
                "correction_excerpt": correction_excerpt,
                "delta_from_previous": delta,
            }
        )
        previous_text = version["raw_text"]

    return {
        "article_url": versions[-1]["url"] if versions else seed["url"],
        "record_id": record_id,
        "version_count": len(timeline_versions),
        "changed_version_count": max(0, len(timeline_versions) - 1),
        "versions": timeline_versions,
        "observations": [
            {
                **row,
                "observed_at": _iso(row["observed_at"]),
            }
            for row in observations
        ],
        "methodology_note": (
            "Story Timeline groups immutable saved snapshots by article URL and compares extracted readable text. "
            "A detected text change is not automatically called a correction. Correction language is flagged only "
            "when the page itself contains explicit update, correction, clarification, or prior-version wording."
        ),
    }


def latest_record_for_url(article_url: str) -> dict[str, Any] | None:
    if not enabled():
        return None
    normalized = _normalize_url(article_url)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT public_id, content_sha256, raw_text, captured_at
                FROM ledger_story
                WHERE RTRIM(url, '/') = %s
                ORDER BY captured_at DESC, public_id DESC
                LIMIT 1
                """,
                (normalized,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def observation_fingerprint(article_url: str, content_sha256: str | None, observed_at: datetime | None = None) -> str:
    timestamp = (observed_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    material = f"{_normalize_url(article_url)}|{content_sha256 or ''}|{timestamp}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:20]


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
