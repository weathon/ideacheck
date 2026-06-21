"""In-process MCP tools wrapping alphaXiv + run/overview persistence.

Two servers are built per run by build_servers():
  - "axv":   alphaXiv search / paper-detail tools + the generated-overview cache.
  - "store": run-scoped persistence (per-paper analysis, final report, read-back).

alphaXiv calls that fail (e.g. a paper has no AI overview -> 404, or no full
text) return is_error text so the analyst can follow its content cascade
(full text > overview > abstract) instead of crashing the whole run. This is
the SDK-recommended pattern, not a silent fallback: the failure is surfaced to
the agent as data and the agent decides what to do.
"""

from __future__ import annotations

import json
from pathlib import Path

from alphaxiv.exceptions import AlphaXivError
from claude_agent_sdk import create_sdk_mcp_server, tool

OVERVIEW_CACHE_DIR = Path.home() / ".ideacheck" / "overview_cache"


def build_servers(axv, run_dir: Path):
    run_dir = Path(run_dir)
    papers_dir = run_dir / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    OVERVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ axv
    @tool(
        "search_papers",
        "Search alphaXiv for papers matching a free-text query. Returns a JSON "
        "list of candidate papers. Use the `id` field (canonical arXiv id) for "
        "every other paper tool.",
        {"query": str},
    )
    async def search_papers(args):
        try:
            results = await axv.search.papers_rich(args["query"])
        except AlphaXivError as exc:
            return {"content": [{"type": "text", "text": f"alphaXiv search failed: {exc}"}], "is_error": True}
        out = [
            {
                "id": r.canonical_id or r.universal_paper_id,
                "canonical_id": r.canonical_id,
                "universal_paper_id": r.universal_paper_id,
                "title": r.title,
                "abstract": r.abstract,
                "authors": [a.display_name for a in r.authors],
                "publication_date": r.publication_date,
                "topics": r.topics,
                "github_url": r.github_url,
                "github_stars": r.github_stars,
            }
            for r in results
        ]
        return {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}]}

    @tool(
        "closest_topics",
        "Find alphaXiv topic tags closest to a phrase. Use this to discover the "
        "vocabulary the literature actually uses before searching.",
        {"query": str},
    )
    async def closest_topics(args):
        try:
            topics = await axv.search.closest_topics(args["query"])
        except AlphaXivError as exc:
            return {"content": [{"type": "text", "text": f"alphaXiv topic lookup failed: {exc}"}], "is_error": True}
        return {"content": [{"type": "text", "text": json.dumps(topics, ensure_ascii=False)}]}

    @tool(
        "get_paper",
        "Fetch full metadata for ONE paper by arXiv id (bare like 1706.03762 or "
        "versioned like 1706.03762v5). Returns title, abstract, authors, date, "
        "topics, pdf url, source url, bibtex. The abstract is the floor source "
        "for analysis. If this fails the paper cannot be analyzed.",
        {"paper_id": str},
    )
    async def get_paper(args):
        try:
            p = await axv.papers.get(args["paper_id"])
        except AlphaXivError as exc:
            return {"content": [{"type": "text", "text": f"Could not fetch paper {args['paper_id']}: {exc}"}], "is_error": True}
        data = {
            "canonical_id": p.resolved.canonical_id,
            "universal_paper_id": p.resolved.versionless_id,
            "title": p.version.title,
            "abstract": p.version.abstract,
            "authors": [a.full_name for a in p.authors],
            "publication_date": p.version.publication_date.isoformat() if p.version.publication_date else None,
            "topics": p.group.topics,
            "pdf_url": p.pdf_url,
            "source_url": p.group.source_url,
            "bibtex": p.group.citation,
        }
        return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}]}

    @tool(
        "get_overview",
        "Get a structured overview of a paper (summary, original problem, "
        "solution, key insights, results). Returns a cached overview if present, "
        "else the alphaXiv AI overview. If neither exists this returns is_error: "
        "delegate to the overview-generator agent to generate one (it caches it), "
        "then call this tool again to read the cached generated overview.",
        {"paper_id": str},
    )
    async def get_overview(args):
        pid = args["paper_id"]
        cache_file = OVERVIEW_CACHE_DIR / f"{pid.replace('/', '_')}.json"
        if cache_file.exists():
            return {"content": [{"type": "text", "text": cache_file.read_text()}]}
        try:
            o = await axv.papers.overview(pid)
        except AlphaXivError as exc:
            return {
                "content": [{"type": "text", "text": f"No alphaXiv overview for {pid} ({exc}). Use the overview-generator agent to generate one, then call get_overview again."}],
                "is_error": True,
            }
        s = o.summary
        data = {
            "paper_id": pid,
            "source": "alphaxiv",
            "title": o.title,
            "summary": s.summary if s else "",
            "original_problem": s.original_problem if s else [],
            "solution": s.solution if s else [],
            "key_insights": s.key_insights if s else [],
            "results": s.results if s else [],
        }
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}]}

    @tool(
        "get_full_text",
        "Fetch the full extracted text of a paper (all pages) by arXiv id. This "
        "is the richest source; prefer it when available. Returns is_error if no "
        "full text exists for the paper.",
        {"paper_id": str},
    )
    async def get_full_text(args):
        try:
            ft = await axv.papers.full_text(args["paper_id"])
        except AlphaXivError as exc:
            return {"content": [{"type": "text", "text": f"No full text for {args['paper_id']} ({exc})."}], "is_error": True}
        if not ft.text.strip():
            return {"content": [{"type": "text", "text": f"No full text for {args['paper_id']}."}], "is_error": True}
        return {"content": [{"type": "text", "text": ft.text}]}

    @tool(
        "find_similar",
        "Find papers alphaXiv considers similar to a given paper (by arXiv id). "
        "Returns a JSON list of related papers (id, title, abstract, authors).",
        {"paper_id": str},
    )
    async def find_similar(args):
        try:
            cards = await axv.papers.similar(args["paper_id"])
        except AlphaXivError as exc:
            return {"content": [{"type": "text", "text": f"Similar-papers lookup failed for {args['paper_id']}: {exc}"}], "is_error": True}
        out = [
            {
                "id": c.canonical_id or c.paper_id,
                "canonical_id": c.canonical_id,
                "title": c.title,
                "abstract": c.abstract,
                "authors": c.authors,
                "publication_date": c.publication_date.isoformat() if c.publication_date else None,
                "topics": c.topics,
            }
            for c in cards
        ]
        return {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}]}

    @tool(
        "save_generated_overview",
        "Cache a generated structured overview for a paper so it is reused across "
        "runs. Called by the overview-generator agent after it writes an overview "
        "from the paper's full text or abstract.",
        {
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "Canonical arXiv id of the paper"},
                "title": {"type": "string"},
                "summary": {"type": "string", "description": "A few-sentence overview of the paper"},
                "original_problem": {"type": "array", "items": {"type": "string"}},
                "solution": {"type": "array", "items": {"type": "string"}},
                "key_insights": {"type": "array", "items": {"type": "string"}},
                "results": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["paper_id", "title", "summary", "original_problem", "solution", "key_insights", "results"],
        },
    )
    async def save_generated_overview(args):
        pid = args["paper_id"]
        cache_file = OVERVIEW_CACHE_DIR / f"{pid.replace('/', '_')}.json"
        data = {
            "paper_id": pid,
            "source": "generated",
            "title": args["title"],
            "summary": args["summary"],
            "original_problem": args["original_problem"],
            "solution": args["solution"],
            "key_insights": args["key_insights"],
            "results": args["results"],
        }
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return {"content": [{"type": "text", "text": f"Cached generated overview for {pid}."}]}

    axv_server = create_sdk_mcp_server(
        name="axv",
        version="0.1.0",
        tools=[search_papers, closest_topics, get_paper, get_overview, get_full_text, find_similar, save_generated_overview],
    )

    # ---------------------------------------------------------------- store
    @tool(
        "save_paper_analysis",
        "Persist the structured overlap analysis of ONE paper vs the user's idea. "
        "Call exactly once per paper. overlap_score is 0-100 where 100 means the "
        "paper essentially already does the user's idea.",
        {
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "Canonical arXiv id"},
                "title": {"type": "string"},
                "url": {"type": "string", "description": "https://www.alphaxiv.org/abs/<paper_id>"},
                "authors": {"type": "array", "items": {"type": "string"}},
                "year": {"type": "string", "description": "Publication year or date"},
                "overlap_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "relationship": {
                    "type": "string",
                    "enum": ["directly_overlapping", "related_but_different", "tangential"],
                },
                "key_similarities": {"type": "array", "items": {"type": "string"}},
                "key_differences": {"type": "array", "items": {"type": "string"}},
                "one_line": {"type": "string", "description": "One-sentence relation to the idea"},
                "evidence_source": {
                    "type": "string",
                    "enum": ["full_text", "overview", "abstract"],
                    "description": "Which source the judgment was based on",
                },
            },
            "required": ["paper_id", "title", "url", "authors", "year", "overlap_score", "relationship", "key_similarities", "key_differences", "one_line", "evidence_source"],
        },
    )
    async def save_paper_analysis(args):
        pid = args["paper_id"]
        (papers_dir / f"{pid.replace('/', '_')}.json").write_text(json.dumps(args, ensure_ascii=False, indent=2))
        return {"content": [{"type": "text", "text": f"Saved analysis for {pid} (overlap {args['overlap_score']})."}]}

    @tool(
        "read_all_analyses",
        "Read back every per-paper analysis saved so far this run. Use this "
        "before writing the final report so the synthesis covers all papers.",
        {},
    )
    async def read_all_analyses(args):
        items = [json.loads(f.read_text()) for f in sorted(papers_dir.glob("*.json"))]
        return {"content": [{"type": "text", "text": json.dumps(items, ensure_ascii=False, indent=2)}]}

    @tool(
        "save_final_report",
        "Persist the overall novelty verdict for the idea. Call exactly once at "
        "the end. novelty_score is 0-100 where 100 means highly novel / not "
        "covered by existing work and 0 means already fully done.",
        {
            "type": "object",
            "properties": {
                "idea": {"type": "string"},
                "novelty_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "verdict": {
                    "type": "string",
                    "enum": ["novel", "incremental", "substantially_covered", "likely_duplicated"],
                },
                "summary": {"type": "string", "description": "Markdown synthesis of the findings"},
                "differentiation_suggestions": {"type": "array", "items": {"type": "string"}},
                "analyzed_paper_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["idea", "novelty_score", "verdict", "summary", "differentiation_suggestions", "analyzed_paper_ids"],
        },
    )
    async def save_final_report(args):
        (run_dir / "report.json").write_text(json.dumps(args, ensure_ascii=False, indent=2))
        return {"content": [{"type": "text", "text": f"Saved final report (novelty {args['novelty_score']}, verdict {args['verdict']})."}]}

    store_server = create_sdk_mcp_server(
        name="store",
        version="0.1.0",
        tools=[save_paper_analysis, read_all_analyses, save_final_report],
    )

    return axv_server, store_server
