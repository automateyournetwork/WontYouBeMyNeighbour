"""
Intelligent Network Suggestions Module

Provides AI-powered analysis and suggestions for network improvements,
optimization, and best practices.
"""

from .network_advisor import (
    NetworkAdvisor,
    Suggestion,
    SuggestionCategory,
    SuggestionPriority,
    get_network_advisor,
    analyze_network,
    get_suggestions,
)

__all__ = [
    "NetworkAdvisor",
    "Suggestion",
    "SuggestionCategory",
    "SuggestionPriority",
    "get_network_advisor",
    "analyze_network",
    "get_suggestions",
]
