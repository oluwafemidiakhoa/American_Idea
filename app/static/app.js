const $ = (id) => document.getElementById(id);
const sample = `Federal officials reported that 1,240,000 people enrolled in the program in 2025, an increase of 18% from 2024. According to the agency's annual report, the program cost $4.6 billion in 2025. The governor said Tuesday that the policy had reduced processing times by 30%. An independent audit found that average processing time fell from 42 days to 31 days. Critics said the program was the worst reform in decades and should be repealed immediately. The agency announced that a revised dataset would be published in September 2026.`;

$("sample").addEventListener("click", () => { $("source").value = "Sample outlet"; $("text").value = sample; });
$("analyze").addEventListener("click", async () => {
  const article_text = $("text").value.trim();
  const source_name = $("source").value.trim() || null;
  const article_url = $("url").value.trim() || null;
  const error = $("error");
  error.hidden = true;
  if (article_text.length < 20) { error.textContent = "Paste at least a short article excerpt."; error.hidden = false; return; }
  const btn = $("analyze"); btn.disabled = true; btn.textContent = "Analyzing…";
  try {
    const response = await fetch("/api/analyze", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({article_text,source_name,article_url})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail?.[0]?.msg || "Analysis failed");
    render(data);
  } catch (e) { error.textContent = e.message; error.hidden = false; }
  finally { btn.disabled = false; btn.textContent = "Extract claims"; }
});

function render(data){
  $("results").hidden = false;
  $("record").textContent = data.record_id;
  $("count").textContent = data.factual_claim_count;
  $("methodology").textContent = data.methodology_note;
  $("claims").innerHTML = data.claims.length ? data.claims.map(c => `
    <article class="claim">
      <div class="claim-top"><div><h3>${escapeHtml(c.text)}</h3><div>Extraction confidence: <strong>${Math.round(c.confidence*100)}%</strong></div></div><span class="status">${c.status.replaceAll('_',' ')}</span></div>
      ${c.why_flagged.length ? `<ul class="reasons">${c.why_flagged.map(r=>`<li>${escapeHtml(r)}</li>`).join('')}</ul>`:''}
      <div class="claim-id">${c.id}</div>
    </article>`).join('') : `<article class="claim"><h3>No high-confidence factual claims detected.</h3><p>Try a longer excerpt containing measurable or attributable assertions.</p></article>`;
  $("results").scrollIntoView({behavior:"smooth",block:"start"});
}
function escapeHtml(v){return v.replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));}
