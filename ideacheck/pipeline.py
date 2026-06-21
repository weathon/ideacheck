"""Run the multi-agent idea-check and yield progress events.

run_idea_check() is an async generator: it opens an alphaXiv client, builds the
in-process MCP servers, runs the Opus orchestrator query() (which delegates to
the Sonnet subagents), and yields a stream of progress-event dicts as the SDK
messages arrive. The CLI prints them; the FastAPI GUI relays them over SSE.

Per-paper results land on disk via the save_* tools as they complete, so a
crash mid-run still leaves every finished paper in <run_dir>/papers/.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from alphaxiv import AlphaXivClient
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from .agents import AGENTS, ALLOWED_TOOLS, ORCHESTRATOR_PROMPT
from .config import AGENT_MODEL
from .tools import build_servers


def make_run_dir(idea: str, base_dir: Path) -> Path:
    slug = "-".join(idea.lower().split()[:6])
    slug = "".join(c for c in slug if c.isalnum() or c == "-").strip("-") or "idea"
    run_dir = Path(base_dir) / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


async def run_idea_check(idea: str, run_dir: Path):
    run_dir = Path(run_dir)
    (run_dir / "papers").mkdir(parents=True, exist_ok=True)
    (run_dir / "meta.json").write_text(json.dumps({"idea": idea, "slug": run_dir.name}, ensure_ascii=False, indent=2))

    async with AlphaXivClient() as axv:
        axv_server, store_server = build_servers(axv, run_dir)
        options = ClaudeAgentOptions(
            model=AGENT_MODEL,
            system_prompt=ORCHESTRATOR_PROMPT,
            permission_mode="bypassPermissions",
            mcp_servers={"axv": axv_server, "store": store_server},
            allowed_tools=ALLOWED_TOOLS,
            agents=AGENTS,
            setting_sources=[],  # self-contained: ignore the host project's CLAUDE.md / settings
        )
        prompt = (
            "Check whether the following research idea has already been explored in the "
            "alphaXiv literature, analyze how each existing paper relates to it, and write "
            "the final report with save_final_report.\n\nIdea:\n\n" + idea
        )

        yield {"type": "start", "idea": idea, "run_dir": str(run_dir)}

        async for message in query(prompt=prompt, options=options):
            inside = bool(getattr(message, "parent_tool_use_id", None))
            scope = "subagent" if inside else "main"
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        if block.text.strip():
                            yield {"type": "text", "scope": scope, "text": block.text}
                    elif isinstance(block, ToolUseBlock):
                        if block.name in ("Agent", "Task"):
                            # subagent_type is an optional field on the Agent tool
                            # input; never let a missing display field kill the run
                            yield {
                                "type": "delegate",
                                "agent": block.input.get("subagent_type") or "subagent",
                                "task": (block.input.get("description") or block.input.get("prompt", ""))[:200],
                            }
                        elif block.name == "mcp__store__save_paper_analysis":
                            # the analysis IS the tool input -> stream it so the UI
                            # can drop the paper's node into the graph in real time
                            yield {"type": "paper", **block.input}
                        elif block.name == "mcp__store__save_final_report":
                            yield {"type": "final", **block.input}
                        elif block.name == "mcp__store__save_improvements":
                            yield {"type": "improvements", **block.input}
                        else:
                            keys = ("query", "paper_id")
                            args = {k: block.input[k] for k in keys if k in block.input}
                            yield {"type": "tool", "scope": scope, "name": block.name, "args": args}
            elif isinstance(message, ResultMessage):
                yield {
                    "type": "result",
                    "subtype": message.subtype,
                    "cost_usd": message.total_cost_usd,
                    "turns": message.num_turns,
                    "duration_ms": message.duration_ms,
                }
