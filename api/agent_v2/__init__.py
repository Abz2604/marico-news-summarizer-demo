"""
AgentV2 - True Agentic Architecture

A clean, tool-based agent system designed for reliability and efficiency.
"""

from .agent_v2 import AgentV2, AgentV2Request, AgentV2Response
from .types import PageType, ExtractedContent, ExtractedLink

__all__ = [
    "AgentV2",
    "AgentV2Request",
    "AgentV2Response",
    "PageType",
    "ExtractedContent",
    "ExtractedLink",
]

