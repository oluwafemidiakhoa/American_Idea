const API_BASE = "https://americanidea-production.up.railway.app";
const $ = (id) => document.getElementById(id);
let currentRecordId = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));
}
function escapeAttr(value){ return escapeHtml(value); }

async function loadRecord(recordId) {
  const error = $("record-error");
  error.hidden = true;
  $("refresh-note").hidden = true;
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
    currentRecordId = data.record_id;
    render(data);
    $("refresh-record").hidden = false;
    $("timeline-link").hidden = false;
    $("timeline-link").href = `./timeline.html?id=${encodeURIComponent(data.record_id)}`;
    history.replaceState(null, "", `?id=${encodeURIComponent(data.record_id)}`);
  } catch (e) {
    error.textContent = e?.message || "Saved record could not be loaded.";
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Open record";
  }
}

async function refreshRecord() {
  if (!currentRecordId) return;
  const button = $("refresh-record");
  const error = $("record-error");
  const note = $("refresh-note");
  error.hidden = true;
  note.hidden = true;
  button.disabled = true;
  button.textContent = "Checking source…";
  try {
    const response = await fetch(`${API_BASE}/api/records/${encodeURIComponent(currentRecordId)}/refresh`, {
      method: "POST",
      headers: {"Accept":"application/json"},
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.detail || `Story refresh failed (HTTP ${response.status}).`);
    note.textContent = data.changed
      ? `A changed source snapshot was detected and saved as ${data.record_id}. The previous record remains immutable.`
      : "No article-text change was detected. The check was recorded without creating a fake new version.";
    note.hidden = false;
    currentRecordId = data.record_id;
    $("record-id").value = data.record_id;
    $("timeline-link").href = `./timeline.html?id=${encodeURIComponent(data.record_id)}`;
    await loadRecord(data.record_id);
  } catch (e) {
    error.textContent = e?.message || "Story refresh failed.";
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Refresh story";
  }
}

async function discoverEvidence(claimId, button) {
  if (!currentRecordId || !claimId) return;
  const error = $("record-error");
  const note = $("refresh-note");
  error.hidden = true;
  note.hidden = true;
  button.disabled = true;
  button.textContent = "Discovering…";
  try {
    const response = await fetch(`${API_BASE}/api/records/${encodeURIComponent(currentRecordId)}/claims/${encodeURIComponent(claimId)}/discover-evidence`, {
      method: "POST",
      headers: {"Accept":"application/json"},
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.detail || `Evidence discovery failed (HTTP ${response.status}).`);
    if (data?.record) render(data.record);
    const queries = (data?.queries || []).slice(0, 2).join(" · ");
    note.textContent = data?.discovered_lead_count
      ? `Discovered ${data.discovered_lead_count} evidence lead${data.discovered_lead_count === 1 ? "" : "s"}. They remain unverified until fetched and compared.${queries ? ` Searches: ${queries}` : ""}`
      : `No new evidence leads were found.${queries ? ` Searches: ${queries}` : ""}`;
    note.hidden = false;
  } catch (e) {
    error.textContent = e?.message || "Evidence discovery failed.";
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Discover evidence";
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
        ${item.note ? `<small>${escapeHtml(item.note)}</small>` : ""}
      </div>`).join("");

    const revisions = (claim.revisions || []).map((revision) => `
      <li><strong>${escapeHtml(revision.previous_status || "initial")}</strong> → <strong>${escapeHtml(revision.new_status)}</strong> · ${escapeHtml(revision.reason)}${revision.changed_at ? ` · ${escapeHtml(new Date(revision.changed_at).toLocaleString())}` : ""}</li>`).join("");

    return `<article class="claim">
      <div class="claim-top"><div><h3>${escapeHtml(claim.text)}</h3><div>Extraction confidence: <strong>${Math.round((claim.confidence || 0) * 100)}%</strong></div></div><span class="status status-${escapeAttr(claim.status)}">${escapeHtml((claim.status || "unresolved").replaceAll("_", " "))}</span></div>
      ${claim.status_basis ? `<div class="status-basis">${escapeHtml(claim.status_basis)}</div>` : ""}
      <div class="actions claim-actions"><button class="secondary discover-evidence" type="button" data-claim-id="${escapeAttr(claim.id)}">Discover evidence</button></div>
      ${evidence ? `<div class="evidence-box"><div class="evidence-heading">Evidence</div>${evidence}</div>` : `<div class="no-evidence">No stored evidence for this claim.</div>`}
      ${revisions ? `<div class="revision-box"><div class="evidence-heading">Status history</div><ul class="reasons">${revisions}</ul></div>` : ""}
      <div class="claim-id">${escapeHtml(claim.id)}</div>
    </article>`;
  }).join("");
}

$("load-record").addEventListener("click", () => loadRecord($("record-id").value));
$("refresh-record").addEventListener("click", refreshRecord);
$("record-id").addEventListener("keydown", (event) => { if (event.key === "Enter") loadRecord($("record-id").value); });
$("saved-claims").addEventListener("click", (event) => {
  const button = event.target.closest(".discover-evidence");
  if (!button) return;
  discoverEvidence(button.dataset.claimId, button);
});

const initialId = new URLSearchParams(location.search).get("id");
if (initialId) {
  $("record-id").value = initialId;
  loadRecord(initialId);
}
