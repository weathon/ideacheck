"""The D3 report view, shared by the static report.html and the live web GUI.

The visualization is a single JS class, `IdeaCheckView`, that renders
INCREMENTALLY: call `addPaper(p)` as each paper analysis lands and a node
animates into the force graph; call `setFinal(f)` when the synthesis is ready to
fill the novelty gauge, verdict, summary and differentiation suggestions.

  - static report.html  feeds the whole saved DATA in at load (build_report_html)
  - the GUI             feeds the same shapes one SSE event at a time, so the
                        report builds in real time while the agents work

Both import REPORT_CSS / REPORT_BODY / REPORT_VIEW_JS from here, so there is one
source of truth for the UI. The per-paper object and the final object have the
exact shapes the save_paper_analysis / save_final_report tools persist, which is
also exactly what pipeline.py streams as {type:"paper"} / {type:"final"} events.
"""

from __future__ import annotations

import json
from pathlib import Path

REPORT_CSS = r"""
:root{
  --bg:#f5f6f8; --panel:#ffffff; --panel2:#f7f8fa; --line:#e7e9ee; --line2:#eef0f4;
  --text:#202330; --muted:#697086; --idea:#5b5bd6; --accent:#4f46e5;
  --r-direct:#dc2626; --r-related:#d97706; --r-tang:#16a34a;
  --shadow:0 1px 2px rgba(17,24,39,.04), 0 6px 20px rgba(17,24,39,.06);
}
*{box-sizing:border-box}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
h1{font-size:27px;margin:0 0 4px;letter-spacing:-.02em;color:#111524;font-weight:700}
h2{font-size:15px;color:#111524;margin:0 0 14px;font-weight:650;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13.5px;margin-bottom:26px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin-bottom:18px;box-shadow:var(--shadow)}
.grid{display:grid;grid-template-columns:290px 1fr;gap:26px}
.idea-box{background:var(--panel2);border-left:3px solid var(--idea);border-radius:8px;padding:13px 15px;color:#374151;white-space:pre-wrap}
.gauge-wrap{display:flex;flex-direction:column;align-items:center;justify-content:center}
.verdict{display:inline-block;padding:5px 13px;border-radius:999px;font-weight:600;font-size:13px;margin-top:8px}
.counts{display:flex;gap:14px;margin-top:14px;flex-wrap:wrap;justify-content:center}
.count{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.dot{width:10px;height:10px;border-radius:50%}
.legend{display:flex;gap:16px;margin:0 0 12px;flex-wrap:wrap;font-size:12px;color:var(--muted)}
.legend .item{display:flex;align-items:center;gap:7px}
#graph{width:100%;height:560px;background:#fbfcfe;border-radius:12px;border:1px solid var(--line2)}
.node-label{font-size:11px;fill:#4b5363;pointer-events:none;font-weight:500}
.node-g circle{transition:r .3s ease}
.muted{color:var(--muted)} .summary :is(h1,h2,h3){color:#111524;font-size:16px;margin:14px 0 6px} .summary code{background:#eef1f6;padding:1px 5px;border-radius:4px;font-size:.92em}
.summary{font-size:14.5px;color:#363c4a} .summary ul{padding-left:20px} .summary p{margin:8px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:10px 10px;border-bottom:1px solid var(--line2);vertical-align:top}
th{color:var(--muted);font-weight:600;cursor:pointer;user-select:none}
tr.row{cursor:pointer} tr.row:hover{background:#f6f8fb}
.score-pill{display:inline-block;min-width:34px;text-align:center;padding:2px 8px;border-radius:6px;font-weight:700;color:#fff;font-size:12px}
.bar-row{cursor:pointer} .bar-label{font-size:11px;fill:#4b5363}
.suggestions li{margin:6px 0}
#panel{position:fixed;top:0;right:0;width:440px;max-width:92vw;height:100%;background:var(--panel);border-left:1px solid var(--line);box-shadow:-18px 0 48px rgba(17,24,39,.14);transform:translateX(100%);transition:transform .22s ease;overflow-y:auto;z-index:50;padding:24px}
#panel.open{transform:translateX(0)}
#panel .close{position:absolute;top:16px;right:18px;cursor:pointer;color:var(--muted);font-size:24px;line-height:1}
#panel h3{margin:2px 40px 8px 0;font-size:18px;color:#111524}
.kv{margin:11px 0} .kv b{color:var(--muted);font-weight:600;font-size:11px;display:block;margin-bottom:3px;text-transform:uppercase;letter-spacing:.04em}
.taglist{margin:6px 0 0;padding-left:18px} .taglist li{margin:4px 0}
.relbadge{display:inline-block;padding:3px 9px;border-radius:6px;font-size:12px;font-weight:600}
.src{font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:6px;padding:1px 6px}
.reading-row{display:flex;gap:11px;align-items:flex-start;padding:11px 0;border-bottom:1px solid var(--line2);cursor:pointer}
.reading-row:hover{background:#f6f8fb}
.read-pill{flex:none;min-width:30px;text-align:center;padding:2px 7px;border-radius:6px;font-weight:700;font-size:12px;background:#eef0fb;color:#4338ca}
.recbadge{flex:none;display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;white-space:nowrap}
.reading-row .meta2{flex:1;min-width:0}
.reading-row .ttl{color:#111524;font-weight:500} .reading-row .why{color:var(--muted);font-size:12.5px;margin-top:2px}
.pick{color:#b45309;font-weight:700;font-size:11px;margin-left:6px}
.impr{border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0;background:var(--panel2)}
.impr h3{margin:0 0 4px;font-size:15px;color:var(--accent)}
.impr .lbl{color:var(--muted);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin-top:10px}
.impr p{margin:3px 0;color:#363c4a} .impr .srcs{margin-top:10px;font-size:12px}
.scope-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:6px}
.lbl2{color:var(--muted);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}
.scope-bg{background:var(--panel2);border-radius:8px;padding:11px 13px;color:#5b6270;white-space:pre-wrap;font-size:13.5px}
.scope-prop{background:#eef0fb;border-left:3px solid var(--idea);border-radius:8px;padding:11px 13px;color:#1f2430;white-space:pre-wrap;font-size:13.5px}
.contrib{margin-top:16px}
.contrib-bar{position:relative;height:22px;background:#eef0f4;border-radius:6px;overflow:hidden;display:flex;align-items:center;margin:4px 0 8px}
.contrib-fill{height:100%;border-radius:6px;transition:width .4s ease}
.contrib-bar span{position:absolute;right:10px;font-size:12px;font-weight:700;color:#1f2430}
@media(max-width:680px){.scope-grid{grid-template-columns:1fr}}
"""

