const $ = (id) => document.getElementById(id);
const API_BASE = "https://americanidea-production.up.railway.app";

const sample = `Federal officials reported that 1,240,000 people enrolled in the program in 2025, an increase of 18% from 2024. According to the agency's annual report, the program cost $4.6 billion in 2025. The governor said Tuesday that the policy had reduced processing times by 30%. An independent audit found that average processing time fell from 42 days to 31 days. Critics said the program was the worst reform in decades and should be repealed immediately. The agency announced that a revised dataset would be published in September 2026.`;

const NUMBERISH = /(?:\$?\d[\d,.]*(?:%|\s?(?:million|billion|trillion))?|\b(?:million|billion|trillion)\b)/i;
const ATTRIBUTION = /\b(?:said|says|reported|according to|announced|claimed|found|shows?|indicates?|estimated|confirmed|rose|fell|increased|decreased|won|lost|voted|approved|rejected|recorded)\b/i;
const DATE_OR_TIME = /\b(?:19|20)\d{2}\b|\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|January|February|March|April|May|June|July|August|September|October|November|December)\b/i;
const OPINION_CUES = /\b(?:I think|I believe|should|ought to|best|worst|disgraceful|wonderful|terrible|greatest|dangerous|radical|far-left|far-right)\b/i;
const BOILERPLATE = /\b(?:sign up|newsletter|click here|watch live|election hub|power rankings|video|advertisement|subscribe|read more|stay up to date|download the app|follow us)\b/i;

function normalize(value) {
  return value.replace(/\s+/g, " ").replace(/^[\s\-•]+|[\s\-•]+$/g, "").trim();
}

function splitSentences(text) {
  const cleaned = text.replace(/\r/g, "\n").replace(/\n+/g, " ");
  const matches = cleaned.match(/[^.!?]+(?:[.!?]+[\"'”’)]*|$)/g) || [];
  return matches.map(normalize).filter(Boolean);
}

function looksLikeFragment(sentence) {
  if (sentence.length < 35 || sentence.length > 500) return true;
  if (/^\d{1,2},\s*20\d{2}\b/.test(sentence)) return true;
  if (/^[a-z]/.test(sentence) && !/^[a-z]+:\s/i.test(sentence)) return true;
  if (/^(?:and|but|or|our|its|it's|to say|while)\b/i.test(sentence) && !/[.!?][\"'”’)]*$/.test(sentence)) return true;
  const words = sentence.split(/\s+/).length;
  return words < 7;
}

async function claimId(text) {
  if (globalThis.crypto?.subtle) {
    const data = new TextEncoder().encode(text.toLowerCase());
    const digest = await crypto.subtle.digest("SHA-256", data);
    const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
    return `claim_${hex.slice(0, 12)}`;
  }
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return `claim_${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

async function extractCandidateClaims(text, limit = 20) {
  const candidates = [];
  for (const raw of splitSentences(text)) {
    const sentence = normalize(raw);
    if (!sentence || BOILERPLATE.test(sentence) || looksLikeFragment(sentence)) continue;

    const reasons = [];
    let score = 0.15;
    if (NUMBERISH.test(sentence)) {
      reasons.push("contains a measurable quantity");
      score += 0.35;
    }
    if (ATTRIBUTION.test(sentence)) {
      reasons.push("contains an attributed or externally verifiable assertion");
      score += 0.25;
    }
    if (DATE_OR_TIME.test(sentence)) {
      reasons.push("contains a date or time-bounded assertion");
      score += 0.15;
    }
    if (OPINION_CUES.test(sentence)) score -= 0.25;

    if (score >= 0.35 && reasons.length) {
      candidates.push({ text: sentence, score: Math.min(score, 0.95), reasons });
    }
  }

  candidates.sort((a, b) => b.score - a.score);
  const unique = [];
  const seen = new Set();
  for (const candidate of candidates) {
    const key = candidate.text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push({
      id: await claimId(candidate.text),
      text: candidate.text,
      status: "unresolved",
      confidence: Math.round(candidate.score * 100) / 100,
      why_flagged: candidate.reasons,
      evidence: [],
    });
    if (unique.length >= limit) break;
  }
  return unique;
}

$("sample").addEventListener("click", () => {
  $("source").value = "Sample outlet";
  $("url").value = "";
  $("text").value = sample;
});

$("clear").addEventListener("click", () => {
  $("source").value = "";
  $("url").value = "";
  $("text").value = "";
  $("results").hidden = true;
  $("error").hidden = true;
});

$("analyze").addEventListener("click", async () => {
  const articleText = $("text").value.trim();
  const sourceName = $("source").value.trim();
  const articleUrl = $("url").value.trim();
  const error = $("error");
  error.hidden = true;

  if (!articleUrl && articleText.length < 20) {
    error.textContent = "Paste a public article URL or at least a short article excerpt.";
    error.hidden = false;
    return;
  }

  if (articleUrl) {
    try { new URL(articleUrl); }
    catch {
      error.textContent = "The article URL is not valid.";
      error.hidden = false;
      return;
    }
  }

  const btn = $("analyze");
  btn.disabled = true;
  btn.textContent = articleUrl ? "Fetching story…" : "Analyzing…";

  try {
    if (articleUrl) {
      const response = await fetch(`${API_BASE}/api/ingest-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ article_url: articleUrl }),
      });

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const message = data?.detail || data?.message || `The source could not be analyzed (HTTP ${response.status}).`;
        throw new Error(message);
      }
      render(data);
      return;
    }

    const claims = await extractCandidateClaims(articleText);
    render({
      record_id: `ai_preview_${Date.now().toString(36)}`,
      source_name: sourceName || null,
      article_url: null,
      claims,
      factual_claim_count: claims.length,
      methodology_note: "Local text mode: candidate factual claims are extracted in your browser with transparent heuristics. Extraction confidence estimates whether a sentence looks verifiable; it is not a truth score. Every claim remains unresolved until evidence is attached.",
    });
  } catch (e) {
    error.textContent = e?.message || "Analysis failed.";
    error.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze story";
  }
});

