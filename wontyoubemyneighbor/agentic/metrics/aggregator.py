"""
Metric Aggregator

Provides:
- Aggregation functions
- Downsampling
- Statistical calculations
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum
import math

from .storage import DataPoint, TimeSeries, TimeSeriesStore, get_timeseries_store


class AggregationType(Enum):
    """Types of aggregation"""
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    FIRST = "first"
    LAST = "last"
    MEDIAN = "median"
    PERCENTILE_95 = "p95"
    PERCENTILE_99 = "p99"
    STDDEV = "stddev"
    VARIANCE = "variance"
    RATE = "rate"  # Rate of change
    DELTA = "delta"  # Difference from first


class AggregationWindow(Enum):
    """Time windows for aggregation"""
    MINUTE = 60
    FIVE_MINUTES = 300
    FIFTEEN_MINUTES = 900
    HOUR = 3600
    SIX_HOURS = 21600
    DAY = 86400
    WEEK = 604800


@dataclass
class AggregationResult:
    """Result of an aggregation"""
    
    series_id: str
    aggregation_type: AggregationType
    window: AggregationWindow
    start_time: datetime
    end_time: datetime
    value: float
    point_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "series_id": self.series_id,
            "aggregation_type": self.aggregation_type.value,
            "window": self.window.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "value": self.value,
            "point_count": self.point_count,
            "metadata": self.metadata
        }


@dataclass
class DownsampledSeries:
    """Downsampled time series"""
    
    id: str
    source_series_id: str
    aggregation_type: AggregationType
    window: AggregationWindow
    points: List[DataPoint] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self, include_points: bool = True) -> dict:
        result = {
            "id": self.id,
            "source_series_id": self.source_series_id,
            "aggregation_type": self.aggregation_type.value,
            "window": self.window.value,
            "point_count": len(self.points),
            "created_at": self.created_at.isoformat()
        }
        if include_points:
            result["points"] = [p.to_dict() for p in self.points]
        return result


class MetricAggregator:
    """Performs metric aggregation"""
    
    def __init__(self, store: Optional[TimeSeriesStore] = None):
        self.store = store or get_timeseries_store()
        self._aggregation_cache: Dict[str, AggregationResult] = {}
        self._downsampled: Dict[str, DownsampledSeries] = {}
    
    def _get_percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile value"""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        idx = int(len(sorted_values) * percentile / 100)
        return sorted_values[min(idx, len(sorted_values) - 1)]
    
    def _calculate_stddev(self, values: List[float]) -> float:
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)
    
    def aggregate(
        self,
        series_id: str,
        aggregation_type: AggregationType,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> Optional[AggregationResult]:
        """Aggregate a time series"""
        series = self.store.get_series(series_id)
        if not series:
            return None
        
        points = series.get_points(start, end)
        if not points:
            return None
        
        values = [p.value for p in points]
        
        # Calculate aggregation
        if aggregation_type == AggregationType.SUM:
            value = sum(values)
        elif aggregation_type == AggregationType.AVG:
            value = sum(values) / len(values)
        elif aggregation_type == AggregationType.MIN:
            value = min(values)
        elif aggregation_type == AggregationType.MAX:
            value = max(values)
        elif aggregation_type == AggregationType.COUNT:
            value = float(len(values))
        elif aggregation_type == AggregationType.FIRST:
            value = values[0]
        elif aggregation_type == AggregationType.LAST:
            value = values[-1]
        elif aggregation_type == AggregationType.MEDIAN:
            value = self._get_percentile(values, 50)
        elif aggregation_type == AggregationType.PERCENTILE_95:
            value = self._get_percentile(values, 95)
        elif aggregation_type == AggregationType.PERCENTILE_99:
            value = self._get_percentile(values, 99)
        elif aggregation_type == AggregationType.STDDEV:
            value = self._calculate_stddev(values)
        elif aggregation_type == AggregationType.VARIANCE:
            if len(values) < 2:
                value = 0.0
            else:
                mean = sum(values) / len(values)
                value = sum((x - mean) ** 2 for x in values) / len(values)
        elif aggregation_type == AggregationType.RATE:
            if len(values) < 2:
                value = 0.0
            else:
                time_diff = (points[-1].timestamp - points[0].timestamp).total_seconds()
                if time_diff > 0:
                    value = (values[-1] - values[0]) / time_diff
                else:
                    value = 0.0
        elif aggregation_type == AggregationType.DELTA:
            value = values[-1] - values[0] if len(values) >= 2 else 0.0
        else:
            value = 0.0
        
        result = AggregationResult(
            series_id=series_id,
            aggregation_type=aggregation_type,
            window=AggregationWindow.HOUR,  # Default
            start_time=points[0].timestamp,
            end_time=points[-1].timestamp,
            value=value,
            point_count=len(points)
        )
        
        return result
    
    def aggregate_by_window(
        self,
        series_id: str,
        aggregation_type: AggregationType,
        window: AggregationWindow,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[AggregationResult]:
        """Aggregate by time window"""
        series = self.store.get_series(series_id)
        if not series:
            return []
        
        points = series.get_points(start, end)
        if not points:
            return []
        
        # Group points by window
        window_seconds = window.value
        buckets: Dict[datetime, List[float]] = {}
        
        for point in points:
            # Round down to window boundary
            ts = point.timestamp
            bucket_ts = datetime.fromtimestamp(
                (ts.timestamp() // window_seconds) * window_seconds
            )
            if bucket_ts not in buckets:
                buckets[bucket_ts] = []
            buckets[bucket_ts].append(point.value)
        
        results = []
        for bucket_ts in sorted(buckets.keys()):
            values = buckets[bucket_ts]
            bucket_end = bucket_ts + timedelta(seconds=window_seconds)
            
            # Calculate aggregation for bucket
            if aggregation_type == AggregationType.SUM:
                value = sum(values)
            elif aggregation_type == AggregationType.AVG:
                value = sum(values) / len(values)
            elif aggregation_type == AggregationType.MIN:
                value = min(values)
            elif aggregation_type == AggregationType.MAX:
                value = max(values)
            elif aggregation_type == AggregationType.COUNT:
                value = float(len(values))
            elif aggregation_type == AggregationType.FIRST:
                value = values[0]
            elif aggregation_type == AggregationType.LAST:
                value = values[-1]
            elif aggregation_type == AggregationType.MEDIAN:
                value = self._get_percentile(values, 50)
            elif aggregation_type == AggregationType.PERCENTILE_95:
                value = self._get_percentile(values, 95)
            elif aggregation_type == AggregationType.PERCENTILE_99:
                value = self._get_percentile(values, 99)
            elif aggregation_type == AggregationType.STDDEV:
                value = self._calculate_stddev(values)
            else:
                value = sum(values) / len(values)  # Default to avg
            
            results.append(AggregationResult(
                series_id=series_id,
                aggregation_type=aggregation_type,
                window=window,
                start_time=bucket_ts,
                end_time=bucket_end,
                value=value,
                point_count=len(values)
            ))
        
        return results
    
    def downsample(
        self,
        series_id: str,
        aggregation_type: AggregationType,
        window: AggregationWindow,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> Optional[DownsampledSeries]:
        """Create downsampled series"""
        aggregations = self.aggregate_by_window(
            series_id, aggregation_type, window, start, end
        )
        
        if not aggregations:
            return None
        
        ds_id = f"ds_{uuid.uuid4().hex[:8]}"
        
        points = [
            DataPoint(
                timestamp=agg.start_time,
                value=agg.value,
                metadata={"window": window.value, "point_count": agg.point_count}
            )
            for agg in aggregations
        ]
        
        downsampled = DownsampledSeries(
            id=ds_id,
            source_series_id=series_id,
            aggregation_type=aggregation_type,
            window=window,
            points=points
        )
        
        self._downsampled[ds_id] = downsampled
        return downsampled
    
    def get_downsampled(self, ds_id: str) -> Optional[DownsampledSeries]:
        """Get downsampled series by ID"""
        return self._downsampled.get(ds_id)
    
    def compare_series(
        self,
        series_ids: List[str],
        aggregation_type: AggregationType = AggregationType.AVG,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Compare multiple series"""
        results = {}
        for series_id in series_ids:
            agg = self.aggregate(series_id, aggregation_type, start, end)
            if agg:
                results[series_id] = agg.value
        return results
    
    def get_moving_average(
        self,
        series_id: str,
        window_size: int = 10,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[DataPoint]:
        """Calculate moving average"""
        series = self.store.get_series(series_id)
        if not series:
            return []
        
        points = series.get_points(start, end)
        if len(points) < window_size:
            return []
        
        results = []
        for i in range(window_size - 1, len(points)):
            window_points = points[i - window_size + 1:i + 1]
            avg_value = sum(p.value for p in window_points) / window_size
            results.append(DataPoint(
                timestamp=points[i].timestamp,
                value=avg_value,
                metadata={"window_size": window_size}
            ))
        
        return results
    
    def detect_anomalies(
        self,
        series_id: str,
        threshold_stddev: float = 2.0,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[DataPoint]:
        """Detect anomalies using standard deviation"""
        series = self.store.get_series(series_id)
        if not series:
            return []
        
        points = series.get_points(start, end)
        if len(points) < 3:
            return []
        
        values = [p.value for p in points]
        mean = sum(values) / len(values)
        stddev = self._calculate_stddev(values)
        
        if stddev == 0:
            return []
        
        anomalies = []
        for point in points:
            z_score = abs(point.value - mean) / stddev
            if z_score > threshold_stddev:
                anomaly = DataPoint(
                    timestamp=point.timestamp,
                    value=point.value,
                    metadata={"z_score": z_score, "mean": mean, "stddev": stddev}
                )
                anomalies.append(anomaly)
        
        return anomalies
    
    def forecast_simple(
        self,
        series_id: str,
        periods: int = 10,
        method: str = "linear"
    ) -> List[DataPoint]:
        """Simple forecasting"""
        series = self.store.get_series(series_id)
        if not series or len(series.data_points) < 2:
            return []
        
        points = series.data_points
        
        # Calculate average interval
        intervals = []
        for i in range(1, len(points)):
            intervals.append((points[i].timestamp - points[i-1].timestamp).total_seconds())
        avg_interval = sum(intervals) / len(intervals) if intervals else 60
        
        # Calculate trend
        if method == "linear":
            # Simple linear regression
            n = len(points)
            x = list(range(n))
            y = [p.value for p in points]
            
            x_mean = sum(x) / n
            y_mean = sum(y) / n
            
            numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
            denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
            
            if denominator == 0:
                slope = 0
            else:
                slope = numerator / denominator
            
            intercept = y_mean - slope * x_mean
        else:
            # Simple average
            slope = 0
            intercept = sum(p.value for p in points) / len(points)
        
        # Generate forecasts
        forecasts = []
        last_ts = points[-1].timestamp
        
        for i in range(1, periods + 1):
            forecast_ts = last_ts + timedelta(seconds=avg_interval * i)
            forecast_value = slope * (len(points) + i - 1) + intercept
            
            forecasts.append(DataPoint(
                timestamp=forecast_ts,
                value=forecast_value,
                metadata={"method": method, "forecast": True}
            ))
        
        return forecasts
    
    def get_statistics(self) -> dict:
        """Get aggregator statistics"""
        return {
            "cached_aggregations": len(self._aggregation_cache),
            "downsampled_series": len(self._downsampled),
            "total_downsampled_points": sum(len(ds.points) for ds in self._downsampled.values())
        }


# Global metric aggregator instance
_metric_aggregator: Optional[MetricAggregator] = None


def get_metric_aggregator() -> MetricAggregator:
    """Get or create the global metric aggregator"""
    global _metric_aggregator
    if _metric_aggregator is None:
        _metric_aggregator = MetricAggregator()
    return _metric_aggregator
