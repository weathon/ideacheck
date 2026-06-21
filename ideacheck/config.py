"""Model configuration.

Set models either by editing the defaults here or via environment variables:

    IDEACHECK_AGENT_MODEL     orchestrator + query-planner + paper-analyst   (default: sonnet)
    IDEACHECK_OVERVIEW_MODEL  overview-generator                            (default: haiku)

Values accept Claude Agent SDK model aliases ('sonnet', 'haiku', 'opus', 'fable')
or a full model id.
"""

import os

AGENT_MODEL = os.environ.get("IDEACHECK_AGENT_MODEL") or "sonnet"
OVERVIEW_MODEL = os.environ.get("IDEACHECK_OVERVIEW_MODEL") or "haiku"
