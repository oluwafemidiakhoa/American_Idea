const API_BASE = "https://americanidea-production.up.railway.app";
const $ = (id) => document.getElementById(id);

function escapeHtml(value){return String(value ?? "").replace(/[&<>'"]/g,(ch)=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));}
function escapeAttr(value){return escapeHtml(value);}

async function loadTimeline(idValue){
  const id=idValue.trim();
  const error=$("timeline-error");error.hidden=true;
  if(!/^ai_[a-z0-9]{8,64}$/i.test(id)){error.textContent="Enter a valid saved record ID beginning with ai_.";error.hidden=false;return;}
  const button=$("load-timeline");button.disabled=true;button.textContent="Loading…";
  try{
    const response=await fetch(`${API_BASE}/api/records/${encodeURIComponent(id)}/timeline`,{headers:{"Accept":"application/json"}});
    const data=await response.json().catch(()=>null);
    if(!response.ok)throw new Error(data?.detail||`Timeline could not be loaded (HTTP ${response.status}).`);
    renderTimeline(data);history.replaceState(null,"",`?id=${encodeURIComponent(id)}`);
  }catch(e){error.textContent=e?.message||"Timeline could not be loaded.";error.hidden=false;}
  finally{button.disabled=false;button.textContent="Open timeline";}
}

function renderTimeline(data){
  $("timeline-results").hidden=false;
  $("timeline-title").textContent=data.versions?.at(-1)?.title||"Version history";
  $("version-count").textContent=data.version_count||0;
  $("timeline-method").textContent=data.methodology_note||"";
  $("timeline-meta").innerHTML=[
    data.article_url?`<a href="${escapeAttr(data.article_url)}" target="_blank" rel="noreferrer">Open current source URL</a>`:null,
    `Changed snapshots: ${escapeHtml(data.changed_version_count||0)}`,
  ].filter(Boolean).join(" · ");

  $("versions").innerHTML=(data.versions||[]).map((version)=>{
    const delta=version.delta_from_previous;
    const added=delta?.added?.length?`<div class="timeline-delta"><strong>Added passages</strong><ul class="reasons">${delta.added.map(x=>`<li>${escapeHtml(x)}</li>`).join("")}</ul></div>`:"";
    const removed=delta?.removed?.length?`<div class="timeline-delta"><strong>Removed passages</strong><ul class="reasons">${delta.removed.map(x=>`<li>${escapeHtml(x)}</li>`).join("")}</ul></div>`:"";
    return `<article class="claim">
      <div class="claim-top"><div><p class="eyebrow">VERSION ${version.version}</p><h3>${escapeHtml(version.title||version.record_id)}</h3></div><span class="status">${version.correction_language_detected?"correction signal":"snapshot"}</span></div>
      <div class="record-meta">Record: <a href="./record.html?id=${encodeURIComponent(version.record_id)}"><code>${escapeHtml(version.record_id)}</code></a> · Captured: ${escapeHtml(new Date(version.captured_at).toLocaleString())} · SHA-256: <code>${escapeHtml(version.content_sha256.slice(0,16))}…</code></div>
      ${delta?`<div class="status-basis">Similarity to previous: ${Math.round(delta.similarity*100)}% · Added: ${delta.added_count} · Removed: ${delta.removed_count}</div>`:"<div class="status-basis">First saved snapshot for this URL.</div>"}
      ${version.correction_excerpt?`<div class="methodology"><strong>Explicit update/correction language detected:</strong> ${escapeHtml(version.correction_excerpt)}</div>`:""}
      ${added}${removed}
    </article>`;
  }).join("");

  const observations=data.observations||[];
  $("observations").innerHTML=observations.length?`<article class="claim"><p class="eyebrow">REFRESH OBSERVATIONS</p><h3>Source checks</h3><ul class="reasons">${observations.map(o=>`<li>${escapeHtml(new Date(o.observed_at).toLocaleString())} · ${o.changed?"changed snapshot":"no text change"}${o.correction_language_detected?" · explicit correction/update language detected":""}</li>`).join("")}</ul></article>`:"";
}

$("load-timeline").addEventListener("click",()=>loadTimeline($("timeline-id").value));
$("timeline-id").addEventListener("keydown",(event)=>{if(event.key==="Enter")loadTimeline($("timeline-id").value);});
const initialId=new URLSearchParams(location.search).get("id");if(initialId){$("timeline-id").value=initialId;loadTimeline(initialId);}
