"""
Chaos Engineering / Failure Injection Module

Provides controlled failure injection for testing network resilience:
- Link failures
- Agent/node failures
- Packet loss simulation
- Latency injection
- Configuration errors

Used for:
- Chaos engineering testing
- Network resilience validation
- Self-healing verification
- Training and education
"""

from .injector import (
    FailureInjector,
    FailureType,
    FailureConfig,
    FailureResult,
    ScheduledFailure
)
from .scenarios import (
    ChaosScenario,
    ScenarioRunner,
    PredefinedScenarios
)

__all__ = [
    'FailureInjector',
    'FailureType',
    'FailureConfig',
    'FailureResult',
    'ScheduledFailure',
    'ChaosScenario',
    'ScenarioRunner',
    'PredefinedScenarios'
]
