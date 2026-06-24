# ideacheck

`ideacheck` is a multi-agent research novelty checker. Give it a research idea,
it mines the [alphaXiv](https://www.alphaxiv.org) literature and produces:

0. **Scope split** — separates **background** from **proposal**, rates contribution size (0–100). Novelty is checked on the *proposal only*.
1. **Novelty** — 0–100 score + verdict (novel / incremental / substantially covered / likely duplicated).
2. **Differentiation** — how the proposal concretely differs from the closest prior work.
3. **Recommended reading** — papers ranked by value to *your* paper, not just overlap.
4. **Methods to add** — in-depth analysis of techniques from the literature to fold into your method.

Output: interactive D3 HTML report + markdown report + per-paper JSON.

> **Cost warning:** This tool is **token-hungry**. A single run analyzes 10–30+
> papers, each requiring full-text retrieval + LLM analysis. Expect:
>
> | | Tokens (approximate) | Cost (approximate) |
> |---|---|---|
> | Niche idea (~10 papers) | TBD | TBD |
> | Broad idea (~25 papers) | TBD | TBD |
> | Very broad (~40+ papers) | TBD | TBD |
>
> To reduce cost, use a harness that supports **cheap or local models** — see
> [Saving cost](#saving-cost) below. Generated overviews are cached under
> `~/.ideacheck/overview_cache/` and reused across runs.

## How it works (multi-agent)

```
orchestrator               split idea → background vs proposal, coordinate + synthesize
  ├─ query-planner         proposal → diverse searches → overlap candidates + read-worthy papers
  ├─ paper-analyst (×N)    one paper → overlap + reading value + similarities/differences (parallel)
  │     └─ overview-gen    makes + caches an overview when a paper has none
  ├─ method-advisor        in-depth: methods to fold in to improve the idea
  └─ (synthesis)           → report.json + render → report.md + report.html
```

The paper-analysts run **in parallel** (one per candidate paper). Each gathers
evidence in priority order — **full text → AI overview → abstract** — and if a
paper has no alphaXiv AI overview it generates and caches one. Every result is
written to disk as it completes, so a crash mid-run keeps all finished papers.

alphaXiv is queried through public endpoints — **no API key needed**.

## Setup

### Option A: Slash command in any AI coding harness (recommended)

The `/ideacheck` command works in any harness that supports custom commands /
skills and shell access. The skill file lives at `.claude/commands/ideacheck.md`
and is designed to be **harness-agnostic**: it documents the full workflow,
CLI tools, JSON schemas, and agent prompts so any harness can execute it.

```bash
git clone https://github.com/weathon/ideacheck.git
cd ideacheck
pip install alphaxiv-py    # the only runtime dependency
```

Then in your harness:

```
/ideacheck a diffusion model that edits 3D scenes from natural-language instructions
/ideacheck --before 2023-05-01 the core idea of the paper under test
```

**Harness-specific orchestration:**

| Harness | How the skill runs |
|---------|-------------------|
| **Claude Code** | Uses the **Workflow** tool for deterministic fan-out (`parallel()`, `pipeline()`), structured schemas, and a progress UI. Best experience. |
| **Cursor / Windsurf / other** | Uses **subagents** (or the harness's equivalent). If no subagent mechanism exists, steps run sequentially in the main context. |
| **Any harness** | The skill is self-contained: it documents every CLI command, every JSON schema, and every agent prompt. Even a harness with no subagent support can follow the instructions step by step. |

**Requirements:** Python ≥ 3.12, `alphaxiv-py` (`pip install alphaxiv-py`).
No API key needed for alphaXiv (public endpoints). Your harness handles LLM
authentication.

### Option B: Standalone CLI (Python package)

The repo also ships as a pip-installable Python package with its own CLI +
web GUI (uses the Claude Agent SDK directly, not a coding harness).

```bash
pip install git+https://github.com/weathon/ideacheck.git
```

```bash
ideacheck check "a diffusion model that edits 3D scenes from natural-language instructions"
ideacheck check --idea-file my_idea.txt --no-open
ideacheck check --before 2023-05-01 "the core idea of the paper under test"
```

Each run writes `./ideacheck_runs/<timestamp>-<slug>/` containing `report.json`,
`papers/<id>.json`, and `report.html` (opens automatically).

Web GUI:

```bash
ideacheck serve --port 8000
# open http://127.0.0.1:8000 , type your idea, hit "Check novelty"
```

## CLI tools

The skill's agents call these via shell. They also work standalone:

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

## The report

The HTML report (interactive, D3-powered) shows:

- **"What you're actually proposing"** — background-vs-proposal split + contribution-size bar
- **Novelty gauge** (0–100) and verdict
- **"How your idea differs from prior work"** — positioning section
- **Similarity network** — force-directed graph (idea at center, papers sized/pulled by overlap)
- **Overlap bar chart**
- **Recommended reading** — ranked by value-to-your-paper, tagged with role
- **"Methods to consider adding"** — in-depth per-method cards
- Sortable **paper table** + click-through detail panel

## Saving cost

This tool is token-intensive. Ways to reduce cost:

1. **Use a harness that supports local/cheap models.** The standalone CLI
   supports `--backend openai` with any OpenAI-compatible endpoint (e.g. a
   local [vLLM](https://docs.vllm.ai) server):
   ```bash
   pip install "ideacheck[openai] @ git+https://github.com/weathon/ideacheck.git"
   ideacheck check --backend openai \
     --base-url http://127.0.0.1:8000/v1 \
     --model Qwen/Qwen3.6-35B-A3B-FP8 \
     "my research idea"
   ```
2. **Use `--before` to narrow scope.** A time cutoff reduces the number of
   candidate papers the search returns.
3. **Overviews are cached.** After the first run, `~/.ideacheck/overview_cache/`
   stores generated overviews — repeat runs on similar ideas reuse them.

## Configuration (standalone CLI)

Models are set via environment variables:

| Variable | Used by | Default |
| --- | --- | --- |
| `IDEACHECK_AGENT_MODEL` | orchestrator + query-planner + paper-analyst | `sonnet` |
| `IDEACHECK_OVERVIEW_MODEL` | overview-generator | `haiku` |
| `IDEACHECK_IMPROVE_MODEL` | method-advisor | `opus` |

```bash
IDEACHECK_AGENT_MODEL=opus ideacheck check "my idea"
```

## Token usage

Measured on real runs (will be updated with more data):

| Idea scope | Papers analyzed | Input tokens | Output tokens | Total tokens | Wall time | Cost (API) |
|---|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| TBD | TBD | TBD | TBD | TBD | TBD | TBD |

## License

MIT
