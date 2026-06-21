"""ideacheck command-line interface.

    ideacheck check "<idea>"     run the multi-agent novelty check, write + open report
    ideacheck check --idea-file path.txt
    ideacheck serve --port 8000  launch the web GUI
"""

from __future__ import annotations

import asyncio
import webbrowser
from pathlib import Path

import click

from .pipeline import make_run_dir, run_idea_check
from .report import build_report_html


@click.group()
def cli():
    """Check whether your research idea has already been explored on alphaXiv."""


@cli.command()
@click.argument("idea", required=False)
@click.option("--idea-file", type=click.Path(exists=True, dir_okay=False), help="Read the idea text from a file.")
@click.option("--out-dir", default="ideacheck_runs", show_default=True, help="Where run directories are written.")
@click.option("--before", "before", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Only consider papers published before this date (YYYY-MM-DD). Lets you test the tool on an already-published paper as of just before it appeared.")
@click.option("--backend", type=click.Choice(["claude", "openai"]), default="claude", show_default=True, help="claude = Claude Agent SDK; openai = OpenAI Agents SDK against any OpenAI-compatible endpoint (e.g. local vLLM).")
@click.option("--base-url", default=None, help="openai backend: OpenAI-compatible base url (default IDEACHECK_OPENAI_BASE_URL or http://127.0.0.1:8000/v1).")
@click.option("--model", "model_name", default=None, help="openai backend: served model id (or IDEACHECK_OPENAI_MODEL).")
@click.option("--api-key", default=None, help="openai backend: api key (default IDEACHECK_OPENAI_API_KEY or 'EMPTY').")
@click.option("--open/--no-open", "open_report", default=True, show_default=True, help="Open the HTML report when done.")
def check(idea, idea_file, out_dir, before, backend, base_url, model_name, api_key, open_report):
    """Run the novelty check on IDEA (or --idea-file)."""
    if idea_file:
        idea = Path(idea_file).read_text().strip()
    if not idea:
        raise click.UsageError("Provide an idea as an argument or via --idea-file.")

    cutoff = before.date() if before else None
    run_dir = make_run_dir(idea, Path(out_dir))
    click.echo(click.style(f"run: {run_dir}", fg="cyan") + (f"  (papers before {cutoff})" if cutoff else "") + (f"  [openai]" if backend == "openai" else ""))

    if backend == "openai":
        from .config import OAI_API_KEY, OAI_BASE_URL, OAI_MODEL
        from .oai_pipeline import run_idea_check_oai
        mdl = model_name or OAI_MODEL
        if not mdl:
            raise click.UsageError("openai backend needs --model (or IDEACHECK_OPENAI_MODEL).")
        gen = run_idea_check_oai(idea, run_dir, cutoff, base_url or OAI_BASE_URL, mdl, api_key or OAI_API_KEY)
    else:
        gen = run_idea_check(idea, run_dir, cutoff)

    async def drive():
        async for ev in gen:
            t = ev["type"]
            if t == "delegate":
                click.echo(click.style(f"  → {ev['agent']}", fg="yellow") + f"  {ev['task']}")
            elif t == "tool":
                click.echo(click.style(f"    {ev['name']}", fg="green") + f"  {ev['args']}")
            elif t == "text":
                tag = "subagent" if ev["scope"] == "subagent" else "main"
                click.echo(click.style(f"  [{tag}] ", fg="magenta") + ev["text"].strip().replace("\n", "\n          "))
            elif t == "scope":
                click.echo(click.style("  proposal: ", fg="cyan", bold=True) + ev["proposal"])
                click.echo(click.style(f"  contribution weight {ev['contribution_weight']}/100 ", fg="cyan") + "(proposal vs the background it assumes)")
            elif t == "paper":
                click.echo(click.style(f"  analyzed overlap={ev['overlap_score']:>3} read={ev['reading_value']:>3} ", fg="cyan") + f"{ev['recommendation']}  {ev['title']}")
            elif t == "final":
                click.echo(click.style(f"  synthesis: novelty {ev['novelty_score']} · {ev['verdict']}", fg="cyan", bold=True))
            elif t == "improvements":
                click.echo(click.style(f"  method advice: {len(ev['recommendations'])} suggestions to improve the method", fg="cyan", bold=True))
            elif t == "result":
                if "backend" in ev and ev["backend"] == "openai":
                    tail = f"via {ev['model']} ({ev['base_url']})"
                else:
                    cost = ev["cost_usd"]
                    tail = f"${cost:.3f} billed to ANTHROPIC_API_KEY" if ev["billed"] else f"${cost:.3f} saved (equivalent API cost; $0 on your Claude subscription)"
                click.echo(click.style(f"done: {ev['turns']} turns · {ev['duration_ms']/1000:.1f}s · {tail}", fg="cyan", bold=True))

    asyncio.run(drive())

    report = build_report_html(run_dir)
    click.echo(click.style(f"report: {report}", fg="cyan", bold=True))
    if open_report:
        webbrowser.open(report.as_uri())


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True)
@click.option("--out-dir", default="ideacheck_runs", show_default=True, help="Where run directories are written.")
def serve(host, port, out_dir):
    """Launch the web GUI."""
    import uvicorn

    from .server import create_app

    app = create_app(Path(out_dir))
    click.echo(click.style(f"ideacheck GUI on http://{host}:{port}", fg="cyan", bold=True))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cli()
