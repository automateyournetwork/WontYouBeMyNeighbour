"""
Metrics Collection Module

Provides:
- Metric definitions
- Time-series storage
- Aggregation functions
- Alerting thresholds
"""

from .collectors import (
    Metric,
    MetricType,
    MetricUnit,
    MetricCategory,
    MetricConfig,
    MetricCollector,
    get_metric_collector
)
from .storage import (
    DataPoint,
    TimeSeries,
    TimeSeriesStore,
    get_timeseries_store
)
from .aggregator import (
    AggregationType,
    AggregationWindow,
    MetricAggregator,
    get_metric_aggregator
)

__all__ = [
    # Collectors
    "Metric",
    "MetricType",
    "MetricUnit",
    "MetricCategory",
    "MetricConfig",
    "MetricCollector",
    "get_metric_collector",
    # Storage
    "DataPoint",
    "TimeSeries",
    "TimeSeriesStore",
    "get_timeseries_store",
    # Aggregator
    "AggregationType",
    "AggregationWindow",
    "MetricAggregator",
    "get_metric_aggregator"
]
