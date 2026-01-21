"""
Network Optimization Module

Provides:
- Traffic pattern analysis
- OSPF cost optimization recommendations
- BGP policy optimization suggestions
- VXLAN VNI allocation optimization
- Path optimization analysis
"""

from .analyzer import (
    TrafficAnalyzer,
    TrafficPattern,
    TrafficMetric,
    AnalysisResult
)
from .recommender import (
    OptimizationRecommender,
    Recommendation,
    RecommendationType,
    RecommendationPriority
)

__all__ = [
    'TrafficAnalyzer',
    'TrafficPattern',
    'TrafficMetric',
    'AnalysisResult',
    'OptimizationRecommender',
    'Recommendation',
    'RecommendationType',
    'RecommendationPriority'
]
