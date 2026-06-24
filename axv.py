#!/usr/bin/env python3
"""CLI for alphaXiv paper lookups. All commands print JSON to stdout.

Usage:
  python ideacheck/axv.py search "diffusion 3d scene editing" [--before 2023-05-01]
  python ideacheck/axv.py topics "scene editing"
  python ideacheck/axv.py paper 2310.04837 [--before 2023-05-01]
  python ideacheck/axv.py overview 2310.04837 [--before 2023-05-01]
  python ideacheck/axv.py fulltext 2310.04837 [--before 2023-05-01]
  python ideacheck/axv.py similar 2310.04837 [--before 2023-05-01]
  python ideacheck/axv.py save-overview overview.json
"""

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from alphaxiv import AlphaXivClient
from alphaxiv.exceptions import AlphaXivError
from alphaxiv.types import parse_datetime

OVERVIEW_CACHE = Path.home() / ".ideacheck" / "overview_cache"


def cutoff_yymm_blocked(paper_id, before):
    if before is None:
        return False
    cutoff_yymm = (before.year - 2000) * 100 + before.month
    if paper_id[:4].isdigit() and int(paper_id[:4]) >= cutoff_yymm:
        print(json.dumps({"error": f"{paper_id} excluded by cutoff (arXiv id at/after {before})"}), file=sys.stderr)
        sys.exit(1)


async def cmd_search(args):
    cutoff = date.fromisoformat(args.before) if args.before else None
    async with AlphaXivClient() as axv:
        results = await axv.search.papers_rich(args.query)
    out = []
    for r in results:
        if cutoff:
            pd = parse_datetime(r.publication_date)
            if pd is None or pd.date() >= cutoff:
                continue
        out.append({
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
        })
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()


async def cmd_topics(args):
    async with AlphaXivClient() as axv:
        topics = await axv.search.closest_topics(args.query)
    json.dump(topics, sys.stdout, ensure_ascii=False)
    print()


async def cmd_paper(args):
    cutoff = date.fromisoformat(args.before) if args.before else None
    cutoff_yymm_blocked(args.paper_id, cutoff)
    async with AlphaXivClient() as axv:
        p = await axv.papers.get(args.paper_id)
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
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    print()


async def cmd_overview(args):
    cutoff = date.fromisoformat(args.before) if args.before else None
    pid = args.paper_id
    cutoff_yymm_blocked(pid, cutoff)
    OVERVIEW_CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = OVERVIEW_CACHE / f"{pid.replace('/', '_')}.json"
    if cache_file.exists():
        print(cache_file.read_text())
        return
    async with AlphaXivClient() as axv:
        o = await axv.papers.overview(pid)
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
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    print()


async def cmd_fulltext(args):
    cutoff = date.fromisoformat(args.before) if args.before else None
    cutoff_yymm_blocked(args.paper_id, cutoff)
    async with AlphaXivClient() as axv:
        ft = await axv.papers.full_text(args.paper_id)
    if not ft.text.strip():
        print(json.dumps({"error": f"No full text for {args.paper_id}"}), file=sys.stderr)
        sys.exit(1)
    print(ft.text)


async def cmd_similar(args):
    cutoff = date.fromisoformat(args.before) if args.before else None
    cutoff_yymm_blocked(args.paper_id, cutoff)
    async with AlphaXivClient() as axv:
        cards = await axv.papers.similar(args.paper_id)
    out = []
    for c in cards:
        if cutoff and (c.publication_date is None or c.publication_date.date() >= cutoff):
            continue
        out.append({
            "id": c.canonical_id or c.paper_id,
            "canonical_id": c.canonical_id,
            "title": c.title,
            "abstract": c.abstract,
            "authors": c.authors,
            "publication_date": c.publication_date.isoformat() if c.publication_date else None,
            "topics": c.topics,
        })
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()


def cmd_save_overview(args):
    OVERVIEW_CACHE.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path(args.json_file).read_text())
    pid = data["paper_id"]
    cache_file = OVERVIEW_CACHE / f"{pid.replace('/', '_')}.json"
    data["source"] = "generated"
    cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"Cached generated overview for {pid}")


parser = argparse.ArgumentParser(description="alphaXiv CLI")
sub = parser.add_subparsers(dest="command", required=True)

p = sub.add_parser("search", help="Search papers by query")
p.add_argument("query")
p.add_argument("--before", default=None, help="YYYY-MM-DD cutoff")

p = sub.add_parser("topics", help="Find closest topic tags")
p.add_argument("query")

p = sub.add_parser("paper", help="Get paper metadata by arXiv id")
p.add_argument("paper_id")
p.add_argument("--before", default=None)

p = sub.add_parser("overview", help="Get structured overview (cached or alphaXiv)")
p.add_argument("paper_id")
p.add_argument("--before", default=None)

p = sub.add_parser("fulltext", help="Get full extracted text")
p.add_argument("paper_id")
p.add_argument("--before", default=None)

p = sub.add_parser("similar", help="Find similar papers")
p.add_argument("paper_id")
p.add_argument("--before", default=None)

p = sub.add_parser("save-overview", help="Cache a generated overview from JSON file")
p.add_argument("json_file")

args = parser.parse_args()

dispatch = {
    "search": cmd_search,
    "topics": cmd_topics,
    "paper": cmd_paper,
    "overview": cmd_overview,
    "fulltext": cmd_fulltext,
    "similar": cmd_similar,
}

if args.command == "save-overview":
    cmd_save_overview(args)
else:
    asyncio.run(dispatch[args.command](args))
