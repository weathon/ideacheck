#!/usr/bin/env python3
"""Convert ideacheck run directory (JSON files) to markdown + HTML report.

Usage:
  python ideacheck/render.py <run_dir>

Reads: meta.json, scope.json, papers/*.json, report.json, improvements.json, filter.json
Writes: report.md, report.html

No numeric scores anywhere — every judgment is categorical (overlap_kind, relationship,
recommendation, verdict) and grouped, never ranked by a made-up number.
"""

import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])

report = json.loads((run_dir / "report.json").read_text())
meta = json.loads((run_dir / "meta.json").read_text())
papers = [json.loads(f.read_text()) for f in sorted((run_dir / "papers").glob("*.json"))]
improvements = json.loads((run_dir / "improvements.json").read_text()) if (run_dir / "improvements.json").exists() else None
scope = json.loads((run_dir / "scope.json").read_text()) if (run_dir / "scope.json").exists() else None

# ── categorical vocabulary (shared between md + html) ─────────────────────

KIND_ORDER = ["same_contribution", "same_tool_only", "same_problem_only", "different"]
KIND_TEXT = {
    "same_contribution": "Same contribution",
    "same_tool_only": "Same tool only",
    "same_problem_only": "Same problem only",
    "different": "Different",
}
REC_TEXT = {
    "closest_prior_work": "Closest prior work",
    "baseline_to_compare": "Baseline to compare",
    "foundational_to_cite": "Foundational - cite",
    "method_to_borrow": "Method to borrow",
    "background_context": "Background",
    "optional": "Optional",
}
REC_ORDER = list(REC_TEXT.keys())


def kind_of(p):
    """Overlap kind from the filter; fall back from same_contribution / relationship if absent."""
    k = p.get("overlap_kind")
    if k in KIND_TEXT:
        return k
    if p.get("same_contribution"):
        return "same_contribution"
    rel = p.get("relationship")
    if rel == "directly_overlapping":
        return "same_contribution"
    if rel == "tangential":
        return "different"
    return "same_problem_only"


# ── markdown report ──────────────────────────────────────────────────────

lines = []
lines.append(f"# Idea Novelty Check")
lines.append("")
lines.append(f"**Run:** {meta['slug']}")
if meta.get("cutoff"):
    lines.append(f"**Literature cutoff:** {meta['cutoff']}")
lines.append("")

lines.append("## The Idea")
lines.append("")
lines.append(report["idea"])
lines.append("")

if scope:
    lines.append("## Scope")
    lines.append("")
    lines.append("### Background (assumed given)")
    lines.append("")
    lines.append(scope["background"])
    lines.append("")
    lines.append("### Your Proposal (evaluated for novelty)")
    lines.append("")
    lines.append(scope["proposal"])
    lines.append("")
    if scope.get("contribution_assessment"):
        lines.append("### Contribution (proposal vs background)")
        lines.append("")
        lines.append(scope["contribution_assessment"])
        lines.append("")

lines.append("## Novelty Verdict")
lines.append("")
lines.append(f"- **Verdict:** {report['verdict']}")
lines.append("")

lines.append("## Synthesis")
lines.append("")
lines.append(report["summary"])
lines.append("")

if report.get("differentiation"):
    lines.append("## How Your Idea Differs from Prior Work")
    lines.append("")
    lines.append(report["differentiation"])
    lines.append("")

if report.get("recommended_reading"):
    lines.append("## Recommended Reading")
    lines.append("")
    for i, r in enumerate(report["recommended_reading"], 1):
        pid = r["paper_id"]
        paper_data = next((p for p in papers if p["paper_id"] == pid), None)
        title = paper_data["title"] if paper_data else pid
        lines.append(f"{i}. **{title}** (`{pid}`) — {r['why']}")
    lines.append("")

if improvements and improvements.get("recommendations"):
    lines.append("## Methods to Consider Adding")
    lines.append("")
    if improvements.get("analysis"):
        lines.append(improvements["analysis"])
        lines.append("")
    for r in improvements["recommendations"]:
        lines.append(f"### {r['title']}")
        lines.append("")
        lines.append(f"**What it is:** {r['technique']}")
        lines.append("")
        lines.append(f"**Why it helps:** {r['why_it_helps']}")
        lines.append("")
        lines.append(f"**How to integrate:** {r['how_to_integrate']}")
        lines.append("")
        if r.get("source_paper_ids"):
            lines.append(f"**Sources:** {', '.join(r['source_paper_ids'])}")
            lines.append("")

