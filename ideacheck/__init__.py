"""ideacheck - multi-agent prior-art / idea-novelty checker over alphaXiv.

A research idea goes in; a Claude Agent SDK orchestrator (Opus) plans alphaXiv
searches, fans out per-paper analyst subagents (Sonnet) that score overlap, then
synthesizes an overall novelty verdict and writes a D3-powered HTML report.
"""

__version__ = "0.1.0"
