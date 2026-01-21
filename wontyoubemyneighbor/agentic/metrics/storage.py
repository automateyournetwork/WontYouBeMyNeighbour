"""
Time Series Storage

Provides:
- Data point storage
- Time series management
- Retention policies
- Query capabilities
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import bisect


@dataclass
class DataPoint:
    """Single data point"""
    
    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "labels": self.labels,
            "metadata": self.metadata
        }
    
    @staticmethod
    def from_dict(data: dict) -> "DataPoint":
        return DataPoint(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            value=data["value"],
            labels=data.get("labels", {}),
            metadata=data.get("metadata", {})
        )


@dataclass
class TimeSeries:
    """Time series data container"""
    
    id: str
    metric_id: str
    name: str
    labels: Dict[str, str] = field(default_factory=dict)
    data_points: List[DataPoint] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    
    # Configuration
    max_points: int = 10000
    retention_hours: int = 24
    
    # Statistics (cached)
    _min_value: Optional[float] = None
    _max_value: Optional[float] = None
    _sum_value: float = 0.0
    _count: int = 0
    
    def add_point(self, value: float, timestamp: Optional[datetime] = None, labels: Optional[Dict[str, str]] = None) -> DataPoint:
        """Add a data point"""
        ts = timestamp or datetime.now()
        merged_labels = {**self.labels, **(labels or {})}
        
        point = DataPoint(
            timestamp=ts,
            value=value,
            labels=merged_labels
        )
        
        # Insert in sorted order by timestamp
        if not self.data_points or ts >= self.data_points[-1].timestamp:
            self.data_points.append(point)
        else:
            # Binary insert
            timestamps = [p.timestamp for p in self.data_points]
            idx = bisect.bisect_left(timestamps, ts)
            self.data_points.insert(idx, point)
        
        # Update statistics
        self._count += 1
        self._sum_value += value
        if self._min_value is None or value < self._min_value:
            self._min_value = value
        if self._max_value is None or value > self._max_value:
            self._max_value = value
        
        # Enforce max points
        if len(self.data_points) > self.max_points:
            removed = self.data_points.pop(0)
            self._count -= 1
            self._sum_value -= removed.value
        
        # Enforce retention
        self._apply_retention()
        
        return point
    
    def _apply_retention(self) -> None:
        """Remove data points older than retention period"""
        cutoff = datetime.now() - timedelta(hours=self.retention_hours)
        
        while self.data_points and self.data_points[0].timestamp < cutoff:
            removed = self.data_points.pop(0)
            self._count -= 1
            self._sum_value -= removed.value
        
        # Recalculate min/max if needed
        if self.data_points:
            self._min_value = min(p.value for p in self.data_points)
            self._max_value = max(p.value for p in self.data_points)
        else:
            self._min_value = None
            self._max_value = None
    
    def get_points(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[DataPoint]:
        """Get data points within time range"""
        points = self.data_points
        
        if start:
            points = [p for p in points if p.timestamp >= start]
        if end:
            points = [p for p in points if p.timestamp <= end]
        if limit:
            points = points[-limit:]
        
        return points
    
    def get_latest(self, n: int = 1) -> List[DataPoint]:
        """Get latest N data points"""
        return self.data_points[-n:] if self.data_points else []
    
    def get_value_at(self, timestamp: datetime) -> Optional[float]:
        """Get value at or closest to timestamp"""
        if not self.data_points:
            return None
        
        timestamps = [p.timestamp for p in self.data_points]
        idx = bisect.bisect_left(timestamps, timestamp)
        
        if idx == 0:
            return self.data_points[0].value
        if idx == len(self.data_points):
            return self.data_points[-1].value
        
        # Return closer value
        before = self.data_points[idx - 1]
        after = self.data_points[idx]
        
        if abs((timestamp - before.timestamp).total_seconds()) < abs((after.timestamp - timestamp).total_seconds()):
            return before.value
        return after.value
    
    def get_statistics(self) -> dict:
        """Get time series statistics"""
        if not self.data_points:
            return {
                "count": 0,
                "min": None,
                "max": None,
                "avg": None,
                "sum": 0,
                "first_timestamp": None,
                "last_timestamp": None
            }
        
        return {
            "count": len(self.data_points),
            "min": self._min_value,
            "max": self._max_value,
            "avg": self._sum_value / len(self.data_points) if self.data_points else None,
            "sum": self._sum_value,
            "first_timestamp": self.data_points[0].timestamp.isoformat(),
            "last_timestamp": self.data_points[-1].timestamp.isoformat()
        }
    
    def to_dict(self, include_points: bool = False) -> dict:
        result = {
            "id": self.id,
            "metric_id": self.metric_id,
            "name": self.name,
            "labels": self.labels,
            "created_at": self.created_at.isoformat(),
            "max_points": self.max_points,
            "retention_hours": self.retention_hours,
            "statistics": self.get_statistics()
        }
        
        if include_points:
            result["data_points"] = [p.to_dict() for p in self.data_points]
        
        return result


class TimeSeriesStore:
    """Manages time series data"""
    
    def __init__(self):
        self.series: Dict[str, TimeSeries] = {}
        self._by_metric: Dict[str, List[str]] = defaultdict(list)  # metric_id -> series_ids
        self._by_label: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))  # label_key -> label_value -> series_ids
    
    def create_series(
        self,
        metric_id: str,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        max_points: int = 10000,
        retention_hours: int = 24
    ) -> TimeSeries:
        """Create a new time series"""
        series_id = f"ts_{uuid.uuid4().hex[:8]}"
        
        series = TimeSeries(
            id=series_id,
            metric_id=metric_id,
            name=name,
            labels=labels or {},
            max_points=max_points,
            retention_hours=retention_hours
        )
        
        self.series[series_id] = series
        self._by_metric[metric_id].append(series_id)
        
        # Index by labels
        for key, value in (labels or {}).items():
            self._by_label[key][value].append(series_id)
        
        return series
    
    def get_series(self, series_id: str) -> Optional[TimeSeries]:
        """Get time series by ID"""
        return self.series.get(series_id)
    
    def get_or_create_series(
        self,
        metric_id: str,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> TimeSeries:
        """Get existing series or create new one"""
        # Try to find existing series with same metric_id and labels
        for series_id in self._by_metric.get(metric_id, []):
            series = self.series.get(series_id)
            if series and series.labels == (labels or {}):
                return series
        
        return self.create_series(metric_id, name, labels, **kwargs)
    
    def delete_series(self, series_id: str) -> bool:
        """Delete a time series"""
        series = self.series.get(series_id)
        if not series:
            return False
        
        # Remove from indexes
        if series_id in self._by_metric.get(series.metric_id, []):
            self._by_metric[series.metric_id].remove(series_id)
        
        for key, value in series.labels.items():
            if series_id in self._by_label.get(key, {}).get(value, []):
                self._by_label[key][value].remove(series_id)
        
        del self.series[series_id]
        return True
    
    def record(
        self,
        metric_id: str,
        value: float,
        timestamp: Optional[datetime] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> DataPoint:
        """Record a value for a metric"""
        series = self.get_or_create_series(
            metric_id=metric_id,
            name=metric_id,
            labels=labels
        )
        return series.add_point(value, timestamp, labels)
    
    def query(
        self,
        metric_id: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Tuple[TimeSeries, List[DataPoint]]]:
        """Query time series data"""
        results = []
        
        # Filter series
        candidate_ids = set(self.series.keys())
        
        if metric_id:
            candidate_ids &= set(self._by_metric.get(metric_id, []))
        
        if labels:
            for key, value in labels.items():
                candidate_ids &= set(self._by_label.get(key, {}).get(value, []))
        
        # Get data from matching series
        for series_id in candidate_ids:
            series = self.series.get(series_id)
            if series:
                points = series.get_points(start, end, limit)
                results.append((series, points))
        
        return results
    
    def get_series_for_metric(self, metric_id: str) -> List[TimeSeries]:
        """Get all series for a metric"""
        series_ids = self._by_metric.get(metric_id, [])
        return [self.series[sid] for sid in series_ids if sid in self.series]
    
    def get_series_by_labels(self, labels: Dict[str, str]) -> List[TimeSeries]:
        """Get series matching all labels"""
        if not labels:
            return list(self.series.values())
        
        candidate_ids = None
        for key, value in labels.items():
            matching = set(self._by_label.get(key, {}).get(value, []))
            if candidate_ids is None:
                candidate_ids = matching
            else:
                candidate_ids &= matching
        
        return [self.series[sid] for sid in (candidate_ids or []) if sid in self.series]
    
    def get_latest_values(
        self,
        metric_id: Optional[str] = None
    ) -> Dict[str, float]:
        """Get latest value for each series"""
        results = {}
        
        series_list = self.series.values()
        if metric_id:
            series_list = [s for s in series_list if s.metric_id == metric_id]
        
        for series in series_list:
            latest = series.get_latest(1)
            if latest:
                results[series.id] = latest[0].value
        
        return results
    
    def cleanup(self, older_than_hours: Optional[int] = None) -> int:
        """Clean up old data points"""
        removed_count = 0
        
        for series in self.series.values():
            if older_than_hours:
                series.retention_hours = older_than_hours
            
            before_count = len(series.data_points)
            series._apply_retention()
            removed_count += before_count - len(series.data_points)
        
        return removed_count
    
    def get_all_series(self) -> List[TimeSeries]:
        """Get all time series"""
        return list(self.series.values())
    
    def get_label_keys(self) -> List[str]:
        """Get all unique label keys"""
        return list(self._by_label.keys())
    
    def get_label_values(self, key: str) -> List[str]:
        """Get all values for a label key"""
        return list(self._by_label.get(key, {}).keys())
    
    def get_statistics(self) -> dict:
        """Get store statistics"""
        total_points = sum(len(s.data_points) for s in self.series.values())
        
        return {
            "total_series": len(self.series),
            "total_data_points": total_points,
            "unique_metrics": len(self._by_metric),
            "label_keys": len(self._by_label),
            "oldest_point": min(
                (s.data_points[0].timestamp for s in self.series.values() if s.data_points),
                default=None
            ),
            "newest_point": max(
                (s.data_points[-1].timestamp for s in self.series.values() if s.data_points),
                default=None
            )
        }


# Global time series store instance
_timeseries_store: Optional[TimeSeriesStore] = None


def get_timeseries_store() -> TimeSeriesStore:
    """Get or create the global time series store"""
    global _timeseries_store
    if _timeseries_store is None:
        _timeseries_store = TimeSeriesStore()
    return _timeseries_store
