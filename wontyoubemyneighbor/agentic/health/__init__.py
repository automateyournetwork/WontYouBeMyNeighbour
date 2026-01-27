"""
Network Health Scoring Module for ASI Networks

Provides comprehensive health scoring for agents and networks based on:
- Protocol stability (neighbor uptime, adjacency state)
- Test pass rates (pyATS tests)
- Resource utilization (CPU, memory, interfaces)
- Configuration quality (best practices compliance)

Usage:
    from agentic.health import (
        HealthScorer, NetworkHealth, AgentHealth,
        get_network_health, get_agent_health
    )

    # Get network-wide health
    health = await get_network_health()
    print(f"Network health: {health.score}%")

    # Get agent-specific health
    agent_health = await get_agent_health("router-1")
    print(f"Agent health: {agent_health.score}%")
"""

from .health_scorer import (
    HealthScorer,
    NetworkHealth,
    AgentHealth,
    HealthComponent,
    HealthTrend,
    HealthSeverity,
    get_health_scorer,
    get_network_health,
    get_agent_health,
    get_health_history,
    get_health_recommendations,
)

__all__ = [
    "HealthScorer",
    "NetworkHealth",
    "AgentHealth",
    "HealthComponent",
    "HealthTrend",
    "HealthSeverity",
    "get_health_scorer",
    "get_network_health",
    "get_agent_health",
    "get_health_history",
    "get_health_recommendations",
]
