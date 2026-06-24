$ARGUMENTS

You are running the ideacheck novelty checker. Check whether the following research idea has already been explored in the alphaXiv literature, analyze how each existing paper relates to it, and produce a structured report.

## Idea

$ARGUMENTS

If the arguments contain `--before YYYY-MM-DD`, extract the date and pass it as `--before YYYY-MM-DD` to every `axv.py` command below. This restricts results to papers published before that date.

## CLI Tools

All lookups go through `python axv.py <subcommand>`. Each prints JSON to stdout.

| Command | What it does |
|---------|-------------|
| `python axv.py search "query" [--before YYYY-MM-DD]` | Full-text search for papers. Returns JSON list with id, title, abstract, authors, date, topics. |
| `python axv.py topics "query"` | Find topic tags the literature uses for a phrase. Use to discover vocabulary before searching. |
| `python axv.py paper <arxiv_id> [--before ...]` | Fetch metadata for one paper by arXiv id. Returns title, abstract, authors, date, topics, pdf_url, bibtex. |
| `python axv.py overview <arxiv_id> [--before ...]` | Get structured overview (summary, problem, solution, insights, results). Cached across runs. Exits non-zero if none exists. |
| `python axv.py fulltext <arxiv_id> [--before ...]` | Get full extracted text of a paper. Richest source. Exits non-zero if unavailable. |
| `python axv.py similar <arxiv_id> [--before ...]` | Find papers alphaXiv considers similar. Returns JSON list. |
| `python axv.py save-overview <json_file>` | Cache a generated overview (for papers without one). JSON must have: paper_id, title, summary, original_problem, solution, key_insights, results. |

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
- **proposal**: the part that is actually the user's proposed contribution

Also judge:
- **contribution_weight** (0-100): how substantial the proposal is relative to the background (100 = the proposal is the bulk / a major new mechanism; low = a small tweak on a large existing foundation)
- **contribution_assessment**: markdown rationale on whether the proposed delta is big enough to stand on its own

Write `$RUN_DIR/scope.json` with these four fields. Everything downstream evaluates the PROPOSAL only - if you evaluated the whole idea, the background would trivially overlap everything.

### Step 2: Search for Papers

Spawn a **query-planner subagent** with this prompt (fill in the proposal and background):

```
You are a literature-search strategist. Search alphaXiv for papers related to a research proposal.

PROPOSAL: <the proposal from scope>
BACKGROUND (context only): <the background from scope>
CUTOFF_FLAG: <"--before YYYY-MM-DD" if cutoff is set, else empty>

Generate several distinct search angles: the core method/technique, the problem it solves, the application domain, and alternative terminology. Use `python axv.py topics "..."` to discover vocabulary the literature actually uses, then run `python axv.py search "..." CUTOFF_FLAG` for each angle. Use `python axv.py similar <id> CUTOFF_FLAG` on strongly-matching papers to widen the net.

ALSO search at a higher level of ABSTRACTION. Strip the idea down to its underlying pattern or mechanism - what it fundamentally does, independent of domain/modality/data type - and search for that pattern in OTHER domains. Cross-domain analogs (same mechanism for images when the idea is about text, same trick in a different field) are highly relevant prior art.

Find two kinds:
1. OVERLAP candidates - papers that may already do part of the proposal
2. READ-WORTHY papers - key baseline, foundational method, method worth borrowing. Be HIGHLY SELECTIVE.

Only use papers from search tools - do NOT add papers from memory. Deduplicate by canonical arXiv id and drop clearly irrelevant ones.

Return the candidate list as one line per paper:
<canonical_id> | <title> | <why relevant>
```

### Step 3: Parallel Paper Analysis

For EVERY candidate paper from the planner, spawn a **paper-analyst subagent** IN PARALLEL (put all Agent calls in a single turn). Give each this prompt (fill in the fields):

