"""OpenAI Agents SDK backend - mirrors the Claude agent topology.

Same four-focus pipeline (scope split -> plan -> per-paper analyse -> method
advice -> synthesise) and the same prompts as the Claude backend, but built with
the OpenAI Agents SDK so it runs on ANY OpenAI-compatible endpoint (set a custom
base_url + model, e.g. a local vLLM server). Sub-agents are exposed to the
orchestrator with `.as_tool()`, which is the OpenAI-SDK equivalent of Claude's
native subagent delegation. alphaXiv access + persistence are `@function_tool`s,
closures over the alphaXiv client / run dir / cutoff (mirroring build_servers).
"""

from __future__ import annotations

import json
from pathlib import Path

from agents import Agent, function_tool
from alphaxiv.exceptions import AlphaXivError
from alphaxiv.types import parse_datetime

from . import agents as cl
from .tools import OVERVIEW_CACHE_DIR


def build_orchestrator(axv, run_dir: Path, cutoff, model):
    run_dir = Path(run_dir)
    papers_dir = run_dir / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    OVERVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cutoff_yymm = (cutoff.year - 2000) * 100 + cutoff.month if cutoff else None

    def blocked(pid):
        return cutoff_yymm is not None and pid[:4].isdigit() and int(pid[:4]) >= cutoff_yymm

    # --------------------------------------------------------------- alphaXiv
    @function_tool(strict_mode=False)
    async def search_papers(query: str) -> str:
        """Search alphaXiv for papers matching a free-text query. Returns a JSON list of candidate papers; use each paper's `id` (canonical arXiv id) for the other tools."""
        try:
            results = await axv.search.papers_rich(query)
        except AlphaXivError as exc:
            return f"alphaXiv search failed: {exc}"
        out = []
        for r in results:
            if cutoff is not None:
                pd = parse_datetime(r.publication_date)
                if pd is None or pd.date() >= cutoff:
                    continue
            out.append({
                "id": r.canonical_id or r.universal_paper_id,
                "title": r.title,
                "abstract": r.abstract,
                "authors": [a.display_name for a in r.authors],
                "publication_date": r.publication_date,
                "topics": r.topics,
            })
        return json.dumps(out, ensure_ascii=False)

    @function_tool(strict_mode=False)
    async def closest_topics(query: str) -> str:
        """Find alphaXiv topic tags closest to a phrase, to discover the vocabulary the literature uses."""
        try:
            return json.dumps(await axv.search.closest_topics(query), ensure_ascii=False)
        except AlphaXivError as exc:
            return f"topic lookup failed: {exc}"

    @function_tool(strict_mode=False)
    async def get_paper(paper_id: str) -> str:
        """Fetch metadata (title, abstract, authors, date, topics, pdf, bibtex) for ONE paper by arXiv id. The abstract is the floor source for analysis."""
        if blocked(paper_id):
            return f"{paper_id} is excluded by the time cutoff. Skip this paper - do not analyze it."
        try:
            p = await axv.papers.get(paper_id)
        except AlphaXivError as exc:
            return f"Could not fetch paper {paper_id}: {exc}"
        return json.dumps({
            "canonical_id": p.resolved.canonical_id,
            "title": p.version.title,
            "abstract": p.version.abstract,
            "authors": [a.full_name for a in p.authors],
            "publication_date": p.version.publication_date.isoformat() if p.version.publication_date else None,
            "topics": p.group.topics,
            "pdf_url": p.pdf_url,
            "bibtex": p.group.citation,
        }, ensure_ascii=False)

    @function_tool(strict_mode=False)
    async def get_overview(paper_id: str) -> str:
        """Get a structured overview (summary, problem, solution, insights, results) for a paper. Returns a cached or alphaXiv overview; if none exists, delegate to the overview_generator tool then call this again."""
        if blocked(paper_id):
            return f"{paper_id} is excluded by the time cutoff. Skip this paper."
        cache_file = OVERVIEW_CACHE_DIR / f"{paper_id.replace('/', '_')}.json"
        if cache_file.exists():
            return cache_file.read_text()
        try:
            o = await axv.papers.overview(paper_id)
        except AlphaXivError as exc:
            return f"No alphaXiv overview for {paper_id} ({exc}). Use the overview_generator tool to make one, then call get_overview again."
        s = o.summary
        data = {
            "paper_id": paper_id, "source": "alphaxiv", "title": o.title,
            "summary": s.summary if s else "",
            "original_problem": s.original_problem if s else [],
            "solution": s.solution if s else [],
            "key_insights": s.key_insights if s else [],
            "results": s.results if s else [],
        }
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return json.dumps(data, ensure_ascii=False)

    @function_tool(strict_mode=False)
    async def get_full_text(paper_id: str) -> str:
        """Fetch the full extracted text of a paper (all pages) by arXiv id. The richest source; prefer it when available."""
        if blocked(paper_id):
            return f"{paper_id} is excluded by the time cutoff. Skip this paper."
        try:
            ft = await axv.papers.full_text(paper_id)
        except AlphaXivError as exc:
            return f"No full text for {paper_id} ({exc})."
        return ft.text if ft.text.strip() else f"No full text for {paper_id}."

    @function_tool(strict_mode=False)
    async def find_similar(paper_id: str) -> str:
        """Find papers alphaXiv considers similar to a given paper (by arXiv id). Returns a JSON list."""
        if blocked(paper_id):
            return f"{paper_id} is after the time cutoff, so it cannot be used as a seed. Skip it."
        try:
            cards = await axv.papers.similar(paper_id)
        except AlphaXivError as exc:
            return f"Similar-papers lookup failed for {paper_id}: {exc}"
        out = []
        for c in cards:
            if cutoff is not None and (c.publication_date is None or c.publication_date.date() >= cutoff):
                continue
            out.append({"id": c.canonical_id or c.paper_id, "title": c.title, "abstract": c.abstract, "authors": c.authors})
        return json.dumps(out, ensure_ascii=False)

    @function_tool(strict_mode=False)
    async def save_generated_overview(paper_id: str, title: str, summary: str, original_problem: list[str], solution: list[str], key_insights: list[str], results: list[str]) -> str:
        """Cache a generated structured overview for a paper that has no alphaXiv overview."""
        cache_file = OVERVIEW_CACHE_DIR / f"{paper_id.replace('/', '_')}.json"
        cache_file.write_text(json.dumps({
            "paper_id": paper_id, "source": "generated", "title": title, "summary": summary,
            "original_problem": original_problem, "solution": solution, "key_insights": key_insights, "results": results,
        }, ensure_ascii=False, indent=2))
        return f"Cached generated overview for {paper_id}."

    # ----------------------------------------------------------------- store
    @function_tool(strict_mode=False)
    async def save_scope(background: str, proposal: str, contribution_weight: int, contribution_assessment: str) -> str:
        """Persist the split of the idea into the assumed background vs the user's actual proposal, plus how big the proposal is (0-100) relative to the background. Call this FIRST, from the user's own statement (no lookup)."""
        (run_dir / "scope.json").write_text(json.dumps({
            "background": background, "proposal": proposal,
            "contribution_weight": contribution_weight, "contribution_assessment": contribution_assessment,
        }, ensure_ascii=False, indent=2))
        return f"Saved scope (contribution_weight {contribution_weight}). Proposal: {proposal[:160]}"

    @function_tool(strict_mode=False)
    async def save_paper_analysis(paper_id: str, title: str, url: str, authors: list[str], year: str, overlap_score: int, relationship: str, key_similarities: list[str], key_differences: list[str], one_line: str, reading_value: int, recommendation: str, why_read: str, evidence_source: str) -> str:
        """Persist the analysis of ONE paper vs the proposal. relationship in {directly_overlapping, related_but_different, tangential}; recommendation in {closest_prior_work, baseline_to_compare, foundational_to_cite, method_to_borrow, background_context, optional}; evidence_source in {full_text, overview, abstract}. overlap_score and reading_value are 0-100."""
        data = {
            "paper_id": paper_id, "title": title, "url": url, "authors": authors, "year": year,
            "overlap_score": overlap_score, "relationship": relationship,
            "key_similarities": key_similarities, "key_differences": key_differences, "one_line": one_line,
            "reading_value": reading_value, "recommendation": recommendation, "why_read": why_read,
            "evidence_source": evidence_source,
        }
        (papers_dir / f"{paper_id.replace('/', '_')}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return f"Saved analysis for {paper_id} (overlap {overlap_score})."

    @function_tool(strict_mode=False)
    async def read_all_analyses() -> str:
        """Read back every per-paper analysis saved so far this run, as a JSON array."""
        items = [json.loads(f.read_text()) for f in sorted(papers_dir.glob("*.json"))]
        return json.dumps(items, ensure_ascii=False)

    @function_tool(strict_mode=False)
    async def save_improvements(idea: str, analysis: str, recommendations: list[dict]) -> str:
        """Persist the in-depth method-improvement analysis. Each recommendation is an object with: title, technique, why_it_helps, how_to_integrate, source_paper_ids (list of arXiv ids)."""
        (run_dir / "improvements.json").write_text(json.dumps({
            "idea": idea, "analysis": analysis, "recommendations": recommendations,
        }, ensure_ascii=False, indent=2))
        return f"Saved {len(recommendations)} method-improvement recommendations."

    @function_tool(strict_mode=False)
    async def save_final_report(idea: str, novelty_score: int, verdict: str, summary: str, differentiation: str, differentiation_suggestions: list[str], recommended_reading: list[dict], analyzed_paper_ids: list[str]) -> str:
        """Persist the final verdict. verdict in {novel, incremental, substantially_covered, likely_duplicated}; novelty_score 0-100 (of the PROPOSAL). recommended_reading is a list of objects with paper_id + why. Call exactly once at the end."""
        (run_dir / "report.json").write_text(json.dumps({
            "idea": idea, "novelty_score": novelty_score, "verdict": verdict, "summary": summary,
            "differentiation": differentiation, "differentiation_suggestions": differentiation_suggestions,
            "recommended_reading": recommended_reading, "analyzed_paper_ids": analyzed_paper_ids,
        }, ensure_ascii=False, indent=2))
        return f"Saved final report (novelty {novelty_score}, verdict {verdict})."

    # ----------------------------------------------------------------- agents
    overview_generator = Agent(
        name="overview-generator", instructions=cl.OVERVIEW_GENERATOR.prompt,
        tools=[get_paper, get_full_text, save_generated_overview], model=model,
    )
    planner = Agent(
        name="query-planner", instructions=cl.PLANNER.prompt,
        tools=[search_papers, closest_topics, find_similar, get_paper], model=model,
    )
    analyst = Agent(
        name="paper-analyst", instructions=cl.ANALYST.prompt,
        tools=[
            get_paper, get_overview, get_full_text, find_similar, save_paper_analysis,
            overview_generator.as_tool("overview_generator", "Generate and cache a structured overview for a paper that has no alphaXiv overview. Pass the paper's canonical id and title.", max_turns=20),
        ],
        model=model,
    )
    method_advisor = Agent(
        name="method-advisor", instructions=cl.METHOD_ADVISOR.prompt,
        tools=[read_all_analyses, get_paper, get_overview, get_full_text, save_improvements], model=model,
    )
    orchestrator = Agent(
        name="orchestrator", instructions=cl.ORCHESTRATOR_PROMPT,
        tools=[
            planner.as_tool("query_planner", "Turn the proposal into diverse alphaXiv searches and return candidate papers. Pass the proposal and background.", max_turns=40),
            analyst.as_tool("paper_analyst", "Analyze ONE paper against the proposal. Pass the paper's canonical id, its title, the proposal, and the background.", max_turns=25),
            method_advisor.as_tool("method_advisor", "In-depth analysis of methods to fold into the idea to improve it. Pass the proposal and background.", max_turns=40),
            save_scope, read_all_analyses, save_final_report,
        ],
        model=model,
    )
    return orchestrator
