---
name: ideacheck
description: Check whether a research idea has already been explored in alphaXiv literature, analyze related papers, and produce structured novelty reports with recommended reading and method suggestions.
---

# ideacheck

Use this skill when the user asks to check whether a research idea is novel, find prior art for an idea, compare a proposal against alphaXiv literature, or run ideacheck.

This skill is local to the `ideacheck` package. Run commands from this skill directory unless the user explicitly asks to use copied project-local scripts.

$ARGUMENTS

You are running the ideacheck novelty checker. Check whether the following research idea has already been explored in the alphaXiv literature, analyze how each existing paper relates to it, and produce a structured report.

## Idea

$ARGUMENTS

If the arguments contain `--before YYYY-MM-DD`, extract the date and pass it as `--before YYYY-MM-DD` to every `axv.py` command below. This restricts results to papers published before that date.

## CLI Tools

All lookups go through `python3 axv.py <subcommand>`. Each prints JSON to stdout.

| Command | What it does |
|---------|-------------|
| `python3 axv.py search "query" [--before YYYY-MM-DD]` | Full-text search for papers. Returns JSON list with id, title, abstract, authors, date, topics. |
| `python3 axv.py topics "query"` | Find topic tags the literature uses for a phrase. Use to discover vocabulary before searching. |
| `python3 axv.py paper <arxiv_id> [--before ...]` | Fetch metadata for one paper by arXiv id. Returns title, abstract, authors, date, topics, pdf_url, bibtex. |
| `python3 axv.py overview <arxiv_id> [--before ...]` | Get structured overview (summary, problem, solution, insights, results). Cached across runs. Exits non-zero if none exists. |
| `python3 axv.py fulltext <arxiv_id> [--before ...]` | Get full extracted text of a paper. Richest source. Exits non-zero if unavailable. |
| `python3 axv.py similar <arxiv_id> [--before ...]` | Find papers alphaXiv considers similar. Returns JSON list. |
| `python3 axv.py save-overview <json_file>` | Cache a generated overview (for papers without one). JSON must have: paper_id, title, summary, original_problem, solution, key_insights, results. |

## Orchestration

Use subagents for the query-planner, parallel paper-analysts, the overlap-filter, and the method-advisor. If subagents are unavailable, run the steps sequentially in the main context.

All subagents and workflow agents should use **model: "sonnet"** to keep costs down. Only the main-loop synthesis (the Synthesis step) runs in the parent context.

The workflow and subagent paths produce identical outputs - the same JSON files and the same rendered report.

## Guiding principle: SAME THING DONE, not SAME TOOL USED

This is the single most important rule of the whole skill, and it governs every step below.

A paper overlaps with the proposal **only when it does the same thing the proposal claims as novel** — the same specific mechanism, for the same purpose. It does **NOT** overlap just because it reaches for the same off-the-shelf tool, language, library, framework, or general technique. Tools are shared infrastructure; contributions are what you do with them.

- "Both use SQL" is NOT overlap. The proposal's contribution might be a *relational entity/event data model* that replaces a graph; a paper that stores a **graph** in SQLite and queries it with SQL uses the same tool (SQL) for the **opposite** data model (graph). It is a contrast/baseline, not prior art. SQL-as-storage ≠ relational-model-as-contribution.
- "Both use an LLM to make an image" is NOT overlap if one generates pixels directly and the other generates a *rendering script* that draws the image — same tool (LLM), different mechanism.
- "Both use GRPO / an agent / dense captions / a vector index" is NOT overlap — those are tools listed in the background.

Before calling anything an overlap, ask: **"Strip away the shared tools — is the actual thing being done the same?"** If the only thing in common is the instrument, it is NOT overlap. This is enforced explicitly by the Overlap Filter step, and no score is used anywhere — judgments are categorical and must be justified in prose.

## Workflow

### Step 0: Setup

Create a run directory and meta.json:
```bash
RUN_DIR="ideacheck_runs/$(date +%Y%m%d-%H%M%S)-$(echo '<first 6 words of idea>' | tr ' ' '-' | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]//g' | cut -c1-50)"
mkdir -p "$RUN_DIR/papers"
```
Write `$RUN_DIR/meta.json`:
```json
{"idea": "<full idea text>", "slug": "<run dir basename>", "cutoff": "<YYYY-MM-DD or null>"}
```

