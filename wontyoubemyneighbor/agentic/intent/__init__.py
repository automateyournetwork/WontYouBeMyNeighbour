"""
Intent-Based Configuration Module

Provides:
- Natural language intent parsing
- Intent to configuration translation
- Multi-agent intent execution
- Intent validation and verification
"""

from .parser import (
    IntentParser,
    Intent,
    IntentType,
    IntentParameter
)
from .executor import (
    IntentExecutor,
    ExecutionPlan,
    ExecutionStep,
    ExecutionResult
)

__all__ = [
    'IntentParser',
    'Intent',
    'IntentType',
    'IntentParameter',
    'IntentExecutor',
    'ExecutionPlan',
    'ExecutionStep',
    'ExecutionResult'
]
