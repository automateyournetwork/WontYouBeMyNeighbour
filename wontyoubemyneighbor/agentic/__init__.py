"""
Agentic Network Router - Natural Language Interface Layer

This module transforms wontyoubemyneighbor into a fully agentic network router
that understands human intent via natural language while maintaining native
protocol participation.

Architecture:
- llm/: Multi-provider LLM interfaces (OpenAI, Claude, Gemini)
- reasoning/: Intent parsing and decision-making engine
- actions/: Autonomous action execution layer
- multi_agent/: RubberBand-to-RubberBand coordination and consensus
- knowledge/: Network state management and analytics
"""

__version__ = "1.0.0"
__author__ = "wontyoubemyneighbor + Claude"

from .llm.interface import LLMInterface, LLMProvider
from .reasoning.intent_parser import IntentParser
from .reasoning.decision_engine import DecisionEngine
from .actions.executor import ActionExecutor
from .knowledge.state_manager import NetworkStateManager

__all__ = [
    "LLMInterface",
    "LLMProvider",
    "IntentParser",
    "DecisionEngine",
    "ActionExecutor",
    "NetworkStateManager",
]