```
Analyze ONE paper against the user's PROPOSED contribution.

PAPER_ID: <canonical arXiv id>
PAPER_TITLE: <title>
PROPOSAL: <the proposal from scope>
BACKGROUND: <the background from scope>
RUN_DIR: <run directory path>
CUTOFF_FLAG: <"--before YYYY-MM-DD" if set, else empty>

Judge overlap against the PROPOSAL only - treat background as shared/given.

Gather the best available description, in this strict priority:
1. FULL TEXT: run `python axv.py fulltext PAPER_ID CUTOFF_FLAG`. If it returns text, use it.
2. OVERVIEW: only if no full text. Run `python axv.py overview PAPER_ID CUTOFF_FLAG`. If it returns data, use it. If it fails (no overview exists), generate one: get the abstract via `python axv.py paper PAPER_ID CUTOFF_FLAG`, write a structured overview as JSON with fields {paper_id, title, summary, original_problem, solution, key_insights, results}, save it to a temp file, then run `python axv.py save-overview <temp_file>`.
3. ABSTRACT: only if neither full text nor overview. Use the abstract from `python axv.py paper`.

Always also call `python axv.py paper PAPER_ID CUTOFF_FLAG` for metadata (title, authors, date).

Judge overlap at BOTH levels:
- SPECIFIC: same method/domain/task as the proposal
- ABSTRACT/ANALOGICAL: same underlying idea in a DIFFERENT domain/modality/task. This counts as real prior art.

Produce TWO independent judgments:

A. OVERLAP:
- overlap_score: 0-100 (100 = essentially already does the proposal)
- relationship: directly_overlapping | related_but_different | tangential
- key_similarities: specific points shared with the proposal
- key_differences: specific ways the proposal differs/goes beyond (this is a FOCUS - be precise)

B. READING VALUE (independent of overlap):
- reading_value: 0-100 (100 = essential reading)
- recommendation: closest_prior_work | baseline_to_compare | foundational_to_cite | method_to_borrow | background_context | optional
- why_read: one sentence

Also: one_line (one sentence relation), evidence_source (full_text | overview | abstract).

Write the analysis as JSON to `$RUN_DIR/papers/<paper_id with / replaced by _>.json` with ALL fields:
paper_id, title, url (https://www.alphaxiv.org/abs/<paper_id>), authors, year, overlap_score, relationship, key_similarities, key_differences, one_line, reading_value, recommendation, why_read, evidence_source

If any tool reports the paper is excluded by time cutoff, STOP - do not analyze it.
```

There is no cap on papers analyzed - the breadth of the literature decides the count.

### Step 4: Method Advice

After all paper analyses are done, spawn a **method-advisor subagent** (use model=opus for this one):

```
You are a senior research methods advisor. Recommend concrete methods/techniques from the analyzed literature that the author could fold into their method to improve it.

PROPOSAL: <proposal>
BACKGROUND: <background>
RUN_DIR: <run directory>
CUTOFF_FLAG: <if set>

Read all analysis JSONs from $RUN_DIR/papers/*.json. Identify papers whose methods are most relevant. For those papers, get deeper content with `python axv.py fulltext <id> CUTOFF_FLAG` or `python axv.py overview <id> CUTOFF_FLAG`.

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

### Step 5: Synthesis

Read all analyses from `$RUN_DIR/papers/*.json` and the scope from `$RUN_DIR/scope.json`.

Write `$RUN_DIR/report.json` with:
```json
{
  "idea": "<full original idea>",
  "novelty_score": <0-100, 100=highly novel, 0=already fully done>,
  "verdict": "<novel | incremental | substantially_covered | likely_duplicated>",
  "summary": "<markdown: novelty landscape + most threatening overlaps>",
  "differentiation": "<markdown: how the proposal differs from closest prior work>",
  "differentiation_suggestions": ["<concrete ways to differentiate further>"],
  "recommended_reading": [{"paper_id": "...", "why": "..."}],
  "analyzed_paper_ids": ["..."]
}
```

Base novelty_score ONLY on overlap with the proposal. Many high-overlap / directly_overlapping papers = low novelty. Only tangential or related-but-different = high novelty. Count ABSTRACT / cross-domain analogs: a proposal that ports an existing mechanism to a new domain is NOT highly novel.

Novelty (proposal vs literature) and contribution_weight (proposal vs background) are two separate axes - the report covers both.

### Step 6: Render

```bash
python render.py "$RUN_DIR"
```

This generates `$RUN_DIR/report.md` (markdown) and `$RUN_DIR/report.html` (interactive D3 visualization with similarity network graph, overlap bars, recommended reading, methods to add, and a sortable paper table).

Tell the user where to find the reports.
