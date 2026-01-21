"""
Metrics Collection

Provides:
- Metric types (counter, gauge, histogram)
- Metric registration
- Label support
- Aggregation
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum
import statistics


class MetricType(Enum):
    """Types of metrics"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"
    TIMER = "timer"


@dataclass
class Metric:
    """Represents a metric"""

    name: str
    type: MetricType
    value: float = 0.0
    labels: Dict[str, str] = field(default_factory=dict)
    description: str = ""
    unit: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # For histograms/summaries
    values: List[float] = field(default_factory=list)
    buckets: Dict[float, int] = field(default_factory=dict)
    count: int = 0
    total: float = 0.0

    @property
    def key(self) -> str:
        """Generate unique key with labels"""
        if not self.labels:
            return self.name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(self.labels.items()))
        return f"{self.name}{{{label_str}}}"

    def increment(self, value: float = 1.0) -> None:
        """Increment counter"""
        if self.type == MetricType.COUNTER:
            self.value += value
            self.updated_at = datetime.now()

    def set(self, value: float) -> None:
        """Set gauge value"""
        if self.type == MetricType.GAUGE:
            self.value = value
            self.updated_at = datetime.now()

    def observe(self, value: float) -> None:
        """Observe a value (histogram/summary)"""
        if self.type in (MetricType.HISTOGRAM, MetricType.SUMMARY, MetricType.TIMER):
            self.values.append(value)
            self.count += 1
            self.total += value
            self.value = value
            self.updated_at = datetime.now()

            # Update buckets for histogram
            if self.type == MetricType.HISTOGRAM:
                for bucket in self.buckets:
                    if value <= bucket:
                        self.buckets[bucket] += 1

            # Trim old values for summary
            if self.type == MetricType.SUMMARY and len(self.values) > 1000:
                self.values = self.values[-500:]

    @property
    def avg(self) -> float:
        """Get average value"""
        if self.count == 0:
            return 0.0
        return self.total / self.count

    @property
    def min_value(self) -> float:
        """Get minimum value"""
        return min(self.values) if self.values else 0.0

    @property
    def max_value(self) -> float:
        """Get maximum value"""
        return max(self.values) if self.values else 0.0

    def percentile(self, p: float) -> float:
        """Get percentile"""
        if not self.values:
            return 0.0
        sorted_values = sorted(self.values)
        idx = int(len(sorted_values) * p / 100)
        return sorted_values[min(idx, len(sorted_values) - 1)]

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        result = {
            "name": self.name,
            "type": self.type.value,
            "value": self.value,
            "labels": self.labels,
            "description": self.description,
            "unit": self.unit,
            "updated_at": self.updated_at.isoformat()
        }

        if self.type in (MetricType.HISTOGRAM, MetricType.SUMMARY, MetricType.TIMER):
            result.update({
                "count": self.count,
                "total": self.total,
                "avg": self.avg,
                "min": self.min_value,
                "max": self.max_value,
                "p50": self.percentile(50),
                "p90": self.percentile(90),
                "p99": self.percentile(99)
            })

        if self.type == MetricType.HISTOGRAM and self.buckets:
            result["buckets"] = self.buckets

        return result


