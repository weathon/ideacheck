# ideacheck

`ideacheck` is a multi-agent CLI + web GUI that takes a research idea, mines the
[alphaXiv](https://www.alphaxiv.org) literature, and produces five things:

0. **Scope split** — first, from your own words (no lookup), it separates the **background** you assume from the part you actually **propose**, and rates how big the proposal is relative to that background (0–100). Novelty is then checked on the *proposal only*, so shared background doesn't count as overlap.
1. **Novelty** — has someone already done the proposed part? a 0–100 score + verdict.
2. **Differentiation** — concretely how the proposal differs from / improves on the closest prior work (positioning).
3. **Recommended reading** — the papers you should actually read while writing, ranked by value to your paper (a baseline to compare, a method to cite/borrow) — *not* just by overlap.
4. **Methods to add** — an in-depth (Opus) analysis of concrete techniques from the literature you could fold into your own method to make it stronger.

It renders all of this as an interactive D3 report, and is built on the
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview) and the
[`alphaxiv-py`](https://github.com/petroslamb/alphaxiv-py) client.

## How it works (multi-agent)

```
orchestrator (agent model)     split idea → background vs proposal (no lookup), then coordinate + synthesize
  ├─ query-planner (agent)     proposal → diverse searches → overlap candidates + read-worthy papers
  ├─ paper-analyst (agent)     one paper → overlap (vs proposal) + reading value + similarities/differences
  │     └─ overview-generator (overview model)   makes + caches an overview when a paper has none
  ├─ method-advisor (improve model)   in-depth: methods to fold in to improve the idea
  └─ (synthesis)               read_all_analyses → save_final_report
```

By default the agents run on **Sonnet**, the overview-generator on **Haiku**, and
the in-depth method-advisor on **Opus** (all configurable — see
[Configuration](#configuration)).

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

> Cost: a run uses Sonnet (agents) + Haiku (overviews) + one Opus pass (the
> method-advisor). A broad idea that surfaces dozens of papers can cost a few
> dollars per run; a niche idea is cheaper. The run prints its cost at the end —
> shown as **saved** (the equivalent API cost, $0 on a Claude subscription) or
> **billed** (when `ANTHROPIC_API_KEY` is set). Generated overviews are cached
> under `~/.ideacheck/overview_cache/` and reused across runs.

## Usage

CLI:

```bash
ideacheck check "a diffusion model that edits 3D scenes from natural-language instructions"
ideacheck check --idea-file my_idea.txt --no-open

# time cutoff: only consider papers published before a date — feed an
# already-published paper's idea and cut off just before it appeared to test
# whether the tool would have flagged the prior art (the paper itself and
# anything newer are excluded):
ideacheck check --before 2023-05-01 "the core idea of the paper under test"
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

- **"What you're actually proposing"** — the background-vs-proposal split and a contribution-size bar,
- a **novelty gauge** (0–100) and verdict (novel / incremental / substantially covered / likely duplicated),
- a **"How your idea differs from prior work"** positioning section,
- a **force-directed similarity network** (idea at the center, each paper sized & pulled in by its overlap score) and an **overlap bar chart**,
- a **Recommended reading** list ranked by value-to-your-paper, each tagged with its role (closest prior work / baseline to compare / foundational to cite / method to borrow / background), with the orchestrator's curated top picks starred,
- a **"Methods to consider adding"** section: the in-depth analysis of techniques to fold into your method, each with what it is, why it helps, how to integrate, and source papers,
- a sortable **paper table** (overlap + reading value) and a click-through per-paper detail panel.

## Configuration

Models are set in `ideacheck/config.py` and can be overridden with environment
variables (no code change needed):

| Variable | Used by | Default |
| --- | --- | --- |
| `IDEACHECK_AGENT_MODEL` | orchestrator + query-planner + paper-analyst | `sonnet` |
| `IDEACHECK_OVERVIEW_MODEL` | overview-generator | `haiku` |
| `IDEACHECK_IMPROVE_MODEL` | method-advisor (in-depth improvement analysis) | `opus` |

Values accept SDK aliases (`sonnet`, `haiku`, `opus`, `fable`) or a full model id.

```bash
# e.g. run the agents on Opus for a deeper (pricier) pass
IDEACHECK_AGENT_MODEL=opus ideacheck check "my idea"
```

## License

MIT
