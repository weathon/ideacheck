# ideacheck

**Has someone already done your idea?** `ideacheck` is a multi-agent CLI + web GUI
that checks a research idea against the [alphaXiv](https://www.alphaxiv.org)
literature, explains how each existing paper is similar to and different from your
idea, and renders an interactive D3 report.

It is built on the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview)
and the [`alphaxiv-py`](https://github.com/petroslamb/alphaxiv-py) client.

## How it works (multi-agent)

```
orchestrator (agent model)     plans the run, then synthesizes the verdict + report
  ├─ query-planner (agent)     idea → diverse alphaXiv searches → candidate papers
  ├─ paper-analyst (agent)     one paper → overlap score + similarities/differences
  │     └─ overview-generator (overview model)   makes + caches an overview when a paper has none
  └─ (synthesis)               read_all_analyses → save_final_report
```

By default the agents run on **Sonnet** and the overview-generator on **Haiku**
(both configurable — see [Configuration](#configuration)).

The orchestrator delegates each candidate paper to a `paper-analyst` subagent (run
in parallel). Each analyst gathers the best available evidence in priority order —
**full text → AI overview → abstract** — and if a paper has no alphaXiv AI overview
it asks an `overview-generator` subagent to synthesize one (cached under
`~/.ideacheck/overview_cache/` for reuse). Every per-paper result is written to disk
as it completes, so a crash mid-run keeps all finished papers.

alphaXiv is queried through public endpoints — **no alphaXiv API key needed**.

## Setup

**1. Requirements**

- Python ≥ 3.12 (required by `alphaxiv-py`).
- A Claude credential (see step 3). The Claude Agent SDK ships its own bundled
  `claude` runtime, so you do **not** need to install Claude Code separately.

**2. Install**

```bash
pip install git+https://github.com/weathon/ideacheck.git
```

(or clone and `pip install -e .` for development.)

**3. Authenticate Claude** — pick either:

- **Reuse a Claude Code login:** if you have ever logged into
  [Claude Code](https://claude.com/claude-code) on this machine, ideacheck reuses
  that session automatically — nothing to set.
- **API key:** otherwise export a key:
  ```bash
  export ANTHROPIC_API_KEY=sk-ant-...
  ```

**4. alphaXiv** needs no setup — search/paper/overview/similar endpoints are
queried publicly, **no alphaXiv API key required**.

> Cost: a run uses Opus (orchestrator) + Sonnet (subagents). A broad idea that
> surfaces dozens of papers can cost a few dollars per run; a niche idea is
> cheaper. Generated overviews are cached under `~/.ideacheck/overview_cache/`
> and reused across runs.

## Usage

CLI:

```bash
ideacheck check "a diffusion model that edits 3D scenes from natural-language instructions"
ideacheck check --idea-file my_idea.txt --no-open
```

Each run writes `./ideacheck_runs/<timestamp>-<slug>/` containing `report.json`,
`papers/<id>.json` (one per paper), and a self-contained `report.html` that opens
automatically.

Web GUI:

```bash
ideacheck serve --port 8000
# open http://127.0.0.1:8000 , type your idea, hit "Check novelty"
```

The GUI streams the agents' activity live and **builds the report progressively**:
each paper's node drops into the similarity graph the moment its analyst finishes,
and the novelty gauge + synthesis fill in once the orchestrator wraps up.

## The report

The HTML report (interactive, D3-powered) shows:

- a **novelty gauge** (0–100) and verdict (novel / incremental / substantially covered / likely duplicated),
- a **force-directed similarity network** with your idea at the center and each paper sized & pulled in by its overlap score,
- an **overlap bar chart**, a sortable **paper table**, and a click-through detail panel with each paper's key similarities and differences,
- the orchestrator's **synthesis** and concrete **differentiation suggestions**.

## Configuration

Models are set in `ideacheck/config.py` and can be overridden with environment
variables (no code change needed):

| Variable | Used by | Default |
| --- | --- | --- |
| `IDEACHECK_AGENT_MODEL` | orchestrator + query-planner + paper-analyst | `sonnet` |
| `IDEACHECK_OVERVIEW_MODEL` | overview-generator | `haiku` |

Values accept SDK aliases (`sonnet`, `haiku`, `opus`, `fable`) or a full model id.

```bash
# e.g. run the agents on Opus for a deeper (pricier) pass
IDEACHECK_AGENT_MODEL=opus ideacheck check "my idea"
```

## License

MIT