if report.get("differentiation_suggestions"):
    lines.append("## How to Differentiate Further")
    lines.append("")
    for s in report["differentiation_suggestions"]:
        lines.append(f"- {s}")
    lines.append("")

if papers:
    lines.append("## All Analyzed Papers")
    lines.append("")
    lines.append("Grouped by what they actually share with the proposal (per the overlap filter). "
                 "Only **Same contribution** papers are genuine prior art; the rest share only a tool, a problem, or nothing.")
    lines.append("")
    for kind in KIND_ORDER:
        group = sorted([p for p in papers if kind_of(p) == kind], key=lambda x: (x.get("title") or "").lower())
        if not group:
            continue
        lines.append(f"### {KIND_TEXT[kind]} ({len(group)})")
        lines.append("")
        lines.append("| Title | Relationship | Recommendation | Year | Source |")
        lines.append("|-------|--------------|----------------|------|--------|")
        for p in group:
            lines.append(f"| {p['title']} | {p.get('relationship', '')} | "
                         f"{REC_TEXT.get(p.get('recommendation'), p.get('recommendation', ''))} | "
                         f"{p.get('year', '')} | {p.get('evidence_source', '')} |")
        lines.append("")
    lines.append("### Paper Details")
    lines.append("")
    ordered = sorted(papers, key=lambda x: (KIND_ORDER.index(kind_of(x)), (x.get("title") or "").lower()))
    for p in ordered:
        lines.append(f"#### {p['title']} (`{p['paper_id']}`)")
        lines.append("")
        lines.append(f"- **Overlap:** {KIND_TEXT[kind_of(p)]} ({p.get('relationship', '')})")
        if p.get("filter_reason"):
            lines.append(f"- **Filter verdict:** {p['filter_reason']}")
        lines.append(f"- **Recommendation:** {REC_TEXT.get(p.get('recommendation'), p.get('recommendation', ''))}")
        lines.append(f"- **One line:** {p['one_line']}")
        lines.append(f"- **Why read:** {p.get('why_read', '')}")
        lines.append(f"- **Evidence:** {p.get('evidence_source', '')}")
        lines.append(f"- **URL:** {p.get('url', '')}")
        if p.get("key_similarities"):
            lines.append(f"- **Key similarities:**")
            for s in p["key_similarities"]:
                lines.append(f"  - {s}")
        if p.get("key_differences"):
            lines.append(f"- **Key differences:**")
            for d in p["key_differences"]:
                lines.append(f"  - {d}")
        lines.append("")

md_text = "\n".join(lines)
(run_dir / "report.md").write_text(md_text, encoding="utf-8")
print(f"wrote {run_dir / 'report.md'}")

# ── HTML report (D3 interactive visualization) ───────────────────────────