function render(data) {
  $("results").hidden = false;
  $("record").textContent = data.title || data.record_id;
  $("count").textContent = data.factual_claim_count;
  $("methodology").textContent = data.methodology_note;

  const meta = [];
  if (data.source_name) meta.push(`Source: ${escapeHtml(data.source_name)}`);
  if (data.article_url) meta.push(`<a href="${escapeAttr(data.article_url)}" target="_blank" rel="noreferrer">Open source article</a>`);
  if (data.content_sha256) meta.push(`SHA-256: <code>${escapeHtml(data.content_sha256.slice(0, 16))}…</code>`);
  if (data.snapshot_status) meta.push(`Snapshot: ${escapeHtml(data.snapshot_status.replaceAll("_", " "))}`);
  $("record-meta").innerHTML = meta.join(" · ");

  $("claims").innerHTML = data.claims.length
    ? data.claims.map((c) => `
      <article class="claim">
        <div class="claim-top">
          <div>
            <h3>${escapeHtml(c.text)}</h3>
            <div>Extraction confidence: <strong>${Math.round(c.confidence * 100)}%</strong></div>
          </div>
          <span class="status">${escapeHtml(c.status.replaceAll("_", " "))}</span>
        </div>
        ${c.why_flagged.length ? `<ul class="reasons">${c.why_flagged.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>` : ""}
        <div class="claim-id">${escapeHtml(c.id)}</div>
      </article>`).join("")
    : `<article class="claim"><h3>No strong candidate factual claims detected.</h3><p>This does not mean the article is true or false. It means the current extractor did not identify strong verifiable claim candidates.</p></article>`;

  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[ch]));
}

function escapeAttr(value) {
  return escapeHtml(value);
}
