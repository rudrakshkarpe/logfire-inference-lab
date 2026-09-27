const $ = (id) => document.getElementById(id);
let profiles = [], current = null, source = null, health = {}, runs = [];
const fmt = (v) => v == null ? '—' : Math.round(v).toLocaleString();
async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`);
  }
  return response.json();
}
function showError(error) { $('error-banner').textContent = error.message; $('error-banner').hidden = false; }
function linkToTrace(traceId) {
  if (!health.project_url || !traceId) return null;
  try {
    const url = new URL(health.project_url);
    if (!['https:', 'http:'].includes(url.protocol)) return null;
    url.searchParams.set('q', `trace_id = '${traceId}'`);
    return url.href;
  } catch { return null; }
}
function render(run) {
  current = run;
  const stats = run.summary;
  for (const [id, value] of [['stat-first', stats.p95_first_chunk_ms], ['stat-queue', stats.p95_queue_ms], ['stat-prefill', stats.p95_prefill_ms]]) {
    $(id).textContent = fmt(value);
    if (value != null) { const unit = document.createElement('em'); unit.textContent = ' ms'; $(id).append(unit); }
  }
  $('stat-errors').textContent = `${(stats.error_rate * 100).toFixed(1)}%`;
  $('stat-count').textContent = `${stats.errors} errors / ${stats.completed} completed`;
  $('run-meta').textContent = `${run.status} · ${stats.completed}/${stats.requested} requests · seed ${run.spec.seed}`;
  $('progress-bar').style.width = `${100 * stats.completed / stats.requested}%`;
  $('cancel-button').hidden = !['running', 'pending'].includes(run.status);
  $('export-link').href = `/api/runs/${run.id}/export`; $('export-link').hidden = false;
  $('csv-link').href = `/api/runs/${run.id}/requests.csv`; $('csv-link').hidden = false;
  const profile = profiles.find(p => p.id === run.spec.scenario);
  $('hypothesis').textContent = profile?.hypothesis || '';
  $('investigate').textContent = profile?.investigate || '';
  const trace = linkToTrace(run.trace_id); $('trace-link').hidden = !trace;
  if (trace) $('trace-link').href = trace;
  const rows = [...run.results].sort((a,b) => a.index-b.index);
  const shown = $('errors-only').checked ? rows.filter(r => r.status !== 'ok') : rows;
  const tbody = $('request-rows'); tbody.replaceChildren();
  if (!shown.length) { const tr = tbody.insertRow(); const td = tr.insertCell(); td.colSpan=7; td.className='empty'; td.textContent='No matching requests.'; }
  for (const row of shown) {
    const tr = tbody.insertRow();
    const values = [row.request_id.slice(-7), row.status, fmt(row.queue_ms), fmt(row.prefill_ms), fmt(row.first_chunk_ms), fmt(row.duration_ms), row.output_tokens];
    values.forEach((value, index) => { const td = tr.insertCell(); if (index === 1) { const pill = document.createElement('span'); pill.className=`pill ${row.status === 'ok' ? '' : 'error'}`; pill.textContent=value; td.append(pill); } else td.textContent=value; });
    if (row.error) tr.title = row.error;
  }
  drawStages(rows); drawChart(rows); compare(run);
  if (run.failure) showError(new Error(`Run ${run.status}: ${run.failure}`));
}
function drawStages(rows) {
  if (!rows.length) return;
  const mean = key => rows.reduce((sum,r)=>sum+r[key],0)/rows.length;
  const items = [['queue','Queue',mean('queue_ms')],['prefill','Prefill',mean('prefill_ms')],['decode','Decode',mean('decode_ms')]];
  const total = items.reduce((sum,item)=>sum+item[2],0);
  $('stages').replaceChildren(); $('stage-values').replaceChildren();
  for (const [className,label,value] of items) {
    const bar = document.createElement('div'); bar.className=`stage ${className}`; bar.style.width=`${value/total*100}%`; bar.title=`${label}: ${fmt(value)} ms`; $('stages').append(bar);
    const text = document.createElement('div'); text.textContent=label; const strong=document.createElement('strong'); strong.textContent=`${fmt(value)} ms`; text.append(strong); $('stage-values').append(text);
  }
}
function drawChart(rows) {
  if (!rows.length) return;
  const ns='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(ns,'svg'); svg.setAttribute('viewBox','0 0 440 129'); svg.setAttribute('role','img'); svg.setAttribute('aria-label','First-chunk latency in request order');
  const top=Math.max(1,...rows.map(r=>r.first_chunk_ms||0));
  for (let i=0;i<3;i++) { const y=15+i*42; const line=document.createElementNS(ns,'line'); for(const [k,v] of Object.entries({x1:42,x2:435,y1:y,y2:y,stroke:'#e9ede7','stroke-dasharray':'3 4'})) line.setAttribute(k,v); svg.append(line); const text=document.createElementNS(ns,'text'); text.setAttribute('x','0');text.setAttribute('y',y+4);text.setAttribute('fill','#88988f');text.setAttribute('font-size','9');text.textContent=fmt(top*(1-i/2));svg.append(text); }
  const points=rows.map((r,i)=>[45+i*385/Math.max(1,rows.length-1),99-(r.first_chunk_ms||0)/top*84]);
  const path=document.createElementNS(ns,'polyline');path.setAttribute('points',points.map(p=>p.join(',')).join(' '));path.setAttribute('fill','none');path.setAttribute('stroke','#386e5c');path.setAttribute('stroke-width','2');svg.append(path);
  points.forEach(([x,y],i)=>{const c=document.createElementNS(ns,'circle');c.setAttribute('cx',x);c.setAttribute('cy',y);c.setAttribute('r','3');c.setAttribute('fill',rows[i].status==='ok'?'#92b897':'#c26749');const t=document.createElementNS(ns,'title');t.textContent=`Request ${rows[i].index+1}: ${fmt(rows[i].first_chunk_ms)} ms`;c.append(t);svg.append(c);});
  $('latency-chart').replaceChildren(svg);
}
function compare(run) {
  const baseline=runs.find(r=>r.id!==run.id && r.spec.scenario==='baseline' && r.status==='completed' && r.spec.seed===run.spec.seed && r.spec.concurrency===run.spec.concurrency && r.spec.requests===run.spec.requests);
  const before=baseline?.summary.p95_first_chunk_ms, after=run.summary.p95_first_chunk_ms;
  $('comparison-panel').hidden=!before || after==null || run.spec.scenario==='baseline';
  if(before && after!=null) $('comparison').textContent=`First-chunk p95: ${fmt(before)} → ${fmt(after)} ms (${(after/before).toFixed(1)}×) · matching seed, count and concurrency`;
}
async function refreshRuns(selected) {
  runs=await api('/api/runs'); const select=$('run-select'); select.replaceChildren();
  if(!runs.length){const option=new Option('No runs yet','');select.add(option);return;}
  for(const run of runs) select.add(new Option(`${profiles.find(p=>p.id===run.spec.scenario)?.title || run.spec.scenario} · ${run.id.slice(0,6)} · ${run.status}`,run.id));
  select.value=selected||runs[0].id;
}
async function watch(id) {
  if(source) source.close();
  render(await api(`/api/runs/${id}`));
  if(!['running','pending'].includes(current.status)) return;
  source=new EventSource(`/api/runs/${id}/events`);
  source.onmessage=async event=>{const run=JSON.parse(event.data);render(run);if(!['running','pending'].includes(run.status)){source.close();await refreshRuns(id);compare(run);}};
  source.onerror=()=>{source.close();showError(new Error('Live connection interrupted. Select this investigation again to reconnect.'));};
}
$('run-form').addEventListener('submit',async event=>{event.preventDefault();$('error-banner').hidden=true;$('run-button').disabled=true;try{const run=await api('/api/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario:$('scenario').value,requests:Number($('requests-input').value),concurrency:Number($('concurrency').value),seed:Number($('seed').value)})});await refreshRuns(run.id);await watch(run.id);}catch(error){showError(error);}finally{$('run-button').disabled=false;}});
$('scenario').addEventListener('change',()=>{$('scenario-description').textContent=profiles.find(p=>p.id===$('scenario').value)?.description||'';});
$('run-select').addEventListener('change',()=>watch($('run-select').value).catch(showError));
$('errors-only').addEventListener('change',()=>{if(current)render(current);});
$('cancel-button').addEventListener('click',async()=>{try{await api(`/api/runs/${current.id}/cancel`,{method:'POST'});await watch(current.id);await refreshRuns(current.id);}catch(error){showError(error);}});
(async()=>{try{[profiles,health]=await Promise.all([api('/api/scenarios'),api('/api/health')]);for(const p of profiles)$('scenario').add(new Option(p.title,p.id));$('scenario').dispatchEvent(new Event('change'));$('connection').textContent=health.export_enabled?'Logfire export enabled':'Local collection';if(health.project_url){const u=new URL(health.project_url);if(['https:','http:'].includes(u.protocol)){$('logfire-link').href=u.href;$('logfire-link').hidden=false;}}await refreshRuns();if($('run-select').value)await watch($('run-select').value);}catch(error){showError(error);$('connection').textContent='Connection unavailable';}})();
