# American Idea Evidence — MVP 0.8

**American Idea Evidence** is a public evidence layer for news and public claims.

Public StoryLens:

`https://oluwafemidiakhoa.github.io/American_Idea/`

Public API:

`https://americanidea-production.up.railway.app`

## What works now

- Paste a public news URL into StoryLens.
- Securely fetch readable article HTML on the FastAPI backend.
- Fingerprint extracted article text with SHA-256.
- Extract candidate factual claims with stable claim IDs.
- Preserve article hyperlinks as source-linked evidence leads.
- Fetch a limited number of evidence leads on demand.
- Fingerprint fetched evidence pages and find the most relevant passage.
- Classify evidence relationships conservatively as `supports`, `contradicts`, `contextualizes`, or `mentions`.
- Keep evidence confidence separate from claim truth status.
- Require strong and independent evidence before stronger status transitions.
- Optionally persist story snapshots, claims, evidence state, and status revisions in PostgreSQL.
- Retrieve a persisted public record with `GET /api/records/{record_id}`.

The system is deliberately evidence-first. Automated extraction and matching are aids to investigation, not an authority that can declare consequential public claims true or false without inspectable evidence.

## Persistent Claim Ledger

MVP 0.8 adds an optional PostgreSQL persistence layer. The API continues to work without a database. When `DATABASE_URL` is present, the service automatically initializes its ledger tables and starts persisting URL analyses.

The stable public story record ID is derived from the SHA-256 fingerprint of the extracted article text:

```text
ai_<first 16 hex characters of content SHA-256>
```

Repeated ingestion of the same extracted article content therefore resolves to the same public record ID.

The ledger stores:

- article URL, title, source, capture time, raw extracted text, and content SHA-256
- stable claim IDs and extraction confidence
- claim status and status basis
- evidence URLs, type, relation, verification confidence, fetch state, excerpts, and SHA-256 fingerprints
- append-only claim status revisions when verification changes a stored claim status

## Railway PostgreSQL setup

In the existing Railway project:

1. Click **+ New** or **Add Service**.
2. Choose **Database → PostgreSQL**.
3. Attach the PostgreSQL service to the same project/environment as `American_Idea`.
4. In the `American_Idea` service, confirm a `DATABASE_URL` variable is available. Railway commonly provides it through a reference to the PostgreSQL service.
5. Redeploy the API.
6. Open:

```text
https://americanidea-production.up.railway.app/api/health
```

When configured, the response should contain:

```json
{
  "status": "ok",
  "service": "american-idea-evidence",
  "version": "0.8.0",
  "ledger_configured": true
}
```

After analyzing a URL, the response will return:

```json
{
  "record_id": "ai_...",
  "snapshot_status": "persisted",
  "ledger_persisted": true
}
```

The record can then be retrieved at:

```text
GET /api/records/ai_<record id>
```

## Run locally

### Windows Command Prompt

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Without `DATABASE_URL`, local mode remains non-persistent.

To test persistence locally, set a PostgreSQL connection string before launching the app:

```cmd
set DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

## API

- `GET /api/health` — service and ledger configuration status
- `POST /api/analyze` — analyze supplied text
- `POST /api/ingest-url` — fetch a public article URL, fingerprint it, extract claims, and attach source-linked evidence leads
- `POST /api/verify-evidence` — fetch and compare a limited number of evidence leads
- `GET /api/records/{record_id}` — retrieve a persisted evidence record

Interactive API documentation:

`https://americanidea-production.up.railway.app/docs`

## Architecture

- `docs/` — GitHub Pages StoryLens frontend
- `app/main.py` — FastAPI routes
- `app/services/url_ingestor.py` — secure public URL ingestion and source-link preservation
- `app/services/claim_extractor.py` — candidate factual-claim extraction
- `app/services/evidence_engine.py` — source-linked evidence discovery
- `app/services/evidence_verifier.py` — conservative evidence fetching and relationship matching
- `app/services/ledger.py` — optional PostgreSQL persistent Claim Ledger
- `schema/postgres.sql` — longer-term relational ledger design
- `tests/` — regression tests

## Next build layers

1. Public saved-record pages on GitHub Pages.
2. Event clustering across multiple outlets.
3. Independent primary-source discovery beyond links already present in the article.
4. Compare Coverage across outlets covering the same event.
5. Correction/retraction watcher and Story Timeline.
6. Human-review queue for high-impact or contested claims.
7. Cryptographic provenance anchoring.
8. Public claim pages, citation/export API, and browser extension.

## Core rule

**No source is above evidence — including American Idea.**
