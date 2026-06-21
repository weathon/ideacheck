"""FastAPI GUI for ideacheck.

The page embeds the SAME D3 view used by the static report (REPORT_BODY +
REPORT_VIEW_JS). As the pipeline streams SSE events, the browser drives the view
live: each {type:"paper"} event drops a node into the similarity graph, and the
final {type:"final"} event fills the novelty gauge, verdict, synthesis, and
differentiation suggestions. The report therefore builds in real time while the
agents are still working.

create_app(base_dir):
  GET /                         the single-page GUI (input + activity log + live report)
  GET /api/stream?idea=...      runs the pipeline, streams progress events as SSE
  GET /runs/<slug>/report.html  serves the saved static report
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from .pipeline import make_run_dir, run_idea_check
from .report import REPORT_BODY, REPORT_CSS, REPORT_VIEW_JS, build_report_html

GUI_HTML = (
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>ideacheck</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{padding:16px 22px;border-bottom:1px solid var(--line);display:flex;align-items:baseline;gap:12px}
header h1{font-size:18px;margin:0} header .tag{color:var(--muted);font-size:13px}
.wrap{max-width:1280px;margin:0 auto;padding:22px}
textarea{width:100%;min-height:84px;background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:12px 14px;font:inherit;resize:vertical}
.row{display:flex;gap:12px;align-items:center;margin:12px 0}
button{background:var(--idea);color:#fff;border:0;border-radius:9px;padding:10px 18px;font-weight:600;cursor:pointer}
button:disabled{opacity:.5;cursor:not-allowed}
.statusline{color:var(--muted);font-size:13px}
a.dl{color:#60a5fa;font-size:13px;margin-left:6px;display:none}
#log{margin:0 0 20px;background:#0e1320;border:1px solid var(--line);border-radius:10px;padding:10px 14px;max-height:200px;overflow:auto;font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
#log .ev{padding:1px 0;white-space:pre-wrap;word-break:break-word}
#log .ev .t{display:inline-block;min-width:88px;color:var(--idea);font-weight:600}
#log .ev.sub .t{color:#a78bfa} #log .ev.delegate .t{color:#f59e0b} #log .ev.tool .t{color:#22c55e}
#log .ev.paper .t{color:#22d3ee} #log .ev.result .t{color:#e5e7eb} #log .ev.err .t{color:#ef4444}
"""
    + REPORT_CSS
    + """</style>
</head>
<body>
<header><h1>ideacheck</h1><span class="tag">has someone already done your idea? — multi-agent check over alphaXiv</span></header>
<div class="wrap">
  <textarea id="idea-input" placeholder="Describe your research idea in a few sentences..."></textarea>
  <div class="row">
    <button id="run">Check novelty</button>
    <span class="statusline" id="status"></span>
    <a class="dl" id="dl" target="_blank">open saved report ↗</a>
  </div>
  <div id="log"></div>
"""
    + REPORT_BODY
    + """</div>
<script>
"""
    + REPORT_VIEW_JS
    + """
const $=id=>document.getElementById(id);
let es=null, V=null;
function logline(ev){
  const d=document.createElement("div"); let cls="ev",t=ev.type,body="";
  if(ev.type==="text"){ cls+=ev.scope==="subagent"?" sub":""; t=ev.scope; body=ev.text; }
  else if(ev.type==="delegate"){ cls+=" delegate"; t="→ "+ev.agent; body=ev.task; }
  else if(ev.type==="tool"){ cls+=" tool"; t=ev.name.replace("mcp__axv__",""); body=JSON.stringify(ev.args||{}); }
  else if(ev.type==="paper"){ cls+=" paper"; t="analyzed"; body=`[${ev.overlap_score}/${ev.reading_value}] ${ev.title}`; }
  else if(ev.type==="final"){ t="synthesis"; body=`novelty ${ev.novelty_score} · ${ev.verdict}`; }
  else if(ev.type==="improvements"){ t="methods"; body=`${(ev.recommendations||[]).length} method suggestions`; }
  else if(ev.type==="result"){ cls+=" result"; t="done"; body=`turns ${ev.turns} · $${(ev.cost_usd||0).toFixed(3)} · ${(ev.duration_ms/1000).toFixed(1)}s`; }
  else if(ev.type==="start"){ t="start"; body=ev.run_dir; }
  else { body=JSON.stringify(ev); }
  d.className=cls; d.innerHTML=`<span class="t">${t}</span> `+escapeHtml(body);
  $("log").appendChild(d); $("log").scrollTop=$("log").scrollHeight;
}
$("run").onclick=()=>{
  const idea=$("idea-input").value.trim(); if(!idea)return;
  if(es)es.close();
  $("log").innerHTML=""; $("dl").style.display="none";
  $("run").disabled=true; $("status").textContent="agents working…";
  V=new IdeaCheckView(); V.setIdea(idea,"");
  es=new EventSource("/api/stream?idea="+encodeURIComponent(idea));
  es.onmessage=e=>{
    const ev=JSON.parse(e.data); logline(ev);
    if(ev.type==="start"){ V.setIdea(ev.idea,""); }
    else if(ev.type==="paper"){ V.addPaper(ev); $("status").textContent=V.papers.length+" papers analyzed…"; }
    else if(ev.type==="final"){ V.setFinal(ev); $("status").textContent="synthesizing report…"; }
    else if(ev.type==="improvements"){ V.setImprovements(ev); $("status").textContent="method advice ready…"; }
    else if(ev.type==="report"){ $("dl").href=ev.url; $("dl").style.display="inline"; $("status").textContent="report ready"; }
    else if(ev.type==="result"){ $("run").disabled=false; es.close(); }
  };
  es.onerror=()=>{ $("status").textContent="stream error (see terminal)"; $("run").disabled=false; if(es)es.close(); };
};
</script>
</body>
</html>
"""
)


def create_app(base_dir: Path) -> FastAPI:
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="ideacheck")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return GUI_HTML

    @app.get("/api/stream")
    async def stream(idea: str):
        async def gen():
            run_dir = make_run_dir(idea, base_dir)
            async for ev in run_idea_check(idea, run_dir):
                yield "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
                if ev["type"] == "result":
                    build_report_html(run_dir)
                    yield "data: " + json.dumps({"type": "report", "url": f"/runs/{run_dir.name}/report.html"}) + "\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/runs/{slug}/report.html", response_class=HTMLResponse)
    async def report(slug: str):
        return FileResponse(base_dir / slug / "report.html", media_type="text/html")

    return app