# DOM skeleton, shared by the static report and the GUI. Same element ids that
# IdeaCheckView writes into.
REPORT_BODY = r"""
  <div class="card grid">
    <div class="gauge-wrap">
      <svg id="gauge" width="220" height="150"></svg>
      <div id="verdict"></div>
      <div class="counts" id="counts"></div>
    </div>
    <div>
      <h2>The idea</h2>
      <div class="idea-box" id="idea"></div>
      <h2 style="margin-top:18px">Synthesis</h2>
      <div class="summary" id="summary"><span class="muted">waiting for the synthesis…</span></div>
    </div>
  </div>

  <div class="card" id="scope-card" style="display:none">
    <h2>What you're actually proposing <span class="muted" style="font-weight:400;font-size:13px">— only this part is checked for novelty</span></h2>
    <div class="scope-grid">
      <div><div class="lbl2">Background (assumed given)</div><div class="scope-bg" id="scope-bg"></div></div>
      <div><div class="lbl2">Your proposal (evaluated)</div><div class="scope-prop" id="scope-prop"></div></div>
    </div>
    <div class="contrib">
      <div class="lbl2">Contribution size — proposal vs background</div>
      <div class="contrib-bar"><div class="contrib-fill" id="contrib-fill"></div><span id="contrib-num"></span></div>
      <div class="summary" id="contrib-assess"></div>
    </div>
  </div>

  <div class="card" id="diff-card" style="display:none">
    <h2>How your idea differs from prior work</h2>
    <div class="summary" id="differentiation"></div>
  </div>

  <div class="card">
    <h2>Similarity network <span class="muted" id="meta" style="font-weight:400;font-size:13px"></span></h2>
    <div class="legend">
      <div class="item"><span class="dot" style="background:var(--idea)"></span>Your idea</div>
      <div class="item"><span class="dot" style="background:var(--r-direct)"></span>Directly overlapping</div>
      <div class="item"><span class="dot" style="background:var(--r-related)"></span>Related but different</div>
      <div class="item"><span class="dot" style="background:var(--r-tang)"></span>Tangential</div>
      <div class="item muted">(node size &amp; closeness = overlap; drag, click for detail)</div>
    </div>
    <svg id="graph"></svg>
  </div>

  <div class="card">
    <h2>Overlap by paper</h2>
    <svg id="bars" width="100%"></svg>
  </div>

  <div class="card" id="reading-card">
    <h2>Recommended reading <span class="muted" style="font-weight:400;font-size:13px">— papers worth reading, ranked by value to your paper (not just overlap)</span></h2>
    <div id="reading"><span class="muted">waiting for analyses…</span></div>
  </div>

  <div class="card" id="improve-card" style="display:none">
    <h2>Methods to consider adding <span class="muted" style="font-weight:400;font-size:13px">— in-depth analysis</span></h2>
    <div class="summary" id="improve-analysis"></div>
    <div id="improvements"></div>
  </div>

  <div class="card" id="sugg-card" style="display:none">
    <h2>How to differentiate further</h2>
    <ul class="suggestions" id="suggestions"></ul>
  </div>

  <div class="card">
    <h2>All analyzed papers</h2>
    <table id="table"><thead><tr>
      <th data-k="overlap_score">Overlap</th><th data-k="reading_value">Read</th><th data-k="title">Title</th>
      <th data-k="relationship">Relationship</th><th data-k="year">Year</th><th>Source</th>
    </tr></thead><tbody></tbody></table>
  </div>

  <div id="panel"><div class="close" onclick="document.getElementById('panel').classList.remove('open')">&times;</div><div id="panel-body"></div></div>
"""

