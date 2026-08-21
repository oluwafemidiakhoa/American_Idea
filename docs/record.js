const API_BASE = "https://americanidea-production.up.railway.app";
const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));
}
function escapeAttr(value){ return escapeHtml(value); }

async function loadRecord(recordId) {
  const error = $("record-error");
  error.hidden = true;
  const id = recordId.trim();
  if (!/^ai_[a-z0-9]{8,64}$/i.test(id)) {
    error.textContent = "Enter a valid saved record ID beginning with ai_.";
    error.hidden = false;
    return;
  }

  const button = $("load-record");
  button.disabled = true;
  button.textContent = "Loading…";
  try {
    const response = await fetch(`${API_BASE}/api/records/${encodeURIComponent(id)}`, {headers:{"Accept":"application/json"}});
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.detail || `Record could not be loaded (HTTP ${response.status}).`);
    render(data);
    history.replaceState(null, "", `?id=${encodeURIComponent(id)}`);
  } catch (e) {
    error.textContent = e?.message || "Saved record could not be loaded.";
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Open record";
  }
}

function render(data) {
  $("saved-record").hidden = false;
  $("saved-title").textContent = data.title || data.record_id;
  $("saved-count").textContent = data.factual_claim_count || data.claims?.length || 0;
  const meta = [
    `Record: <code>${escapeHtml(data.record_id)}</code>`,
    data.source_name ? `Source: ${escapeHtml(data.source_name)}` : null,
    data.article_url ? `<a href="${escapeAttr(data.article_url)}" target="_blank" rel="noreferrer">Open source article</a>` : null,
    data.content_sha256 ? `SHA-256: <code>${escapeHtml(data.content_sha256.slice(0,16))}…</code>` : null,
    data.captured_at ? `Captured: ${escapeHtml(new Date(data.captured_at).toLocaleString())}` : null,
  ].filter(Boolean);
  $("saved-meta").innerHTML = meta.join(" · ");

  $("saved-claims").innerHTML = (data.claims || []).map((claim) => {
    const evidence = (claim.evidence || []).map((item) => `
      <div class="evidence-item verification-${escapeAttr(item.fetch_status || "not_fetched")}">
        <div><span class="evidence-kind">${escapeHtml(item.kind)}</span> <span class="evidence-relation">${escapeHtml((item.relation || "unverified_lead").replaceAll("_", " "))}</span></div>
        ${item.url ? `<a href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(item.label || item.url)}</strong></a>` : `<strong>${escapeHtml(item.label || "Evidence")}</strong>`}
        ${item.verification_confidence ? `<small>Verification confidence: ${Math.round(item.verification_confidence * 100)}%</small>` : ""}
        ${item.source_excerpt ? `<blockquote>${escapeHtml(item.source_excerpt)}</blockquote>` : ""}
        ${item.source_sha256 ? `<small>Source SHA-256: <code>${escapeHtml(item.source_sha256.slice(0,16))}…</code></small>` : ""}
      </div>`).join("");

    const revisions = (claim.revisions || []).map((revision) => `
      <li><strong>${escapeHtml(revision.previous_status || "initial")}</strong> → <strong>${escapeHtml(revision.new_status)}</strong> · ${escapeHtml(revision.reason)}${revision.changed_at ? ` · ${escapeHtml(new Date(revision.changed_at).toLocaleString())}` : ""}</li>`).join("");

    return `<article class="claim">
      <div class="claim-top"><div><h3>${escapeHtml(claim.text)}</h3><div>Extraction confidence: <strong>${Math.round((claim.confidence || 0) * 100)}%</strong></div></div><span class="status status-${escapeAttr(claim.status)}">${escapeHtml((claim.status || "unresolved").replaceAll("_", " "))}</span></div>
      ${claim.status_basis ? `<div class="status-basis">${escapeHtml(claim.status_basis)}</div>` : ""}
      ${evidence ? `<div class="evidence-box"><div class="evidence-heading">Evidence</div>${evidence}</div>` : `<div class="no-evidence">No stored evidence for this claim.</div>`}
      ${revisions ? `<div class="revision-box"><div class="evidence-heading">Status history</div><ul class="reasons">${revisions}</ul></div>` : ""}
      <div class="claim-id">${escapeHtml(claim.id)}</div>
    </article>`;
  }).join("");
}

$("load-record").addEventListener("click", () => loadRecord($("record-id").value));
$("record-id").addEventListener("keydown", (event) => { if (event.key === "Enter") loadRecord($("record-id").value); });

const initialId = new URLSearchParams(location.search).get("id");
if (initialId) {
  $("record-id").value = initialId;
  loadRecord(initialId);
}