REPORT_CSS = r"""
:root{
  --bg:#f5f6f8; --panel:#ffffff; --panel2:#f7f8fa; --line:#e7e9ee; --line2:#eef0f4;
  --text:#202330; --muted:#697086; --idea:#5b5bd6; --accent:#4f46e5;
  --shadow:0 1px 2px rgba(17,24,39,.04), 0 6px 20px rgba(17,24,39,.06);
}
*{box-sizing:border-box}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
h1{font-size:27px;margin:0 0 4px;letter-spacing:-.02em;color:#111524;font-weight:700}
h2{font-size:15px;color:#111524;margin:0 0 14px;font-weight:650;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13.5px;margin-bottom:26px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin-bottom:18px;box-shadow:var(--shadow)}
.grid{display:grid;grid-template-columns:300px 1fr;gap:26px}
.idea-box{background:var(--panel2);border-left:3px solid var(--idea);border-radius:8px;padding:13px 15px;color:#374151;white-space:pre-wrap}
.verdict-wrap{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.verdict{display:inline-block;padding:8px 18px;border-radius:999px;font-weight:700;font-size:16px;margin-top:4px}
.verdict-cap{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}
.counts{display:flex;gap:14px;margin-top:18px;flex-wrap:wrap;justify-content:center}
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
th{color:var(--muted);font-weight:600;user-select:none}
tr.row{cursor:pointer} tr.row:hover{background:#f6f8fb}
tr.grouphdr td{background:#f3f4f8;font-weight:700;color:#111524;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.suggestions li{margin:6px 0}
.kindpill{display:inline-block;padding:3px 9px;border-radius:6px;font-size:12px;font-weight:600;color:#fff}
#panel{position:fixed;top:0;right:0;width:460px;max-width:92vw;height:100%;background:var(--panel);border-left:1px solid var(--line);box-shadow:-18px 0 48px rgba(17,24,39,.14);transform:translateX(100%);transition:transform .22s ease;overflow-y:auto;z-index:50;padding:24px}
#panel.open{transform:translateX(0)}
#panel .close{position:absolute;top:16px;right:18px;cursor:pointer;color:var(--muted);font-size:24px;line-height:1}
#panel h3{margin:2px 40px 8px 0;font-size:18px;color:#111524}
.kv{margin:11px 0} .kv b{color:var(--muted);font-weight:600;font-size:11px;display:block;margin-bottom:3px;text-transform:uppercase;letter-spacing:.04em}
.taglist{margin:6px 0 0;padding-left:18px} .taglist li{margin:4px 0}
.relbadge{display:inline-block;padding:3px 9px;border-radius:6px;font-size:12px;font-weight:600}
.recbadge{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;white-space:nowrap}
.src{font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:6px;padding:1px 6px}
.filterbox{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:9px 11px;color:#7c2d12;font-size:12.5px;margin:8px 0}
.reading-row{display:flex;gap:11px;align-items:flex-start;padding:11px 0;border-bottom:1px solid var(--line2);cursor:pointer}
.reading-row:hover{background:#f6f8fb}
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
@media(max-width:680px){.scope-grid{grid-template-columns:1fr}}
"""

