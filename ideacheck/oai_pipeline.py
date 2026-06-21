"""Run the idea-check on the OpenAI Agents SDK backend (any OpenAI-compatible
endpoint, e.g. a local vLLM server).

Mirrors pipeline.run_idea_check: an async generator yielding the same progress
event dicts (start / scope / delegate / tool / paper / final / improvements /
result), so the CLI, GUI, and report all work unchanged. The orchestrator and
sub-agents run on the configured model via OpenAIChatCompletionsModel +
AsyncOpenAI(base_url=...). Per-paper results land on disk as the save_* tools
fire, so the report is built from disk regardless of the live stream.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from agents import (
    AsyncOpenAI,
    ItemHelpers,
    OpenAIChatCompletionsModel,
    Runner,
    set_tracing_disabled,
)
from alphaxiv import AlphaXivClient

from .oai_agents import build_orchestrator

SAVE_EVENT = {
    "save_scope": "scope",
    "save_paper_analysis": "paper",
    "save_final_report": "final",
    "save_improvements": "improvements",
}
AGENT_TOOLS = {"query_planner", "paper_analyst", "method_advisor", "overview_generator"}


async def run_idea_check_oai(idea: str, run_dir: Path, cutoff, base_url: str, model_name: str, api_key: str):
    run_dir = Path(run_dir)
    (run_dir / "papers").mkdir(parents=True, exist_ok=True)
    (run_dir / "meta.json").write_text(json.dumps(
        {"idea": idea, "slug": run_dir.name, "cutoff": cutoff.isoformat() if cutoff else None,
         "backend": "openai", "model": model_name},
        ensure_ascii=False, indent=2))

    set_tracing_disabled(True)
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    model = OpenAIChatCompletionsModel(model=model_name, openai_client=client)

    prompt = (
        "Check whether the following research idea has already been explored in the "
        "alphaXiv literature, analyze how each existing paper relates to it, and write "
        "the final report with save_final_report.\n\nIdea:\n\n" + idea
    )
    if cutoff is not None:
        prompt += (
            f"\n\nTIME CUTOFF: only papers published before {cutoff.isoformat()} exist for this "
            f"check; the tools enforce it. Treat the literature as of {cutoff.isoformat()}."
        )

    async with AlphaXivClient() as axv:
        orchestrator = build_orchestrator(axv, run_dir, cutoff, model)
        yield {"type": "start", "idea": idea, "run_dir": str(run_dir), "cutoff": cutoff.isoformat() if cutoff else None}

        start = time.time()
        turns = 0
        result = Runner.run_streamed(orchestrator, input=prompt, max_turns=400)
        async for ev in result.stream_events():
            if ev.type != "run_item_stream_event":
                continue
            item = ev.item
            kind = getattr(item, "type", "")
            if kind == "tool_call_item":
                turns += 1
                raw = item.raw_item
                name = getattr(raw, "name", "") or ""
                raw_args = getattr(raw, "arguments", "") or "{}"
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}
                if name in SAVE_EVENT:
                    yield {"type": SAVE_EVENT[name], **args}
                elif name in AGENT_TOOLS:
                    yield {"type": "delegate", "agent": name, "task": json.dumps(args, ensure_ascii=False)[:200]}
                else:
                    yield {"type": "tool", "scope": "sub", "name": name, "args": {k: args[k] for k in ("query", "paper_id") if k in args}}
            elif kind == "message_output_item":
                text = ItemHelpers.text_message_output(item)
                if text and text.strip():
                    yield {"type": "text", "scope": "main", "text": text}

        yield {
            "type": "result", "subtype": "success", "turns": turns,
            "duration_ms": (time.time() - start) * 1000,
            "backend": "openai", "model": model_name, "base_url": base_url,
        }
