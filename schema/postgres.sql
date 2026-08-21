-- American Idea Evidence: PostgreSQL claim-ledger schema
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE source (
  source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  canonical_url text,
  source_type text NOT NULL CHECK (source_type IN ('news','government','court','academic','official_record','dataset','social','podcast','video','other')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE story (
  story_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid REFERENCES source(source_id),
  url text,
  headline text,
  published_at timestamptz,
  captured_at timestamptz NOT NULL DEFAULT now(),
  content_sha256 text NOT NULL,
  raw_text text,
  UNIQUE(content_sha256)
);

CREATE TABLE claim (
  claim_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_text text NOT NULL,
  normalized_sha256 text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'unresolved' CHECK (status IN ('supported','partially_supported','contested','unsupported','unresolved')),
  confidence numeric(5,4) CHECK (confidence BETWEEN 0 AND 1),
  first_observed_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE story_claim (
  story_id uuid NOT NULL REFERENCES story(story_id) ON DELETE CASCADE,
  claim_id uuid NOT NULL REFERENCES claim(claim_id) ON DELETE CASCADE,
  quoted_text text,
  article_position integer,
  PRIMARY KEY (story_id, claim_id)
);

CREATE TABLE evidence_item (
  evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid REFERENCES source(source_id),
  title text NOT NULL,
  url text,
  evidence_type text NOT NULL CHECK (evidence_type IN ('primary','secondary','counterevidence','context')),
  published_at timestamptz,
  captured_at timestamptz NOT NULL DEFAULT now(),
  content_sha256 text,
  note text
);

CREATE TABLE claim_evidence (
  claim_id uuid NOT NULL REFERENCES claim(claim_id) ON DELETE CASCADE,
  evidence_id uuid NOT NULL REFERENCES evidence_item(evidence_id) ON DELETE CASCADE,
  relation text NOT NULL CHECK (relation IN ('supports','contradicts','contextualizes','mentions')),
  weight numeric(5,4) CHECK (weight BETWEEN 0 AND 1),
  rationale text,
  PRIMARY KEY (claim_id, evidence_id)
);

CREATE TABLE evidence_assessment (
  assessment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_id uuid NOT NULL REFERENCES evidence_item(evidence_id) ON DELETE CASCADE,
  quality_score numeric(5,4) NOT NULL CHECK (quality_score BETWEEN 0 AND 1),
  directness numeric(5,4) NOT NULL CHECK (directness BETWEEN 0 AND 1),
  independence numeric(5,4) NOT NULL CHECK (independence BETWEEN 0 AND 1),
  review_required boolean NOT NULL DEFAULT true,
  methodology_version text NOT NULL,
  assessed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE claim_revision (
  revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id uuid NOT NULL REFERENCES claim(claim_id) ON DELETE CASCADE,
  previous_status text,
  new_status text NOT NULL,
  reason text NOT NULL,
  methodology_version text NOT NULL,
  changed_by text NOT NULL,
  changed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE correction (
  correction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  story_id uuid NOT NULL REFERENCES story(story_id) ON DELETE CASCADE,
  observed_at timestamptz NOT NULL DEFAULT now(),
  correction_text text NOT NULL,
  correction_url text,
  content_sha256 text
);

CREATE TABLE provenance_anchor (
  anchor_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type text NOT NULL CHECK (entity_type IN ('story','claim','evidence','revision','correction')),
  entity_id uuid NOT NULL,
  sha256 text NOT NULL,
  anchor_method text NOT NULL,
  anchor_reference text,
  anchored_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_story_source ON story(source_id, published_at DESC);
CREATE INDEX idx_claim_status ON claim(status, first_observed_at DESC);
CREATE INDEX idx_evidence_source ON evidence_item(source_id, published_at DESC);
CREATE INDEX idx_claim_evidence_relation ON claim_evidence(claim_id, relation);
