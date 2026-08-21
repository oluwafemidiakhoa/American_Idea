const $ = (id) => document.getElementById(id);
const API_BASE = "https://americanidea-production.up.railway.app";
let currentAnalysis = null;
let evidenceMatrices = {};
let providerDiagnostics = {};

const sample = `Federal officials reported that 1,240,000 people enrolled in the program in 2025, an increase of 18% from 2024. According to the agency's annual report, the program cost $4.6 billion in 2025. The governor said Tuesday that the policy had reduced processing times by 30%. An independent audit found that average processing time fell from 42 days to 31 days.`;
const NUMBERISH = /(?:\$?\d[\d,.]*(?:%|\s?(?:million|billion|trillion))?|\b(?:million|billion|trillion)\b)/i;
const ATTRIBUTION = /\b(?:said|says|reported|according to|announced|claimed|found|shows?|indicates?|estimated|confirmed|rose|fell|increased|decreased|won|lost|voted|approved|rejected|recorded)\b/i;
const DATE_OR_TIME = /\b(?:19|20)\d{2}\b|\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|January|February|March|April|May|June|July|August|September|October|November|December)\b/i;
const BOILERPLATE = /\b(?:sign up|newsletter|click here|watch live|election hub|power rankings|video|advertisement|subscribe|read more|stay up to date|download the app|follow us)\b/i;

