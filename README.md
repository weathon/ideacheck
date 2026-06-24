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

### Option A: Claude Code Skill (recommended)

Clone this repo and `cd` into it (or add it as a submodule). The `/ideacheck`
slash command is available automatically — Claude Code picks up
`.claude/commands/ideacheck.md` from the working directory.

```bash
git clone https://github.com/weathon/ideacheck.git
cd ideacheck
pip install alphaxiv-py    # the only runtime dependency
```

Then inside Claude Code:

```
/ideacheck a diffusion model that edits 3D scenes from natural-language instructions
/ideacheck --before 2023-05-01 the core idea of the paper under test
```

The skill orchestrates everything via subagents:
1. **Scope split** — separates background from proposal (no lookups)
2. **Query-planner subagent** — diverse searches + cross-domain analog discovery
3. **Paper-analyst subagents** — one per paper, spawned IN PARALLEL, each calls `axv.py` CLI tools
4. **Method-advisor subagent** (Opus) — in-depth method improvement analysis
5. **Synthesis** — final novelty verdict + report JSON
6. **Render** — calls `python render.py` to produce `report.md` + `report.html`

The CLI tools can also be used standalone:

```bash
python axv.py search "query" [--before YYYY-MM-DD]   # search papers
python axv.py topics "query"                          # discover vocabulary
python axv.py paper <arxiv_id>                        # paper metadata
python axv.py overview <arxiv_id>                     # structured overview (cached)
python axv.py fulltext <arxiv_id>                     # full extracted text
python axv.py similar <arxiv_id>                      # similar papers
python axv.py save-overview <json_file>               # cache a generated overview
python render.py <run_dir>                            # JSON → report.md + report.html
```

**Requirements:** Python ≥ 3.12, `alphaxiv-py` (`pip install alphaxiv-py`).
No API key needed for alphaXiv (public endpoints). Claude Code handles
authentication automatically.

> Cost: a run uses Sonnet (subagents) + one Opus pass (method-advisor).
> A broad idea with dozens of papers costs a few dollars; a niche idea is
> cheaper. Generated overviews are cached under `~/.ideacheck/overview_cache/`
> and reused across runs.

### Option B: Standalone CLI (Python package)

The repo also ships as a pip-installable Python package with its own CLI +
web GUI (uses the Claude Agent SDK directly, not Claude Code).

```bash
pip install git+https://github.com/weathon/ideacheck.git
```

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

## Backends: Claude or any OpenAI-compatible model

There are two backends with the same four-focus pipeline, prompts, and report:

- `--backend claude` (default) — the Claude Agent SDK (native subagent delegation).
- `--backend openai` — the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/),
  which can point at **any OpenAI-compatible endpoint** via a custom `base_url` +
  `model`. That means you can run the whole multi-agent pipeline on a **self-hosted
  model** (e.g. a local [vLLM](https://docs.vllm.ai) server) or any provider. The
  same orchestrator + sub-agents (exposed with `.as_tool()`) and the same alphaXiv
  function-tools are used; one model serves every agent.

```bash
pip install "ideacheck[openai] @ git+https://github.com/weathon/ideacheck.git"

# run the whole pipeline on a local vLLM server
ideacheck check --backend openai \
  --base-url http://127.0.0.1:8000/v1 \
  --model Qwen/Qwen3.6-35B-A3B-FP8 \
  "my research idea"
```

Or via env (`IDEACHECK_OPENAI_BASE_URL`, `IDEACHECK_OPENAI_MODEL`,
`IDEACHECK_OPENAI_API_KEY`; key defaults to `EMPTY`, which vLLM ignores). The
model must support tool/function calling.

## License

MIT