REPORT_VIEW_JS = r"""
const REL = {
  directly_overlapping:{c:"#dc2626",t:"Directly overlapping"},
  related_but_different:{c:"#d97706",t:"Related but different"},
  tangential:{c:"#16a34a",t:"Tangential"}
};
const relColor = r => (REL[r]||{c:"#6b7280"}).c;
const relText  = r => (REL[r]||{t:r||"unknown"}).t;
const REC = {
  closest_prior_work:{c:"#dc2626",t:"Closest prior work"},
  baseline_to_compare:{c:"#d97706",t:"Baseline to compare"},
  foundational_to_cite:{c:"#2563eb",t:"Foundational — cite"},
  method_to_borrow:{c:"#7c3aed",t:"Method to borrow"},
  background_context:{c:"#64748b",t:"Background"},
  optional:{c:"#94a3b8",t:"Optional"}
};
const recColor = r => (REC[r]||{c:"#94a3b8"}).c;
const recText  = r => (REC[r]||{t:r||""}).t;
// dark-ranged red→amber→green so the pill stays readable with white text
const scoreColor = d3.scaleLinear().domain([0,50,100]).range(["#c0392b","#b45309","#15803d"]).clamp(true);
const tint = (c,a) => { const x=d3.color(c); x.opacity=a; return x+""; };
function verdictBadge(v){
  const m={novel:{c:"#16a34a",t:"Novel"},incremental:{c:"#d97706",t:"Incremental"},
    substantially_covered:{c:"#ea580c",t:"Substantially covered"},likely_duplicated:{c:"#dc2626",t:"Likely duplicated"}};
  return m[v]||{c:"#64748b",t:v||"unknown"};
}
function escapeHtml(s){return (s==null?"":String(s)).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}

class IdeaCheckView {
  constructor(){
    this.papers=[]; this.byId={}; this._slug=""; this._recommended={}; this._cutoff=null;
    this.nodes=[{id:"__idea__",idea:true}]; this.links=[];
    const svg=d3.select("#graph");
    this.W=svg.node().clientWidth||1100; this.H=560;
    svg.attr("viewBox",`0 0 ${this.W} ${this.H}`);
    this.gG=svg.append("g");
    svg.call(d3.zoom().scaleExtent([0.3,3]).on("zoom",e=>this.gG.attr("transform",e.transform)));
    this.linkG=this.gG.append("g").attr("stroke","#cbd5e1");
    this.nodeG=this.gG.append("g");
    this.linkSel=this.linkG.selectAll("line");
    this.nodeSel=this.nodeG.selectAll("g");
    const self=this;
    this.sim=d3.forceSimulation(this.nodes)
      .force("link",d3.forceLink(this.links).id(d=>d.id).distance(d=>320-d.score*2.5).strength(d=>0.2+d.score/100*0.7))
      .force("charge",d3.forceManyBody().strength(-260))
      .force("center",d3.forceCenter(this.W/2,this.H/2))
      .force("collide",d3.forceCollide().radius(d=>self.rOf(d)+14))
      .on("tick",()=>self.tick());
    d3.selectAll("#table th[data-k]").on("click",function(){
      const k=this.getAttribute("data-k");
      if(k===self.sortKey)self.sortDir*=-1; else {self.sortKey=k;self.sortDir=-1;}
      self.renderTable();
    });
    this.sortKey="overlap_score"; this.sortDir=-1;
  }
  rOf(d){return d.idea?30:(8+d.overlap_score/100*22);}
  setIdea(idea,slug){ document.getElementById("idea").textContent=idea||""; this._slug=slug||""; this.renderMeta(); }
  setCutoff(c){ this._cutoff=c; this.renderMeta(); }
  renderMeta(){ document.getElementById("meta").textContent=this.papers.length+" paper"+(this.papers.length===1?"":"s")+" analyzed"+(this._cutoff?"  ·  literature as of "+this._cutoff:"")+(this._slug?"  ·  "+this._slug:""); }

  addPaper(p){
    if(!p)return;
    if(!p.id)p.id=p.paper_id;           // analyses carry paper_id; use it as the node id
    if(!p.id||this.byId[p.id])return;
    this.byId[p.id]=p; this.papers.push(p);
    this.nodes.push(Object.assign({id:p.id},p));
    this.links.push({source:"__idea__",target:p.id,score:p.overlap_score});
    this.updateGraph(); this.renderBars(); this.renderTable(); this.renderCounts(); this.renderReading(); this.renderMeta();
  }

  updateGraph(){
    const self=this;
    this.linkSel=this.linkG.selectAll("line").data(this.links,d=>(d.target.id||d.target))
      .join("line").attr("stroke-width",d=>1+d.score/100*5).attr("stroke-opacity",d=>0.18+d.score/100*0.5);
    this.nodeSel=this.nodeG.selectAll("g.node-g").data(this.nodes,d=>d.id).join(
      enter=>{
        const g=enter.append("g").attr("class","node-g").style("cursor","pointer")
          .call(d3.drag()
            .on("start",(e,d)=>{if(!e.active)self.sim.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;})
            .on("drag",(e,d)=>{d.fx=e.x;d.fy=e.y;})
            .on("end",(e,d)=>{if(!e.active)self.sim.alphaTarget(0);d.fx=null;d.fy=null;}))
          .on("click",(e,d)=>{if(!d.idea)self.openPaper(d.id);});
        g.append("circle").attr("r",d=>self.rOf(d))
          .attr("fill",d=>d.idea?"#5b5bd6":relColor(d.relationship))
          .attr("stroke",d=>d.idea?"#c7d0f7":"#ffffff").attr("stroke-width",d=>d.idea?3:1.5);
        g.append("text").attr("class","node-label").attr("text-anchor","middle").attr("dy",d=>self.rOf(d)+13)
          .text(d=>d.idea?"YOUR IDEA":(d.title||"").slice(0,42)+((d.title||"").length>42?"…":""));
        return g;
      }
    );
    this.sim.nodes(this.nodes);
    this.sim.force("link").links(this.links);
    this.sim.alpha(0.9).restart();
  }
  tick(){
    this.linkSel.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y).attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
    this.nodeSel.attr("transform",d=>`translate(${d.x},${d.y})`);
  }

  renderBars(){
    const ps=this.papers.slice().sort((a,b)=>b.overlap_score-a.overlap_score);
    const svg=d3.select("#bars"); svg.selectAll("*").remove();
    if(!ps.length)return;
    const W=svg.node().clientWidth||1100, rowH=26, M={l:230,r:46,t:18,b:8};
    const H=M.t+M.b+ps.length*rowH; svg.attr("viewBox",`0 0 ${W} ${H}`).attr("height",H);
    const x=d3.scaleLinear().domain([0,100]).range([M.l,W-M.r]);
    const y=d3.scaleBand().domain(ps.map(p=>p.id)).range([M.t,H-M.b]).padding(0.22);
    const g=svg.append("g"), self=this;
    g.append("g").attr("transform",`translate(0,${M.t})`).call(d3.axisTop(x).ticks(5).tickSize(-(H)))
      .call(s=>s.selectAll("line").attr("stroke","#eef0f4")).call(s=>s.select(".domain").remove())
      .call(s=>s.selectAll("text").attr("fill","#9aa1b2"));
    const rows=g.selectAll(".bar-row").data(ps).join("g").attr("class","bar-row").on("click",(e,p)=>self.openPaper(p.id));
    rows.append("rect").attr("x",x(0)).attr("y",p=>y(p.id)).attr("height",y.bandwidth())
      .attr("width",p=>x(p.overlap_score)-x(0)).attr("rx",4).attr("fill",p=>relColor(p.relationship));
    rows.append("text").attr("class","bar-label").attr("x",M.l-10).attr("y",p=>y(p.id)+y.bandwidth()/2+4).attr("text-anchor","end")
      .text(p=>(p.title||"").slice(0,40)+((p.title||"").length>40?"…":""));
    rows.append("text").attr("x",p=>x(p.overlap_score)+6).attr("y",p=>y(p.id)+y.bandwidth()/2+4)
      .attr("fill","#363c4a").attr("font-size",12).attr("font-weight",700).text(p=>p.overlap_score);
  }

  renderTable(){
    const tb=d3.select("#table tbody"); tb.selectAll("*").remove();
    const self=this;
    const rows=this.papers.slice().sort((a,b)=>{
      const av=a[self.sortKey],bv=b[self.sortKey];
      return (av<bv?-1:av>bv?1:0)*self.sortDir;
    });
    rows.forEach(p=>{
      const tr=tb.append("tr").attr("class","row").on("click",()=>self.openPaper(p.id));
      tr.append("td").html(`<span class="score-pill" style="background:${scoreColor(p.overlap_score)}">${p.overlap_score}</span>`);
      tr.append("td").html(`<span class="read-pill">${p.reading_value==null?"":p.reading_value}</span>`);
      tr.append("td").text(p.title||"");
      tr.append("td").html(`<span class="relbadge" style="background:${tint(relColor(p.relationship),0.12)};color:${relColor(p.relationship)}">${relText(p.relationship)}</span>`);
      tr.append("td").text(p.year||"");
      tr.append("td").html(`<span class="src">${p.evidence_source||""}</span>`);
    });
  }

  renderReading(){
    const ps=this.papers.slice().sort((a,b)=>(b.reading_value||0)-(a.reading_value||0));
    const el=document.getElementById("reading"); el.innerHTML="";
    if(!ps.length){ el.innerHTML="<span class='muted'>waiting for analyses…</span>"; return; }
    const self=this;
    ps.forEach(p=>{
      const pick=self._recommended[p.id];
      const row=document.createElement("div"); row.className="reading-row";
      row.onclick=()=>self.openPaper(p.id);
      row.innerHTML=`<span class="read-pill">${p.reading_value==null?"?":p.reading_value}</span>`
        +`<span class="recbadge" style="background:${tint(recColor(p.recommendation),0.14)};color:${recColor(p.recommendation)}">${recText(p.recommendation)}</span>`
        +`<div class="meta2"><div class="ttl">${escapeHtml(p.title||"")}`
        +(pick?` <span class="pick">★ top pick</span>`:``)+`</div>`
        +`<div class="why">${escapeHtml(pick||p.why_read||"")}</div></div>`;
      el.appendChild(row);
    });
  }

  setImprovements(imp){
    if(!imp)return;
    document.getElementById("improve-analysis").innerHTML=marked.parse(imp.analysis||"");
    const el=document.getElementById("improvements"); el.innerHTML="";
    const self=this;
    (imp.recommendations||[]).forEach(r=>{
      const srcs=(r.source_paper_ids||[]).map(id=>{
        const p=self.byId[id];
        return `<a href="${p?p.url:("https://www.alphaxiv.org/abs/"+id)}" target="_blank" rel="noopener">${escapeHtml(p?p.title:id)}</a>`;
      }).join(" · ");
      const d=document.createElement("div"); d.className="impr";
      d.innerHTML=`<h3>${escapeHtml(r.title||"")}</h3>`
        +`<div class="lbl">what it is</div><p>${escapeHtml(r.technique||"")}</p>`
        +`<div class="lbl">why it helps your idea</div><p>${escapeHtml(r.why_it_helps||"")}</p>`
        +`<div class="lbl">how to integrate</div><p>${escapeHtml(r.how_to_integrate||"")}</p>`
        +(srcs?`<div class="srcs"><span class="muted">from:</span> ${srcs}</div>`:``);
      el.appendChild(d);
    });
    document.getElementById("improve-card").style.display=(imp.recommendations||[]).length?"":"none";
  }

  renderCounts(){
    const el=document.getElementById("counts"); el.innerHTML="";
    const self=this;
    ["directly_overlapping","related_but_different","tangential"].forEach(r=>{
      const n=self.papers.filter(p=>p.relationship===r).length; if(!n)return;
      const d=document.createElement("div"); d.className="count";
      d.innerHTML=`<span class="dot" style="background:${relColor(r)}"></span>${n} ${relText(r)}`;
      el.appendChild(d);
    });
  }

  setScope(s){
    if(!s)return;
    document.getElementById("scope-bg").textContent=s.background||"";
    document.getElementById("scope-prop").textContent=s.proposal||"";
    const w=s.contribution_weight;
    const fill=document.getElementById("contrib-fill");
    fill.style.width=w+"%"; fill.style.background=scoreColor(w);
    document.getElementById("contrib-num").textContent=w+"/100";
    document.getElementById("contrib-assess").innerHTML=marked.parse(s.contribution_assessment||"");
    document.getElementById("scope-card").style.display="";
  }

  setFinal(f){
    if(!f)return;
    const sc=f.novelty_score;
    const svg=d3.select("#gauge"); svg.selectAll("*").remove();
    const cx=110,cy=130,R=92;
    const arc=d3.arc().innerRadius(R-18).outerRadius(R).startAngle(-Math.PI/2);
    svg.append("path").attr("transform",`translate(${cx},${cy})`).attr("d",arc.endAngle(Math.PI/2)()).attr("fill","#e7e9ee");
    svg.append("path").attr("transform",`translate(${cx},${cy})`).attr("d",arc.endAngle(-Math.PI/2+Math.PI*sc/100)()).attr("fill",scoreColor(sc));
    svg.append("text").attr("x",cx).attr("y",cy-18).attr("text-anchor","middle").attr("font-size",40).attr("font-weight",800).attr("fill","#111524").text(sc);
    svg.append("text").attr("x",cx).attr("y",cy+4).attr("text-anchor","middle").attr("font-size",12).attr("fill","#697086").text("novelty / 100");
    const vb=verdictBadge(f.verdict);
    document.getElementById("verdict").innerHTML=`<span class="verdict" style="background:${tint(vb.c,0.12)};color:${vb.c};border:1px solid ${tint(vb.c,0.35)}">${vb.t}</span>`;
    document.getElementById("summary").innerHTML=marked.parse(f.summary||"");
    if(f.differentiation){
      document.getElementById("differentiation").innerHTML=marked.parse(f.differentiation);
      document.getElementById("diff-card").style.display="";
    }
    const sug=document.getElementById("suggestions"); sug.innerHTML="";
    (f.differentiation_suggestions||[]).forEach(s=>{const li=document.createElement("li");li.textContent=s;sug.appendChild(li);});
    document.getElementById("sugg-card").style.display=(f.differentiation_suggestions||[]).length?"":"none";
    this._recommended={};
    (f.recommended_reading||[]).forEach(r=>{this._recommended[r.paper_id]=r.why;});
    this.renderReading();
  }

  openPaper(id){
    const p=this.byId[id]; if(!p)return;
    const lis=a=>(a&&a.length)?("<ul class='taglist'>"+a.map(s=>`<li>${escapeHtml(s)}</li>`).join("")+"</ul>"):"<div class='muted'>none</div>";
    document.getElementById("panel-body").innerHTML=`
      <h3>${escapeHtml(p.title||"")}</h3>
      <div class="kv"><span class="relbadge" style="background:${tint(relColor(p.relationship),0.12)};color:${relColor(p.relationship)}">${relText(p.relationship)}</span>
        &nbsp;<span class="score-pill" style="background:${scoreColor(p.overlap_score)}">${p.overlap_score}</span> overlap
        &nbsp;<span class="read-pill">${p.reading_value==null?"?":p.reading_value}</span> read
        &nbsp;<span class="src">judged from ${p.evidence_source||"?"}</span></div>
      <div class="kv"><b>Authors</b>${escapeHtml((p.authors||[]).join(", "))||"<span class='muted'>n/a</span>"}</div>
      <div class="kv"><b>Year</b>${escapeHtml(p.year||"n/a")} &nbsp; <a href="${p.url}" target="_blank" rel="noopener">open on alphaXiv ↗</a></div>
      <div class="kv"><b>In one line</b>${escapeHtml(p.one_line||"")}</div>
      <div class="kv"><b>Why read it</b><span class="recbadge" style="background:${tint(recColor(p.recommendation),0.14)};color:${recColor(p.recommendation)}">${recText(p.recommendation)}</span> ${escapeHtml(p.why_read||"")}</div>
      <div class="kv"><b>Key similarities</b>${lis(p.key_similarities)}</div>
      <div class="kv"><b>Key differences</b>${lis(p.key_differences)}</div>`;
    document.getElementById("panel").classList.add("open");
  }
}
document.addEventListener("keydown",e=>{if(e.key==="Escape")document.getElementById("panel").classList.remove("open");});
"""