REPORT_BODY = r"""
  <div class="card grid">
    <div class="verdict-wrap">
      <div class="verdict-cap">Novelty verdict</div>
      <div id="verdict"></div>
      <div class="counts" id="counts"></div>
    </div>
    <div>
      <h2>The idea</h2>
      <div class="idea-box" id="idea"></div>
      <h2 style="margin-top:18px">Synthesis</h2>
      <div class="summary" id="summary"><span class="muted">waiting for the synthesis...</span></div>
    </div>
  </div>

  <div class="card" id="scope-card" style="display:none">
    <h2>What you're actually proposing <span class="muted" style="font-weight:400;font-size:13px">- only this part is checked for novelty</span></h2>
    <div class="scope-grid">
      <div><div class="lbl2">Background (assumed given)</div><div class="scope-bg" id="scope-bg"></div></div>
      <div><div class="lbl2">Your proposal (evaluated)</div><div class="scope-prop" id="scope-prop"></div></div>
    </div>
    <div class="contrib" id="contrib-wrap" style="display:none">
      <div class="lbl2">Contribution - proposal vs background</div>
      <div class="summary" id="contrib-assess"></div>
    </div>
  </div>

  <div class="card" id="diff-card" style="display:none">
    <h2>How your idea differs from prior work</h2>
    <div class="summary" id="differentiation"></div>
  </div>

  <div class="card">
    <h2>Similarity network <span class="muted" id="meta" style="font-weight:400;font-size:13px"></span></h2>
    <div class="legend" id="legend">
      <div class="item"><span class="dot" style="background:var(--idea)"></span>Your idea</div>
      <div class="item muted">(color = what it shares with you; closeness = same-thing-done; drag, click for detail)</div>
    </div>
    <svg id="graph"></svg>
  </div>

  <div class="card" id="reading-card">
    <h2>Recommended reading <span class="muted" style="font-weight:400;font-size:13px">- papers worth reading, grouped by role (not by a score)</span></h2>
    <div id="reading"><span class="muted">waiting for analyses...</span></div>
  </div>

  <div class="card" id="improve-card" style="display:none">
    <h2>Methods to consider adding <span class="muted" style="font-weight:400;font-size:13px">- in-depth analysis</span></h2>
    <div class="summary" id="improve-analysis"></div>
    <div id="improvements"></div>
  </div>

  <div class="card" id="sugg-card" style="display:none">
    <h2>How to differentiate further</h2>
    <ul class="suggestions" id="suggestions"></ul>
  </div>

  <div class="card">
    <h2>All analyzed papers <span class="muted" style="font-weight:400;font-size:13px">- grouped by what they actually share; only "Same contribution" is genuine prior art</span></h2>
    <table id="table"><thead><tr>
      <th>Title</th><th>Relationship</th><th>Recommendation</th><th>Year</th><th>Source</th>
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
  foundational_to_cite:{c:"#2563eb",t:"Foundational - cite"},
  method_to_borrow:{c:"#7c3aed",t:"Method to borrow"},
  background_context:{c:"#64748b",t:"Background"},
  optional:{c:"#94a3b8",t:"Optional"}
};
const recColor = r => (REC[r]||{c:"#94a3b8"}).c;
const recText  = r => (REC[r]||{t:r||""}).t;
const RECORDER = ["closest_prior_work","baseline_to_compare","foundational_to_cite","method_to_borrow","background_context","optional"];
// overlap kind = the filter's categorical verdict. No numbers; the weight below only
// shapes the force layout (closer = more genuinely the same thing), it is never shown.
const KIND = {
  same_contribution:{c:"#dc2626",t:"Same contribution",w:90,r:26},
  same_tool_only:   {c:"#d97706",t:"Same tool only",   w:48,r:18},
  same_problem_only:{c:"#0891b2",t:"Same problem only",w:34,r:15},
  different:        {c:"#16a34a",t:"Different",         w:14,r:12}
};
const KINDORDER = ["same_contribution","same_tool_only","same_problem_only","different"];
function kindOf(p){
  if(p.overlap_kind && KIND[p.overlap_kind]) return p.overlap_kind;
  if(p.same_contribution) return "same_contribution";
  if(p.relationship==="directly_overlapping") return "same_contribution";
  if(p.relationship==="tangential") return "different";
  return "same_problem_only";
}
const kindColor = p => KIND[kindOf(p)].c;
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
      .force("link",d3.forceLink(this.links).id(d=>d.id).distance(d=>320-d.w*2.5).strength(d=>0.2+d.w/100*0.7))
      .force("charge",d3.forceManyBody().strength(-260))
      .force("center",d3.forceCenter(this.W/2,this.H/2))
      .force("collide",d3.forceCollide().radius(d=>self.rOf(d)+14))
      .on("tick",()=>self.tick());
  }
  rOf(d){return d.idea?30:KIND[kindOf(d)].r;}
  setIdea(idea,slug){ document.getElementById("idea").textContent=idea||""; this._slug=slug||""; this.renderMeta(); }
  setCutoff(c){ this._cutoff=c; this.renderMeta(); }
  renderMeta(){ document.getElementById("meta").textContent=this.papers.length+" paper"+(this.papers.length===1?"":"s")+" analyzed"+(this._cutoff?"  ·  literature as of "+this._cutoff:"")+(this._slug?"  ·  "+this._slug:""); }

  addPaper(p){
    if(!p)return;
    if(!p.id)p.id=p.paper_id;
    if(!p.id||this.byId[p.id])return;
    this.byId[p.id]=p; this.papers.push(p);
    this.nodes.push(Object.assign({id:p.id},p));
    this.links.push({source:"__idea__",target:p.id,w:KIND[kindOf(p)].w});
    this.updateGraph(); this.renderTable(); this.renderCounts(); this.renderLegend(); this.renderReading(); this.renderMeta();
  }

  updateGraph(){
    const self=this;
    this.linkSel=this.linkG.selectAll("line").data(this.links,d=>(d.target.id||d.target))
      .join("line").attr("stroke-width",d=>1+d.w/100*5).attr("stroke-opacity",d=>0.18+d.w/100*0.5);
    this.nodeSel=this.nodeG.selectAll("g.node-g").data(this.nodes,d=>d.id).join(
      enter=>{
        const g=enter.append("g").attr("class","node-g").style("cursor","pointer")
          .call(d3.drag()
            .on("start",(e,d)=>{if(!e.active)self.sim.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;})
            .on("drag",(e,d)=>{d.fx=e.x;d.fy=e.y;})
            .on("end",(e,d)=>{if(!e.active)self.sim.alphaTarget(0);d.fx=null;d.fy=null;}))
          .on("click",(e,d)=>{if(!d.idea)self.openPaper(d.id);});
        g.append("circle").attr("r",d=>self.rOf(d))
          .attr("fill",d=>d.idea?"#5b5bd6":kindColor(d))
          .attr("stroke",d=>d.idea?"#c7d0f7":"#ffffff").attr("stroke-width",d=>d.idea?3:1.5);
        g.append("text").attr("class","node-label").attr("text-anchor","middle").attr("dy",d=>self.rOf(d)+13)
          .text(d=>d.idea?"YOUR IDEA":(d.title||"").slice(0,42)+((d.title||"").length>42?"...":""));
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

  renderTable(){
    const tb=d3.select("#table tbody"); tb.selectAll("*").remove();
    const self=this;
    KINDORDER.forEach(kind=>{
      const group=this.papers.filter(p=>kindOf(p)===kind)
        .sort((a,b)=>(a.title||"").toLowerCase()<(b.title||"").toLowerCase()?-1:1);
      if(!group.length)return;
      const hdr=tb.append("tr").attr("class","grouphdr");
      hdr.append("td").attr("colspan",5)
        .html(`<span class="dot" style="display:inline-block;background:${KIND[kind].c}"></span>&nbsp;${KIND[kind].t} (${group.length})`);
      group.forEach(p=>{
        const tr=tb.append("tr").attr("class","row").on("click",()=>self.openPaper(p.id));
        tr.append("td").text(p.title||"");
        tr.append("td").html(`<span class="relbadge" style="background:${tint(relColor(p.relationship),0.12)};color:${relColor(p.relationship)}">${relText(p.relationship)}</span>`);
        tr.append("td").html(`<span class="recbadge" style="background:${tint(recColor(p.recommendation),0.14)};color:${recColor(p.recommendation)}">${recText(p.recommendation)}</span>`);
        tr.append("td").text(p.year||"");
        tr.append("td").html(`<span class="src">${p.evidence_source||""}</span>`);
      });
    });
  }

  renderReading(){
    // grouped by recommendation role, not ranked by a number; top picks first within role
    const self=this;
    const ps=this.papers.slice().sort((a,b)=>{
      const ai=RECORDER.indexOf(a.recommendation), bi=RECORDER.indexOf(b.recommendation);
      const aa=ai<0?99:ai, bb=bi<0?99:bi;
      if(aa!==bb)return aa-bb;
      const ap=self._recommended[a.id]?0:1, bp=self._recommended[b.id]?0:1;
      return ap-bp;
    });
    const el=document.getElementById("reading"); el.innerHTML="";
    if(!ps.length){ el.innerHTML="<span class='muted'>waiting for analyses...</span>"; return; }
    ps.forEach(p=>{
      const pick=self._recommended[p.id];
      const row=document.createElement("div"); row.className="reading-row";
      row.onclick=()=>self.openPaper(p.id);
      row.innerHTML=`<span class="recbadge" style="background:${tint(recColor(p.recommendation),0.14)};color:${recColor(p.recommendation)}">${recText(p.recommendation)}</span>`
        +`<div class="meta2"><div class="ttl">${escapeHtml(p.title||"")}`
        +(pick?` <span class="pick">top pick</span>`:``)+`</div>`
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

  renderLegend(){
    const el=document.getElementById("legend"); el.innerHTML="";
    const idea=document.createElement("div"); idea.className="item";
    idea.innerHTML=`<span class="dot" style="background:var(--idea)"></span>Your idea`;
    el.appendChild(idea);
    const self=this;
    KINDORDER.forEach(k=>{
      if(!self.papers.some(p=>kindOf(p)===k))return;
      const d=document.createElement("div"); d.className="item";
      d.innerHTML=`<span class="dot" style="background:${KIND[k].c}"></span>${KIND[k].t}`;
      el.appendChild(d);
    });
    const note=document.createElement("div"); note.className="item muted";
    note.textContent="(color = what it shares; closeness = same-thing-done; drag, click for detail)";
    el.appendChild(note);
  }

  renderCounts(){
    const el=document.getElementById("counts"); el.innerHTML="";
    const self=this;
    KINDORDER.forEach(k=>{
      const n=self.papers.filter(p=>kindOf(p)===k).length; if(!n)return;
      const d=document.createElement("div"); d.className="count";
      d.innerHTML=`<span class="dot" style="background:${KIND[k].c}"></span>${n} ${KIND[k].t}`;
      el.appendChild(d);
    });
  }

  setScope(s){
    if(!s)return;
    document.getElementById("scope-bg").textContent=s.background||"";
    document.getElementById("scope-prop").textContent=s.proposal||"";
    if(s.contribution_assessment){
      document.getElementById("contrib-assess").innerHTML=marked.parse(s.contribution_assessment);
      document.getElementById("contrib-wrap").style.display="";
    }
    document.getElementById("scope-card").style.display="";
  }

  setFinal(f){
    if(!f)return;
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
    const k=kindOf(p);
    const lis=a=>(a&&a.length)?("<ul class='taglist'>"+a.map(s=>`<li>${escapeHtml(s)}</li>`).join("")+"</ul>"):"<div class='muted'>none</div>";
    document.getElementById("panel-body").innerHTML=`
      <h3>${escapeHtml(p.title||"")}</h3>
      <div class="kv"><span class="kindpill" style="background:${KIND[k].c}">${KIND[k].t}</span>
        &nbsp;<span class="relbadge" style="background:${tint(relColor(p.relationship),0.12)};color:${relColor(p.relationship)}">${relText(p.relationship)}</span>
        &nbsp;<span class="src">judged from ${p.evidence_source||"?"}</span></div>
      ${p.filter_reason?`<div class="filterbox"><b>Overlap filter:</b> ${escapeHtml(p.filter_reason)}</div>`:``}
      <div class="kv"><b>Authors</b>${escapeHtml((p.authors||[]).join(", "))||"<span class='muted'>n/a</span>"}</div>
      <div class="kv"><b>Year</b>${escapeHtml(p.year||"n/a")} &nbsp; <a href="${p.url}" target="_blank" rel="noopener">open on alphaXiv</a></div>
      <div class="kv"><b>In one line</b>${escapeHtml(p.one_line||"")}</div>
      <div class="kv"><b>Why read it</b><span class="recbadge" style="background:${tint(recColor(p.recommendation),0.14)};color:${recColor(p.recommendation)}">${recText(p.recommendation)}</span> ${escapeHtml(p.why_read||"")}</div>
      <div class="kv"><b>Key similarities</b>${lis(p.key_similarities)}</div>
      <div class="kv"><b>Key differences</b>${lis(p.key_differences)}</div>`;
    document.getElementById("panel").classList.add("open");
  }
}
document.addEventListener("keydown",e=>{if(e.key==="Escape")document.getElementById("panel").classList.remove("open");});
"""

data = {
    "idea": report["idea"],
    "slug": meta["slug"],
    "cutoff": meta.get("cutoff"),
    "scope": scope,
    "verdict": report["verdict"],
    "summary": report["summary"],
    "differentiation": report.get("differentiation"),
    "differentiation_suggestions": report.get("differentiation_suggestions"),
    "recommended_reading": report.get("recommended_reading"),
    "papers": papers,
    "improvements": improvements,
}
blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Idea Novelty Check</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1280px;margin:0 auto;padding:28px 22px 80px}}
{REPORT_CSS}
</style>
</head>
<body>
<div class="wrap">
  <h1>Idea Novelty Check</h1>
  <div class="sub">multi-agent prior-art check over alphaXiv</div>
{REPORT_BODY}
</div>
<script>
{REPORT_VIEW_JS}
const DATA = {blob};
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

(run_dir / "report.html").write_text(html, encoding="utf-8")
print(f"wrote {run_dir / 'report.html'}")
