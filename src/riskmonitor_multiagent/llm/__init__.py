"""LLM 客户端与适配层."""

from __future__ import annotations

from riskmonitor_multiagent.llm.llm_client import LLMError
from riskmonitor_multiagent.llm.llm_client import LlmClient
from riskmonitor_multiagent.llm.llm_client import extract_first_text

__all__ = ["LlmClient", "LLMError", "extract_first_text"]

