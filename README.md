# American Idea Evidence — MVP 0.1

A first working slice of **American Idea Evidence**: a public evidence layer for news and public claims.

## What works now

- Paste article text into StoryLens.
- Extract candidate factual claims using transparent, inspectable heuristics.
- Assign stable claim fingerprints.
- Keep every extracted claim **unresolved** until evidence is attached.
- Expose a FastAPI endpoint for programmatic analysis.
- Provide an initial PostgreSQL schema for stories, claims, evidence, corrections, revisions, and provenance anchors.

This is intentionally evidence-first: the MVP does **not** pretend an LLM or heuristic can declare political claims true or false on its own.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

API docs: `http://127.0.0.1:8000/docs`

## API

`POST /api/analyze`

```json
{
  "source_name": "Example outlet",
  "article_url": "https://example.com/story",
  "article_text": "Paste article text here..."
}
```

## Next build layers

1. URL ingestion + immutable snapshots.
2. Event clustering across multiple outlets.
3. Primary-source retrieval (government, courts, datasets, transcripts).
4. Claim ↔ evidence relationship scoring with explicit rationale.
5. Cross-outlet Compare Coverage view.
6. Correction/retraction watcher.
7. Human-review queue for high-impact or contested claims.
8. Cryptographic provenance anchoring.
9. Public claim pages and citation/export API.
10. Browser extension / publisher evidence card.

## Core rule

**No source is above evidence — including American Idea.**
"# American_Idea" 