class MetricCollector:
    """Collects and manages metrics"""

    # Default histogram buckets
    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]

    def __init__(self):
        self.metrics: Dict[str, Metric] = {}
        self._registrations: Dict[str, Dict[str, Any]] = {}
        self._collectors: List[Callable[[], List[Metric]]] = []

    def register(
        self,
        name: str,
        metric_type: MetricType,
        description: str = "",
        unit: str = "",
        labels: Optional[List[str]] = None,
        buckets: Optional[List[float]] = None
    ) -> None:
        """Register a metric"""
        self._registrations[name] = {
            "type": metric_type,
            "description": description,
            "unit": unit,
            "labels": labels or [],
            "buckets": buckets or self.DEFAULT_BUCKETS
        }

    def counter(
        self,
        name: str,
        description: str = "",
        labels: Optional[Dict[str, str]] = None
    ) -> Metric:
        """Get or create a counter"""
        return self._get_or_create(name, MetricType.COUNTER, description, labels)

    def gauge(
        self,
        name: str,
        description: str = "",
        labels: Optional[Dict[str, str]] = None
    ) -> Metric:
        """Get or create a gauge"""
        return self._get_or_create(name, MetricType.GAUGE, description, labels)

    def histogram(
        self,
        name: str,
        description: str = "",
        labels: Optional[Dict[str, str]] = None,
        buckets: Optional[List[float]] = None
    ) -> Metric:
        """Get or create a histogram"""
        metric = self._get_or_create(name, MetricType.HISTOGRAM, description, labels)
        if not metric.buckets:
            metric.buckets = {b: 0 for b in (buckets or self.DEFAULT_BUCKETS)}
        return metric

    def summary(
        self,
        name: str,
        description: str = "",
        labels: Optional[Dict[str, str]] = None
    ) -> Metric:
        """Get or create a summary"""
        return self._get_or_create(name, MetricType.SUMMARY, description, labels)

    def timer(
        self,
        name: str,
        description: str = "",
        labels: Optional[Dict[str, str]] = None
    ) -> Metric:
        """Get or create a timer"""
        return self._get_or_create(name, MetricType.TIMER, description, labels)

    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Increment a counter"""
        metric = self.counter(name, labels=labels)
        metric.increment(value)

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Set a gauge value"""
        metric = self.gauge(name, labels=labels)
        metric.set(value)

    def observe(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Observe a value for histogram/summary"""
        metric = self.histogram(name, labels=labels)
        metric.observe(value)

    def time(
        self,
        name: str,
        duration_seconds: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Record a timer value"""
        metric = self.timer(name, labels=labels)
        metric.observe(duration_seconds)

    def get(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[Metric]:
        """Get a metric by name"""
        key = self._make_key(name, labels or {})
        return self.metrics.get(key)

    def get_all(self, name: Optional[str] = None) -> List[Metric]:
        """Get all metrics, optionally filtered by name"""
        if name:
            return [m for m in self.metrics.values() if m.name == name]
        return list(self.metrics.values())

    def get_by_type(self, metric_type: MetricType) -> List[Metric]:
        """Get metrics by type"""
        return [m for m in self.metrics.values() if m.type == metric_type]

    def get_by_labels(self, labels: Dict[str, str]) -> List[Metric]:
        """Get metrics by labels"""
        return [
            m for m in self.metrics.values()
            if all(m.labels.get(k) == v for k, v in labels.items())
        ]

    def add_collector(self, collector: Callable[[], List[Metric]]) -> None:
        """Add a custom metric collector"""
        self._collectors.append(collector)

    def collect(self) -> List[Metric]:
        """Collect all metrics including from custom collectors"""
        metrics = list(self.metrics.values())
        for collector in self._collectors:
            try:
                metrics.extend(collector())
            except Exception:
                pass
        return metrics

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format"""
        lines = []
        grouped = {}

        for metric in self.collect():
            if metric.name not in grouped:
                grouped[metric.name] = []
            grouped[metric.name].append(metric)

        for name, metrics in grouped.items():
            reg = self._registrations.get(name, {})
            desc = reg.get("description") or metrics[0].description
            mtype = metrics[0].type.value

            if desc:
                lines.append(f"# HELP {name} {desc}")
            lines.append(f"# TYPE {name} {mtype}")

            for metric in metrics:
                labels_str = ""
                if metric.labels:
                    label_parts = [f'{k}="{v}"' for k, v in metric.labels.items()]
                    labels_str = "{" + ",".join(label_parts) + "}"

                if metric.type == MetricType.HISTOGRAM:
                    # Histogram buckets
                    for bucket, count in sorted(metric.buckets.items()):
                        lines.append(f'{name}_bucket{{le="{bucket}"{labels_str}}} {count}')
                    lines.append(f'{name}_bucket{{le="+Inf"{labels_str}}} {metric.count}')
                    lines.append(f'{name}_sum{labels_str} {metric.total}')
                    lines.append(f'{name}_count{labels_str} {metric.count}')
                elif metric.type == MetricType.SUMMARY:
                    lines.append(f'{name}{{quantile="0.5"{labels_str}}} {metric.percentile(50)}')
                    lines.append(f'{name}{{quantile="0.9"{labels_str}}} {metric.percentile(90)}')
                    lines.append(f'{name}{{quantile="0.99"{labels_str}}} {metric.percentile(99)}')
                    lines.append(f'{name}_sum{labels_str} {metric.total}')
                    lines.append(f'{name}_count{labels_str} {metric.count}')
                else:
                    lines.append(f'{name}{labels_str} {metric.value}')

        return "\n".join(lines)

    def reset(self, name: Optional[str] = None) -> int:
        """Reset metrics"""
        if name:
            removed = 0
            for key in list(self.metrics.keys()):
                if key.startswith(name):
                    del self.metrics[key]
                    removed += 1
            return removed
        count = len(self.metrics)
        self.metrics.clear()
        return count

    def get_statistics(self) -> dict:
        """Get collector statistics"""
        type_counts = {}
        for metric in self.metrics.values():
            type_counts[metric.type.value] = type_counts.get(metric.type.value, 0) + 1

        return {
            "total_metrics": len(self.metrics),
            "registered_metrics": len(self._registrations),
            "custom_collectors": len(self._collectors),
            "by_type": type_counts,
            "metric_names": list(set(m.name for m in self.metrics.values()))
        }

    def _get_or_create(
        self,
        name: str,
        metric_type: MetricType,
        description: str = "",
        labels: Optional[Dict[str, str]] = None
    ) -> Metric:
        """Get or create a metric"""
        labels = labels or {}
        key = self._make_key(name, labels)

        if key not in self.metrics:
            reg = self._registrations.get(name, {})
            self.metrics[key] = Metric(
                name=name,
                type=metric_type,
                labels=labels,
                description=description or reg.get("description", ""),
                unit=reg.get("unit", "")
            )

        return self.metrics[key]

    def _make_key(self, name: str, labels: Dict[str, str]) -> str:
        """Generate metric key"""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


# Global metric collector instance
_metric_collector: Optional[MetricCollector] = None


def get_metric_collector() -> MetricCollector:
    """Get or create the global metric collector"""
    global _metric_collector
    if _metric_collector is None:
        _metric_collector = MetricCollector()
    return _metric_collector
