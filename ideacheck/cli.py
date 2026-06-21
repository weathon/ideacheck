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
@click.option("--open/--no-open", "open_report", default=True, show_default=True, help="Open the HTML report when done.")
def check(idea, idea_file, out_dir, open_report):
    """Run the novelty check on IDEA (or --idea-file)."""
    if idea_file:
        idea = Path(idea_file).read_text().strip()
    if not idea:
        raise click.UsageError("Provide an idea as an argument or via --idea-file.")

    run_dir = make_run_dir(idea, Path(out_dir))
    click.echo(click.style(f"run: {run_dir}", fg="cyan"))

    async def drive():
        async for ev in run_idea_check(idea, run_dir):
            t = ev["type"]
            if t == "delegate":
                click.echo(click.style(f"  → {ev['agent']}", fg="yellow") + f"  {ev['task']}")
            elif t == "tool":
                click.echo(click.style(f"    {ev['name']}", fg="green") + f"  {ev['args']}")
            elif t == "text":
                tag = "subagent" if ev["scope"] == "subagent" else "main"
                click.echo(click.style(f"  [{tag}] ", fg="magenta") + ev["text"].strip().replace("\n", "\n          "))
            elif t == "paper":
                click.echo(click.style(f"  analyzed [{ev['overlap_score']:>3}] ", fg="cyan") + f"{ev['relationship']}  {ev['title']}")
            elif t == "final":
                click.echo(click.style(f"  synthesis: novelty {ev['novelty_score']} · {ev['verdict']}", fg="cyan", bold=True))
            elif t == "result":
                click.echo(click.style(f"done: {ev['turns']} turns · ${ev['cost_usd']:.3f} · {ev['duration_ms']/1000:.1f}s", fg="cyan"))

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
