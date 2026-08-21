# American Idea Evidence — MVP 0.3

A working public preview of **American Idea Evidence**: a public evidence layer for news and public claims.

## Public StoryLens preview

The repository now includes a GitHub Pages-ready StoryLens interface in `docs/`.

Expected public URL after GitHub Pages is enabled from the `main` branch `/docs` folder:

`https://oluwafemidiakhoa.github.io/American_Idea/`

The public preview runs candidate-claim extraction locally in the browser. Pasted article text is not sent to American Idea by the static preview. Article URLs are stored only as a reference in the current static page; server-side URL ingestion will be connected when the FastAPI backend is deployed publicly.

## What works now

- Paste article text into StoryLens.
- Extract candidate factual claims using transparent, inspectable heuristics.
- Filter common navigation/newsletter boilerplate and obvious fragments.
- Assign stable claim fingerprints.
- Keep every extracted claim **unresolved** until evidence is attached.
- Run a privacy-preserving static StoryLens preview in the browser.
- Expose a FastAPI endpoint for programmatic analysis when the backend is running.
- Provide an initial PostgreSQL schema for stories, claims, evidence, corrections, revisions, and provenance anchors.

This is intentionally evidence-first: the system does **not** pretend an LLM or heuristic can declare political claims true or false on its own.

## Run the FastAPI backend locally

### Windows Command Prompt

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

API docs: `http://127.0.0.1:8765/docs`

## API

`POST /api/analyze`

```json
{
  "source_name": "Example outlet",
  "article_url": "https://example.com/story",
  "article_text": "Paste article text here..."
}
```

## Architecture

- `docs/` — GitHub Pages public StoryLens preview.
- `app/` — FastAPI application and server-side analysis.
- `app/services/claim_extractor.py` — candidate factual-claim extraction.
- `schema/postgres.sql` — initial Claim Ledger database design.
- `tests/` — regression tests for extraction quality.

## Next build layers

1. Public backend deployment and secure URL ingestion.
2. Immutable source snapshots with content hashes and retrieval timestamps.
3. Event clustering across multiple outlets.
4. Primary-source discovery and evidence retrieval.
5. Claim ↔ evidence relationship scoring with explicit rationale.
6. Cross-outlet Compare Coverage view.
7. Correction/retraction watcher and Story Timeline.
8. Human-review queue for high-impact or contested claims.
9. Cryptographic provenance anchoring.
10. Public claim pages, citation/export API, and browser extension.

## Core rule

**No source is above evidence — including American Idea.**
