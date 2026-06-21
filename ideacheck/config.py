"""Model configuration.

Set models either by editing the defaults here or via environment variables:

    IDEACHECK_AGENT_MODEL     orchestrator + query-planner + paper-analyst   (default: sonnet)
    IDEACHECK_OVERVIEW_MODEL  overview-generator                            (default: haiku)
    IDEACHECK_IMPROVE_MODEL   method-advisor (in-depth improvement analysis) (default: opus)

Values accept Claude Agent SDK model aliases ('sonnet', 'haiku', 'opus', 'fable')
or a full model id.
"""

import os

AGENT_MODEL = os.environ.get("IDEACHECK_AGENT_MODEL") or "sonnet"
OVERVIEW_MODEL = os.environ.get("IDEACHECK_OVERVIEW_MODEL") or "haiku"
IMPROVE_MODEL = os.environ.get("IDEACHECK_IMPROVE_MODEL") or "opus"

# OpenAI Agents SDK backend (--backend openai): any OpenAI-compatible endpoint,
# e.g. a local vLLM server. One model runs every agent.
#   IDEACHECK_OPENAI_BASE_URL  default http://127.0.0.1:8000/v1
#   IDEACHECK_OPENAI_MODEL     required (the served model id)
#   IDEACHECK_OPENAI_API_KEY   default "EMPTY" (vLLM ignores it)
OAI_BASE_URL = os.environ.get("IDEACHECK_OPENAI_BASE_URL") or "http://127.0.0.1:8000/v1"
OAI_MODEL = os.environ.get("IDEACHECK_OPENAI_MODEL") or ""
OAI_API_KEY = os.environ.get("IDEACHECK_OPENAI_API_KEY") or "EMPTY"
