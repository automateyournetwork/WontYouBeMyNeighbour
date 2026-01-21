"""
What-If Analysis Module

Provides:
- Link/Node failure simulation
- Configuration change dry-run
- Impact analysis and prediction
- Recovery time estimation
- Rollback capability
"""

from .simulator import (
    WhatIfSimulator,
    Scenario,
    ScenarioType,
    SimulationResult,
    ImpactLevel
)
from .analyzer import (
    ImpactAnalyzer,
    ImpactReport,
    AffectedPath,
    RecoveryEstimate
)

__all__ = [
    'WhatIfSimulator',
    'Scenario',
    'ScenarioType',
    'SimulationResult',
    'ImpactLevel',
    'ImpactAnalyzer',
    'ImpactReport',
    'AffectedPath',
    'RecoveryEstimate'
]
