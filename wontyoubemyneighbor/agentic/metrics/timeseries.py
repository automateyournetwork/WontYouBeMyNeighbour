"""
Time Series Storage

Provides:
- Time series data storage
- Data point management
- Aggregation and downsampling
- Range queries
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
import statistics


class AggregationType(Enum):
    """Aggregation types for downsampling"""
    AVG = "avg"
    SUM = "sum"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    LAST = "last"
    FIRST = "first"


@dataclass
class DataPoint:
    """Single data point in time series"""

    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "labels": self.labels
        }


@dataclass
class TimeSeries:
    """Time series data for a metric"""

    name: str
    labels: Dict[str, str] = field(default_factory=dict)
    data_points: List[DataPoint] = field(default_factory=list)
    retention_days: int = 7
    max_points: int = 100000

    @property
    def key(self) -> str:
        """Generate unique key"""
        if not self.labels:
            return self.name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(self.labels.items()))
        return f"{self.name}{{{label_str}}}"

    def add(self, value: float, timestamp: Optional[datetime] = None, labels: Optional[Dict[str, str]] = None) -> DataPoint:
        """Add a data point"""
        point = DataPoint(
            timestamp=timestamp or datetime.now(),
            value=value,
            labels=labels or {}
        )
        self.data_points.append(point)

        # Enforce max points
        if len(self.data_points) > self.max_points:
            self.data_points = self.data_points[-self.max_points // 2:]

        return point

    def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[DataPoint]:
        """Query data points within time range"""
        points = self.data_points

        if start_time:
            points = [p for p in points if p.timestamp >= start_time]
        if end_time:
            points = [p for p in points if p.timestamp <= end_time]

        points = sorted(points, key=lambda p: p.timestamp)

        if limit:
            points = points[-limit:]

        return points

    def aggregate(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        aggregation: AggregationType = AggregationType.AVG
    ) -> float:
        """Aggregate data points"""
        points = self.query(start_time, end_time)

        if not points:
            return 0.0

        values = [p.value for p in points]

        if aggregation == AggregationType.AVG:
            return statistics.mean(values)
        elif aggregation == AggregationType.SUM:
            return sum(values)
        elif aggregation == AggregationType.MIN:
            return min(values)
        elif aggregation == AggregationType.MAX:
            return max(values)
        elif aggregation == AggregationType.COUNT:
            return float(len(values))
        elif aggregation == AggregationType.LAST:
            return values[-1]
        elif aggregation == AggregationType.FIRST:
            return values[0]

        return 0.0

    def downsample(
        self,
        interval_seconds: int,
        aggregation: AggregationType = AggregationType.AVG,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[DataPoint]:
        """Downsample data to larger time intervals"""
        points = self.query(start_time, end_time)

        if not points:
            return []

        # Group by interval
        buckets: Dict[datetime, List[float]] = {}
        interval = timedelta(seconds=interval_seconds)

        for point in points:
            # Round to interval
            bucket_time = datetime.fromtimestamp(
                (point.timestamp.timestamp() // interval_seconds) * interval_seconds
            )
            if bucket_time not in buckets:
                buckets[bucket_time] = []
            buckets[bucket_time].append(point.value)

        # Aggregate each bucket
        result = []
        for timestamp, values in sorted(buckets.items()):
            if aggregation == AggregationType.AVG:
                value = statistics.mean(values)
            elif aggregation == AggregationType.SUM:
                value = sum(values)
            elif aggregation == AggregationType.MIN:
                value = min(values)
            elif aggregation == AggregationType.MAX:
                value = max(values)
            elif aggregation == AggregationType.COUNT:
                value = float(len(values))
            elif aggregation == AggregationType.LAST:
                value = values[-1]
            elif aggregation == AggregationType.FIRST:
                value = values[0]
            else:
                value = statistics.mean(values)

            result.append(DataPoint(timestamp=timestamp, value=value))

        return result

    def cleanup(self) -> int:
        """Remove old data points"""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        old_count = len(self.data_points)
        self.data_points = [p for p in self.data_points if p.timestamp >= cutoff]
        return old_count - len(self.data_points)

    @property
    def latest_value(self) -> Optional[float]:
        """Get latest value"""
        if not self.data_points:
            return None
        return self.data_points[-1].value

    @property
    def point_count(self) -> int:
        """Get number of data points"""
        return len(self.data_points)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "labels": self.labels,
            "point_count": self.point_count,
            "latest_value": self.latest_value,
            "retention_days": self.retention_days
        }


class TimeSeriesStore:
    """Stores and manages time series data"""

    def __init__(self):
        self.series: Dict[str, TimeSeries] = {}
        self.default_retention_days = 7
        self.default_max_points = 100000

    def get_or_create(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None
    ) -> TimeSeries:
        """Get or create time series"""
        labels = labels or {}
        key = self._make_key(name, labels)

        if key not in self.series:
            self.series[key] = TimeSeries(
                name=name,
                labels=labels,
                retention_days=self.default_retention_days,
                max_points=self.default_max_points
            )

        return self.series[key]

    def record(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        timestamp: Optional[datetime] = None
    ) -> DataPoint:
        """Record a data point"""
        ts = self.get_or_create(name, labels)
        return ts.add(value, timestamp)

    def query(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[DataPoint]:
        """Query time series data"""
        ts = self.get_or_create(name, labels)
        return ts.query(start_time, end_time, limit)

    def query_range(
        self,
        name: str,
        duration: timedelta,
        labels: Optional[Dict[str, str]] = None
    ) -> List[DataPoint]:
        """Query data for duration from now"""
        start_time = datetime.now() - duration
        return self.query(name, labels, start_time=start_time)

    def aggregate(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        aggregation: AggregationType = AggregationType.AVG
    ) -> float:
        """Aggregate time series data"""
        ts = self.get_or_create(name, labels)
        return ts.aggregate(start_time, end_time, aggregation)

    def downsample(
        self,
        name: str,
        interval_seconds: int,
        labels: Optional[Dict[str, str]] = None,
        aggregation: AggregationType = AggregationType.AVG,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[DataPoint]:
        """Downsample time series"""
        ts = self.get_or_create(name, labels)
        return ts.downsample(interval_seconds, aggregation, start_time, end_time)

    def get_latest(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None
    ) -> Optional[float]:
        """Get latest value"""
        ts = self.get_or_create(name, labels)
        return ts.latest_value

    def list_series(self, name_filter: Optional[str] = None) -> List[TimeSeries]:
        """List all time series"""
        series = list(self.series.values())
        if name_filter:
            series = [s for s in series if name_filter in s.name]
        return series

    def delete_series(self, name: str, labels: Optional[Dict[str, str]] = None) -> bool:
        """Delete a time series"""
        key = self._make_key(name, labels or {})
        if key in self.series:
            del self.series[key]
            return True
        return False

    def cleanup(self) -> int:
        """Cleanup old data from all series"""
        total = 0
        for ts in self.series.values():
            total += ts.cleanup()
        return total

    def get_statistics(self) -> dict:
        """Get store statistics"""
        total_points = sum(ts.point_count for ts in self.series.values())
        return {
            "series_count": len(self.series),
            "total_data_points": total_points,
            "default_retention_days": self.default_retention_days,
            "series_names": list(set(ts.name for ts in self.series.values()))
        }

    def _make_key(self, name: str, labels: Dict[str, str]) -> str:
        """Generate series key"""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


# Global time series store instance
_timeseries_store: Optional[TimeSeriesStore] = None


def get_timeseries_store() -> TimeSeriesStore:
    """Get or create the global time series store"""
    global _timeseries_store
    if _timeseries_store is None:
        _timeseries_store = TimeSeriesStore()
    return _timeseries_store