### Step 1: Scope Split

Before any searching, using ONLY the user's statement (no lookups), split the idea into two parts:
- **background**: the setup the user presents as already-existing, NOT claimed as their contribution
- **proposal**: the part that is actually the user's proposed contribution — the SPECIFIC DELTA on top of the background

The distinction is critical because everything downstream evaluates overlap against the PROPOSAL only. Getting this wrong makes the whole novelty judgment wrong.

**What goes in background** (these are GIVEN, shared with the field, NOT the user's contribution):
- The task / problem domain (e.g., "long video QA", "egocentric video understanding")
- Problems the user identifies as motivation (e.g., "train/test contamination in dataset X", "current methods are slow")
- Existing systems, methods, infrastructure the user builds upon or reuses (e.g., "uses the same indices and tools as System-X")
- General methodologies the user adopts but did not invent (e.g., "uses GRPO", "uses an agentic approach", "uses dense captions for retrieval")
- Standard components: retrieval indices, tool-use frameworks, RL training pipelines, VLM backbones

**What goes in proposal** (these are the user's CLAIMED NOVEL CONTRIBUTIONS):
- Specific architectural/design choices that differ from prior work (e.g., "removes edge constraints and lets agent free-hop" — NOT "uses an agent")
- Specific new data sources or data strategies (e.g., "gaming streams as proxy data" — NOT "trains on a dataset")
- Specific new training objectives or reward designs (e.g., "offline RL to optimize captions for QA utility" — NOT "uses RL")
- The proposal should be stated as the DELTA, not re-stating the background. "Trains agent with GRPO" is background if GRPO is an existing method; "trains the free-hopping traversal policy with GRPO on gaming data instead of hand-designed PPR" is proposal because it specifies WHAT is new.

**Common mistakes to avoid:**
- Putting the general approach in proposal (e.g., "uses GRPO to train agent" when GRPO is standard) — this inflates overlap with every paper that also uses GRPO
- Putting reused infrastructure in proposal (e.g., "agent has search/refine tools" when these are inherited from prior work) — this inflates overlap with every agentic system
- Conflating "addresses the same problem" with "proposes the same solution" — two papers can identify the same problem but propose completely different solutions
- Conflating "uses the same tool" with "makes the same contribution" — see the Guiding Principle above; a shared instrument is background, not a delta

Also write:
- **contribution_assessment**: markdown rationale on whether the proposed delta is big enough to stand on its own, and which part of it is the real novelty vs reused tooling. No numeric weight — describe it in words.

Write `$RUN_DIR/scope.json` with: `background`, `proposal`, `contribution_assessment`.

### Step 2: Search for Papers

Spawn a **query-planner** with this prompt:

```text
You are a literature-search strategist. Search alphaXiv for papers related to a research proposal.

PROPOSAL: <the proposal from scope>
BACKGROUND (context only): <the background from scope>
CUTOFF_FLAG: <"--before YYYY-MM-DD" if cutoff is set, else empty>

Generate several distinct search angles: the core method/technique, the problem it solves, the application domain, and alternative terminology. Use `python3 axv.py topics "..."` to discover vocabulary the literature actually uses, then run `python3 axv.py search "..." CUTOFF_FLAG` for each angle. Use `python3 axv.py similar <id> CUTOFF_FLAG` on strongly-matching papers to widen the net.

You MUST ALSO search at a higher level of ABSTRACTION — this is required, not optional. Strip the idea down to its underlying pattern or mechanism - what it fundamentally does, independent of domain/modality/data type - and search for that pattern in OTHER domains. Cross-domain analogs (same mechanism for images when the idea is about text, same trick in a different field) are exactly the candidates a literal search misses, so reach for them aggressively here.

(Note the asymmetry: SEARCH reaches abstractly to surface every possible analog; the later OVERLAP EVALUATION does NOT — it judges each candidate concretely. Cast the widest net now; the analysis stage decides what truly overlaps. A candidate surfaced by an abstract query is NOT automatically an overlap.)

Find two kinds:
1. OVERLAP candidates - papers that may already do part of the proposal
2. READ-WORTHY papers - key baseline, foundational method, method worth borrowing. Be HIGHLY SELECTIVE.

Only use papers from search tools - do NOT add papers from memory. Deduplicate by canonical arXiv id and drop clearly irrelevant ones.

Return the candidate list as one line per paper:
<canonical_id> | <title> | <why relevant>
```

### Step 3: Parallel Paper Analysis

For EVERY candidate paper from the planner, spawn a **paper-analyst** IN PARALLEL. Give each this prompt:

```text
Analyze ONE paper against the user's PROPOSED contribution.

PAPER_ID: <canonical arXiv id>
PAPER_TITLE: <title>
PROPOSAL: <the proposal from scope>
BACKGROUND: <the background from scope>
RUN_DIR: <run directory path>
CUTOFF_FLAG: <"--before YYYY-MM-DD" if set, else empty>

Judge overlap against the PROPOSAL only - treat background as shared/given.

CRITICAL — what counts as overlap vs. shared background:
The BACKGROUND describes the task, problem, general methodology, and reused infrastructure. A paper that shares these with the user's idea has shared BACKGROUND, not overlap. Only count overlap when the paper makes the SAME SPECIFIC NOVEL CHOICE as the proposal.

These do NOT count as overlap (they are shared background):
- Same task/domain (e.g., both do long video QA)
- Same general approach (e.g., both use an agentic framework, both use RL, both use GRPO)
- Same infrastructure (e.g., both use dense captions, both use retrieval indices, both use tool-calling agents)
- Same problem identified (e.g., both note that dataset X has contamination issues)
- Using the same off-the-shelf methods/algorithms that appear in the background
- **Same TOOL/language/library used for a DIFFERENT mechanism** (see the Guiding Principle). E.g. the paper stores a graph in SQLite and queries it with SQL, while the proposal's contribution is a relational entity/event model — same tool (SQL), opposite data model. This is a CONTRAST/baseline, not overlap.

These DO count as overlap (they are proposal-level):
- Same specific architectural delta (e.g., both specifically remove graph edge constraints in favor of free-form traversal)
- Same specific data strategy (e.g., both use gaming streams as proxy training data for ego-video)
- Same specific training innovation (e.g., both train captions via RL to maximize downstream QA accuracy, not just caption quality)

The test for every claimed similarity: **"Strip away the shared tools — is the actual thing being done the same?"** If the only thing in common is the instrument (SQL, LLM, GRPO, an agent, a vector index), it is NOT overlap. Look at HOW the tool is used: "LLM generates pixels" vs "LLM generates a rendering script that draws the image" are different contributions despite sharing the LLM.

In key_similarities, clearly label each point as (SAME CONTRIBUTION), (SAME TOOL ONLY), or (BACKGROUND SHARED). Only (SAME CONTRIBUTION) points are real overlap; (SAME TOOL ONLY) and (BACKGROUND SHARED) are NOT.

Gather the best available description, in this strict priority:
1. FULL TEXT: run `python3 axv.py fulltext PAPER_ID CUTOFF_FLAG`. If it returns text, use it.
2. OVERVIEW: only if no full text. Run `python3 axv.py overview PAPER_ID CUTOFF_FLAG`. If it returns data, use it. If it fails (no overview exists), generate one: get the abstract via `python3 axv.py paper PAPER_ID CUTOFF_FLAG`, write a structured overview as JSON with fields {paper_id, title, summary, original_problem, solution, key_insights, results}, save it to a temp file, then run `python3 axv.py save-overview <temp_file>`.
3. ABSTRACT: only if neither full text nor overview. Use the abstract from `python3 axv.py paper`.

Always also call `python3 axv.py paper PAPER_ID CUTOFF_FLAG` for metadata (title, authors, date).

Judge overlap CONCRETELY — do NOT reach for abstraction here. Abstraction is a SEARCH tool, not an evaluation tool. This paper was likely surfaced by an abstract/cross-domain query, but you must now judge it on the concrete mechanism, not on the high-level concept the two share.
- Compare the actual, concrete mechanism the paper proposes against the proposal's concrete mechanism — the real objects, operations, data, and procedure.
- Do NOT climb the ladder of abstraction to make two things look the same. "Both retrieve from memory", "both build a structured representation", "both use a simulator" are abstractions; if at the concrete level the mechanisms differ, it is NOT overlap, no matter how similar the one-sentence abstraction sounds.
- A cross-domain paper counts as overlap ONLY if, concretely, it does the SAME mechanism (the same operation on the same kind of object), not merely an analogous one. Same-domain is not required; concrete sameness is.
- When in doubt, default to NOT overlap and explain the concrete difference in key_differences.

Produce TWO independent judgments. Use NO numeric scores anywhere — every judgment is categorical and must be justified in prose.

A. OVERLAP:
- relationship: directly_overlapping | related_but_different | tangential
- key_similarities: specific points shared with the proposal, each labeled (SAME CONTRIBUTION), (SAME TOOL ONLY), or (BACKGROUND SHARED)
- key_differences: specific ways the proposal differs/goes beyond (this is a FOCUS - be precise)

B. READING VALUE (independent of overlap):
- recommendation: closest_prior_work | baseline_to_compare | foundational_to_cite | method_to_borrow | background_context | optional
- why_read: one sentence

Also: one_line (one sentence relation), evidence_source (full_text | overview | abstract).

Write the analysis as JSON to `$RUN_DIR/papers/<paper_id with / replaced by _>.json` with ALL fields:
paper_id, title, url (https://www.alphaxiv.org/abs/<paper_id>), authors, year, relationship, key_similarities, key_differences, one_line, recommendation, why_read, evidence_source

If any tool reports the paper is excluded by time cutoff, STOP - do not analyze it.
```

There is no cap on papers analyzed - the breadth of the literature decides the count.

### Step 4: Overlap Filter

The parallel paper-analysts each see only ONE paper and tend to over-claim overlap — most often by counting a SHARED TOOL as if it were a shared contribution. After all analysts finish, spawn a SINGLE **overlap-filter** subagent that re-reads every analysis with fresh, skeptical eyes and decides, per paper, whether the claimed overlap is real (same thing done) or spurious (same tool / same problem only). It writes its verdict back into each paper JSON.

Give the overlap-filter this prompt:

```text
You are an adversarial overlap auditor. Analysts judged each paper in isolation and tend to inflate overlap by mistaking a shared TOOL for a shared CONTRIBUTION. Re-judge every paper against the proposal and correct this.

PROPOSAL: <the proposal from scope>
BACKGROUND: <the background from scope>
RUN_DIR: <run directory path>
CUTOFF_FLAG: <"--before YYYY-MM-DD" if set, else empty>

Read every JSON in $RUN_DIR/papers/*.json. For EACH paper:

Judge CONCRETELY, never abstractly. The candidate was surfaced by an abstract/cross-domain search, but abstraction is a search tool, not an evaluation tool. Do NOT climb the ladder of abstraction to make two things look the same — "both retrieve from memory" / "both build a structured representation" / "both use a simulator" are abstractions that hide concrete differences. Compare the real objects, operations, and procedure.

Apply the SAME-THING-DONE test (this is the whole point of your job):
  Strip away every shared tool, language, library, framework, and general technique (SQL, an LLM, GRPO, an agent, a vector index, dense captions, RL, ...). After stripping the instruments, is the actual, CONCRETE MECHANISM the paper proposes the same as the proposal's claimed novel mechanism (the same operation on the same kind of object), used for the same purpose? A merely analogous mechanism in another domain is NOT the same — it is at most same_problem_only or same_tool_only.
  - If yes -> the overlap is real.
  - If the only thing shared is the instrument, or the same tool is used for a DIFFERENT or OPPOSITE mechanism (e.g. SQL used to store/query a GRAPH while the proposal's contribution is a relational entity/event model) -> the overlap is spurious; the paper is a CONTRAST or baseline, not prior art.
  - If only the task/problem is shared -> spurious (background).

When in doubt, RE-READ the paper to settle it: `python3 axv.py fulltext PAPER_ID CUTOFF_FLAG` (or overview/paper). Do not guess — verify how the paper actually uses the shared tool before deciding.

Classify each paper into exactly one overlap_kind:
- same_contribution  — does the same specific thing the proposal claims as novel (possibly in another domain = cross-domain prior art)
- same_tool_only     — shares only an instrument/technique, used for a different mechanism
- same_problem_only  — shares only the task/problem, different solution
- different          — neither

Then EDIT that paper's JSON in place, adding/overwriting these fields:
- overlap_kind: one of the four above
- same_contribution: true only if overlap_kind == same_contribution, else false
- filter_reason: 1-3 sentences naming the shared tool/problem, the actual mechanism in the paper, the proposal's mechanism, and why they are or are not the same thing
- relationship: KEEP or CORRECT the analyst's value so it is consistent with overlap_kind (only same_contribution papers may be directly_overlapping; tool/problem-only papers are at most related_but_different, usually tangential)
Preserve all other fields. Write valid JSON back to the same path.

Finally write $RUN_DIR/filter.json:
{
  "real_overlaps": ["<paper_id>", ...],          // same_contribution only
  "demoted": [{"paper_id": "...", "was": "<analyst relationship>", "overlap_kind": "...", "reason": "..."}],
  "notes": "<markdown: which apparent overlaps were really just shared tools/problems, and what genuine prior art remains>"
}
```

Only papers the filter marks `same_contribution: true` may be treated as real novelty threats by the Synthesis step. Everything else is a baseline/contrast/background.

### Step 5: Method Advice

After all paper analyses are done, spawn a **method-advisor**:

```text
You are a senior research methods advisor. Recommend concrete methods/techniques from the analyzed literature that the author could fold into their method to improve it.

PROPOSAL: <proposal>
BACKGROUND: <background>
RUN_DIR: <run directory>
CUTOFF_FLAG: <if set>

Read all analysis JSONs from $RUN_DIR/papers/*.json. Identify papers whose methods are most relevant. For those papers, get deeper content with `python3 axv.py fulltext <id> CUTOFF_FLAG` or `python3 axv.py overview <id> CUTOFF_FLAG`.

Produce recommendations. For EACH: a short title, in-depth explanation of the technique, why adding it would specifically improve THIS idea, concrete guidance on integration, and source_paper_ids.

Write `$RUN_DIR/improvements.json` with:
{
  "idea": "<full idea>",
  "analysis": "<markdown overview of improvement opportunities>",
  "recommendations": [
    {"title": "...", "technique": "...", "why_it_helps": "...", "how_to_integrate": "...", "source_paper_ids": ["..."]}
  ]
}
```

### Step 6: Synthesis

Read all analyses from `$RUN_DIR/papers/*.json` (now carrying the filter's `overlap_kind` / `same_contribution` fields), the filter verdict `$RUN_DIR/filter.json`, and the scope from `$RUN_DIR/scope.json`.

Use NO numeric score — the verdict is categorical and must be argued in prose. Write `$RUN_DIR/report.json` with:
```json
{
  "idea": "<full original idea>",
  "verdict": "<novel | incremental | substantially_covered | likely_duplicated>",
  "summary": "<markdown: novelty landscape + the genuine overlaps>",
  "differentiation": "<markdown: how the proposal differs from closest prior work>",
  "differentiation_suggestions": ["<concrete ways to differentiate further>"],
  "recommended_reading": [{"paper_id": "...", "why": "..."}],
  "analyzed_paper_ids": ["..."]
}
```

Base the verdict ONLY on papers the filter marked `same_contribution: true`. Papers that share the same task, same general methodology, same infrastructure, or the same TOOL used for a different mechanism are NOT evidence against novelty — the filter has already demoted them; do not resurrect them as threats.

When writing the summary, for each genuine overlap explicitly state which SPECIFIC PROPOSAL CLAIM it does the same thing on, and confirm it survives the same-thing-done test (not "both use GRPO" or "both do long video QA" or "both used SQL"). Apply the Guiding Principle one last time: how a tool is USED is what matters — "LLM generates an image" vs "LLM generates a rendering script that draws the image" are different contributions despite the shared LLM.

Judge concretely, not abstractly (the SEARCH reached for abstractions to find candidates; the EVALUATION must not). A cross-domain paper reduces novelty only when, at the concrete level, it does the SAME mechanism (same operation on the same kind of object) — not when it is merely an abstract/analogical cousin. Porting a genuinely identical concrete mechanism to a new domain is low novelty; sharing only a high-level concept ("both retrieve from memory", "both use a simulator") is not an overlap at all.

### Step 7: Render

```bash
python3 render.py "$RUN_DIR"
```

This generates `$RUN_DIR/report.md` and `$RUN_DIR/report.html`.

Tell the user where to find the reports.