function normalize(v){return v.replace(/\s+/g," ").replace(/^[\s\-•]+|[\s\-•]+$/g,"").trim();}
function splitSentences(text){return (text.replace(/\r/g,"\n").replace(/\n+/g," ").match(/[^.!?]+(?:[.!?]+[\"'”’)]*|$)/g)||[]).map(normalize).filter(Boolean);}
function looksLikeFragment(s){return s.length<35||s.length>500||/^\d{1,2},\s*20\d{2}\b/.test(s)||(/^[a-z]/.test(s)&&!/^[a-z]+:\s/i.test(s))||s.split(/\s+/).length<7;}
async function claimId(text){const data=new TextEncoder().encode(text.toLowerCase());const digest=await crypto.subtle.digest("SHA-256",data);const hex=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,"0")).join("");return `claim_${hex.slice(0,12)}`;}
async function extractCandidateClaims(text,limit=20){const out=[];for(const raw of splitSentences(text)){const s=normalize(raw);if(!s||BOILERPLATE.test(s)||looksLikeFragment(s))continue;const reasons=[];let score=.15;if(NUMBERISH.test(s)){reasons.push("contains a measurable quantity");score+=.35;}if(ATTRIBUTION.test(s)){reasons.push("contains an attributed or externally verifiable assertion");score+=.25;}if(DATE_OR_TIME.test(s)){reasons.push("contains a date or time-bounded assertion");score+=.15;}if(score>=.35&&reasons.length)out.push({id:await claimId(s),text:s,status:"unresolved",confidence:Math.min(score,.95),why_flagged:reasons,evidence:[],atomic_claims:[],atomic_claim_count:0,integrity_flags:[],aggregate_status:"unresolved"});if(out.length>=limit)break;}return out;}

$("sample").addEventListener("click",()=>{$("source").value="Sample outlet";$("url").value="";$("text").value=sample;});
$("clear").addEventListener("click",()=>{$("source").value="";$("url").value="";$("text").value="";$("results").hidden=true;$("verify").hidden=true;$("error").hidden=true;currentAnalysis=null;evidenceMatrices={};providerDiagnostics={};});

$("analyze").addEventListener("click",async()=>{
  const text=$("text").value.trim(), source=$("source").value.trim(), url=$("url").value.trim(), error=$("error"); error.hidden=true;
  if(!url&&text.length<20){error.textContent="Paste a public article URL or at least a short article excerpt.";error.hidden=false;return;}
  if(url){try{new URL(url);}catch{error.textContent="The article URL is not valid.";error.hidden=false;return;}}
  const btn=$("analyze");btn.disabled=true;btn.textContent=url?"Fetching story…":"Analyzing…";
  try{
    if(url){const r=await fetch(`${API_BASE}/api/ingest-url`,{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json"},body:JSON.stringify({article_url:url})});const data=await r.json().catch(()=>null);if(!r.ok)throw new Error(data?.detail||`The source could not be analyzed (HTTP ${r.status}).`);currentAnalysis=data;evidenceMatrices={};providerDiagnostics={};render(data);$("verify").hidden=!(data.evidence_link_count>0);return;}
    const claims=await extractCandidateClaims(text);currentAnalysis={record_id:`ai_preview_${Date.now().toString(36)}`,source_name:source||null,article_url:null,claims,factual_claim_count:claims.length,methodology_note:"Local text mode: claims are extracted in your browser. Atomic Claim Provenance and deep verification require a persisted source URL."};render(currentAnalysis);$("verify").hidden=true;
  }catch(e){error.textContent=e?.message||"Analysis failed.";error.hidden=false;}finally{btn.disabled=false;btn.textContent="Analyze story";}
});

$("verify").addEventListener("click",async()=>{if(!currentAnalysis?.article_url||!currentAnalysis?.claims?.length)return;const btn=$("verify"),error=$("error");error.hidden=true;btn.disabled=true;btn.textContent="Checking linked evidence…";try{const r=await fetch(`${API_BASE}/api/verify-evidence`,{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json"},body:JSON.stringify({article_url:currentAnalysis.article_url,claims:currentAnalysis.claims,max_fetches:6})});const data=await r.json().catch(()=>null);if(!r.ok)throw new Error(data?.detail||`Linked evidence verification failed (HTTP ${r.status}).`);currentAnalysis={...currentAnalysis,...data,record_id:currentAnalysis.record_id,title:currentAnalysis.title,source_name:currentAnalysis.source_name,content_sha256:currentAnalysis.content_sha256,snapshot_status:currentAnalysis.snapshot_status,evidence_link_count:currentAnalysis.evidence_link_count,claims_with_evidence:currentAnalysis.claims_with_evidence};render(currentAnalysis);}catch(e){error.textContent=e?.message||"Linked evidence verification failed.";error.hidden=false;}finally{btn.disabled=false;btn.textContent="Verify linked evidence";}});

async function deepVerify(claimId, button){
  if(!currentAnalysis?.ledger_persisted||!currentAnalysis?.record_id||!claimId)return;
  const error=$("error");error.hidden=true;button.disabled=true;button.textContent="Deep verifying…";
  try{
    const r=await fetch(`${API_BASE}/api/records/${encodeURIComponent(currentAnalysis.record_id)}/claims/${encodeURIComponent(claimId)}/auto-verify`,{method:"POST",headers:{"Accept":"application/json"}});
    const data=await r.json().catch(()=>null);if(!r.ok)throw new Error(data?.detail||`Deep verification failed (HTTP ${r.status}).`);
    evidenceMatrices[claimId]=data.evidence_matrix||null;
    providerDiagnostics[claimId]=data.provider_diagnostics||{};
    const rr=await fetch(`${API_BASE}/api/records/${encodeURIComponent(currentAnalysis.record_id)}`,{headers:{"Accept":"application/json"}});
    const record=await rr.json().catch(()=>null);if(!rr.ok)throw new Error(record?.detail||`Saved record refresh failed (HTTP ${rr.status}).`);
    currentAnalysis={...currentAnalysis,...record,ledger_persisted:true};
    render(currentAnalysis);
  }catch(e){error.textContent=e?.message||"Deep verification failed.";error.hidden=false;}finally{button.disabled=false;button.textContent="Deep verify";}
}

function providerHtml(claimId){const p=providerDiagnostics[claimId];if(!p||!Object.keys(p).length)return"";const labels=Object.entries(p).map(([name,d])=>`${escapeHtml(name.replaceAll("_"," "))}: ${escapeHtml(d.status)} (${escapeHtml(d.result_count)})`);return `<div class="status-basis"><strong>Provider diagnostics</strong><br>${labels.join(" · ")}</div>`;}
function matrixHtml(claimId){const m=evidenceMatrices[claimId];if(!m)return"";return `<div class="status-basis"><strong>Evidence Matrix</strong><br>Verified sources: ${escapeHtml(m.verified_source_count)} · Primary: ${escapeHtml(m.verified_primary_count)} · Secondary: ${escapeHtml(m.verified_secondary_count)} · Failed/blocked: ${escapeHtml(m.blocked_or_failed_count)} · Unverified leads: ${escapeHtml(m.unverified_lead_count)}<br>Strongest support: ${Math.round((m.strongest_support||0)*100)}% · Strongest contradiction: ${Math.round((m.strongest_contradiction||0)*100)}%</div>${providerHtml(claimId)}`;}

function atomicHtml(claim){
  const atoms=claim.atomic_claims||[];if(!atoms.length)return"";
  const flags=(claim.integrity_flags||[]).map(v=>escapeHtml(v.replaceAll("_"," "))).join(" · ");
  const cards=atoms.map((a,i)=>{const contract=a.evidence_contract||{};return `<div class="evidence-item"><div><span class="evidence-kind">ATOM ${i+1}</span> <span class="evidence-relation">${escapeHtml((a.atomic_type||"general_fact").replaceAll("_"," "))}</span></div><strong>${escapeHtml(a.text)}</strong><small>Status: ${escapeHtml((a.status||"unresolved").replaceAll("_"," "))}</small>${a.decomposition_reason?`<small>${escapeHtml(a.decomposition_reason)}</small>`:""}${contract.name?`<small><strong>Evidence contract:</strong> ${escapeHtml(contract.name.replaceAll("_"," "))}</small>`:""}${contract.minimum?`<small>${escapeHtml(contract.minimum)}</small>`:""}</div>`;}).join("");
  return `<div class="evidence-box"><div class="evidence-heading">Claim Anatomy · ${atoms.length} atomic proposition${atoms.length===1?"":"s"}</div>${flags?`<div class="status-basis"><strong>Integrity flags:</strong> ${flags}<br><strong>Aggregate atomic status:</strong> ${escapeHtml((claim.aggregate_status||"unresolved").replaceAll("_"," "))}</div>`:""}${cards}</div>`;
}

function render(data){$("results").hidden=false;$("record").textContent=data.title||data.record_id;$("count").textContent=data.factual_claim_count;$("methodology").textContent=data.methodology_note;const meta=[];if(data.source_name)meta.push(`Source: ${escapeHtml(data.source_name)}`);if(data.article_url)meta.push(`<a href="${escapeAttr(data.article_url)}" target="_blank" rel="noreferrer">Open source article</a>`);if(data.ledger_persisted&&data.record_id)meta.push(`<a href="./record.html?id=${encodeURIComponent(data.record_id)}">Open saved record</a>`);if(data.content_sha256)meta.push(`SHA-256: <code>${escapeHtml(data.content_sha256.slice(0,16))}…</code>`);if(Number.isInteger(data.evidence_link_count))meta.push(`Evidence leads: ${data.evidence_link_count}`);if(Number.isInteger(data.fetched_source_count))meta.push(`Sources fetched: ${data.fetched_source_count}`);if(Number.isInteger(data.verified_evidence_count))meta.push(`Evidence matches: ${data.verified_evidence_count}`);$("record-meta").innerHTML=meta.join(" · ");$("claims").innerHTML=data.claims.length?data.claims.map(c=>{const evidence=(c.evidence||[]).map(item=>`<div class="evidence-item verification-${escapeAttr(item.fetch_status||"not_fetched")}"><div><span class="evidence-kind">${escapeHtml(item.kind)}</span> <span class="evidence-relation">${escapeHtml((item.relation||"unverified_lead").replaceAll("_"," "))}</span></div><a href="${escapeAttr(item.url||"#")}" target="_blank" rel="noreferrer"><strong>${escapeHtml(item.label)}</strong></a>${item.verification_confidence?`<small>Verification confidence: ${Math.round(item.verification_confidence*100)}%</small>`:""}${item.source_excerpt?`<blockquote>${escapeHtml(item.source_excerpt)}</blockquote>`:""}${item.note?`<small>${escapeHtml(item.note)}</small>`:""}</div>`).join("");const deep=data.ledger_persisted?`<div class="actions claim-actions"><button class="deep-verify" type="button" data-claim-id="${escapeAttr(c.id)}">Deep verify</button></div>`:"";return `<article class="claim"><div class="claim-top"><div><h3>${escapeHtml(c.text)}</h3><div>Extraction confidence: <strong>${Math.round(c.confidence*100)}%</strong></div></div><span class="status status-${escapeAttr(c.status)}">${escapeHtml(c.status.replaceAll("_"," "))}</span></div>${c.status_basis?`<div class="status-basis">${escapeHtml(c.status_basis)}</div>`:""}${atomicHtml(c)}${matrixHtml(c.id)}${deep}${evidence?`<div class="evidence-box"><div class="evidence-heading">Evidence</div>${evidence}</div>`:`<div class="no-evidence">No source-linked or discovered evidence has been stored for this claim yet.</div>`}<div class="claim-id">${escapeHtml(c.id)}</div></article>`;}).join(""):`<article class="claim"><h3>No strong candidate factual claims detected.</h3></article>`;$("results").scrollIntoView({behavior:"smooth",block:"start"});}
function escapeHtml(v){return String(v).replace(/[&<>'"]/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));}function escapeAttr(v){return escapeHtml(v);}

$("claims").addEventListener("click",(event)=>{const button=event.target.closest(".deep-verify");if(button)deepVerify(button.dataset.claimId,button);});