REPORT_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Idea Novelty Check</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:28px 22px 80px}
"""
    + REPORT_CSS
    + """</style>
</head>
<body>
<div class="wrap">
  <h1>Idea Novelty Check</h1>
  <div class="sub">multi-agent prior-art check over alphaXiv</div>
"""
    + REPORT_BODY
    + """</div>
<script>
"""
    + REPORT_VIEW_JS
    + """
const DATA = __IDEACHECK_DATA__;
const V = new IdeaCheckView();
V.setIdea(DATA.idea, DATA.slug);
V.setCutoff(DATA.cutoff);
V.setScope(DATA.scope);
(DATA.papers||[]).forEach(p=>V.addPaper(p));
V.setFinal(DATA);
V.setImprovements(DATA.improvements);
</script>
</body>
</html>
"""
)


def build_report_html(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    report = json.loads((run_dir / "report.json").read_text())
    meta = json.loads((run_dir / "meta.json").read_text())
    papers = [json.loads(f.read_text()) for f in sorted((run_dir / "papers").glob("*.json"))]
    improvements_file = run_dir / "improvements.json"
    improvements = json.loads(improvements_file.read_text()) if improvements_file.exists() else None
    scope_file = run_dir / "scope.json"
    scope = json.loads(scope_file.read_text()) if scope_file.exists() else None

    data = {
        "idea": report["idea"],
        "slug": meta["slug"],
        "cutoff": meta["cutoff"],
        "scope": scope,
        "novelty_score": report["novelty_score"],
        "verdict": report["verdict"],
        "summary": report["summary"],
        "differentiation": report["differentiation"],
        "differentiation_suggestions": report["differentiation_suggestions"],
        "recommended_reading": report["recommended_reading"],
        "papers": papers,
        "improvements": improvements,
    }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = REPORT_TEMPLATE.replace("__IDEACHECK_DATA__", blob)
    out = run_dir / "report.html"
    out.write_text(html, encoding="utf-8")
    return out
