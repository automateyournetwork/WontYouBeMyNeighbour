"""
Capacity Planner

Network capacity planning, forecasting, and recommendations.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import uuid
import math
import statistics


class ResourceType(Enum):
    """Type of network resource."""
    BANDWIDTH = "bandwidth"
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    PORTS = "ports"
    CONNECTIONS = "connections"
    SESSIONS = "sessions"
    ROUTES = "routes"
    NEIGHBORS = "neighbors"
    VLANS = "vlans"
    PREFIXES = "prefixes"
    POWER = "power"
    CUSTOM = "custom"


class UtilizationLevel(Enum):
    """Utilization severity level."""
    IDLE = "idle"  # < 10%
    LOW = "low"  # 10-30%
    MODERATE = "moderate"  # 30-60%
    HIGH = "high"  # 60-80%
    CRITICAL = "critical"  # 80-95%
    EXHAUSTED = "exhausted"  # > 95%


class TrendDirection(Enum):
    """Trend direction for capacity."""
    DECREASING = "decreasing"
    STABLE = "stable"
    INCREASING = "increasing"
    RAPIDLY_INCREASING = "rapidly_increasing"


@dataclass
class ResourceMetric:
    """A single capacity metric data point."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    resource_type: ResourceType = ResourceType.CUSTOM
    device_id: str = ""
    device_name: str = ""
    resource_name: str = ""  # e.g., "eth0", "CPU 0", "Routing Table"

    # Values
    current_value: float = 0.0
    max_capacity: float = 100.0
    unit: str = ""  # e.g., "Mbps", "%", "GB", "routes"

    # Utilization
    utilization_pct: float = 0.0
    utilization_level: UtilizationLevel = UtilizationLevel.LOW

    # Historical data (last 24 samples, e.g., hourly)
    history: List[Tuple[str, float]] = field(default_factory=list)

    # Thresholds
    warning_threshold: float = 70.0
    critical_threshold: float = 90.0

    # Timestamps
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "resource_type": self.resource_type.value,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "resource_name": self.resource_name,
            "current_value": self.current_value,
            "max_capacity": self.max_capacity,
            "unit": self.unit,
            "utilization_pct": self.utilization_pct,
            "utilization_level": self.utilization_level.value,
            "history": self.history,
            "warning_threshold": self.warning_threshold,
            "critical_threshold": self.critical_threshold,
            "timestamp": self.timestamp
        }

    def calculate_utilization(self):
        """Calculate utilization percentage and level."""
        if self.max_capacity > 0:
            self.utilization_pct = (self.current_value / self.max_capacity) * 100
        else:
            self.utilization_pct = 0.0

        # Determine level
        if self.utilization_pct < 10:
            self.utilization_level = UtilizationLevel.IDLE
        elif self.utilization_pct < 30:
            self.utilization_level = UtilizationLevel.LOW
        elif self.utilization_pct < 60:
            self.utilization_level = UtilizationLevel.MODERATE
        elif self.utilization_pct < 80:
            self.utilization_level = UtilizationLevel.HIGH
        elif self.utilization_pct < 95:
            self.utilization_level = UtilizationLevel.CRITICAL
        else:
            self.utilization_level = UtilizationLevel.EXHAUSTED


@dataclass
class CapacityThreshold:
    """Threshold configuration for capacity alerts."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    resource_type: ResourceType = ResourceType.CUSTOM
    device_pattern: str = "*"  # Glob pattern for device matching
    resource_pattern: str = "*"  # Glob pattern for resource matching

    warning_pct: float = 70.0
    critical_pct: float = 90.0

    # Actions
    alert_on_warning: bool = True
    alert_on_critical: bool = True
    auto_scale: bool = False

    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "resource_type": self.resource_type.value,
            "device_pattern": self.device_pattern,
            "resource_pattern": self.resource_pattern,
            "warning_pct": self.warning_pct,
            "critical_pct": self.critical_pct,
            "alert_on_warning": self.alert_on_warning,
            "alert_on_critical": self.alert_on_critical,
            "auto_scale": self.auto_scale,
            "enabled": self.enabled,
            "created_at": self.created_at
        }


@dataclass
class CapacityForecast:
    """Capacity forecast prediction."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    resource_type: ResourceType = ResourceType.CUSTOM
    device_id: str = ""
    device_name: str = ""
    resource_name: str = ""

    # Current state
    current_utilization: float = 0.0
    current_value: float = 0.0
    max_capacity: float = 100.0
    unit: str = ""

    # Trend analysis
    trend_direction: TrendDirection = TrendDirection.STABLE
    trend_slope: float = 0.0  # Units per day
    trend_confidence: float = 0.0  # 0-1

    # Predictions
    predicted_7d: float = 0.0
    predicted_30d: float = 0.0
    predicted_90d: float = 0.0

    # Time to thresholds
    days_to_warning: Optional[int] = None
    days_to_critical: Optional[int] = None
    days_to_exhaustion: Optional[int] = None

    # Generated at
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "resource_type": self.resource_type.value,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "resource_name": self.resource_name,
            "current_utilization": self.current_utilization,
            "current_value": self.current_value,
            "max_capacity": self.max_capacity,
            "unit": self.unit,
            "trend_direction": self.trend_direction.value,
            "trend_slope": self.trend_slope,
            "trend_confidence": self.trend_confidence,
            "predicted_7d": self.predicted_7d,
            "predicted_30d": self.predicted_30d,
            "predicted_90d": self.predicted_90d,
            "days_to_warning": self.days_to_warning,
            "days_to_critical": self.days_to_critical,
            "days_to_exhaustion": self.days_to_exhaustion,
            "generated_at": self.generated_at
        }


@dataclass
class CapacityRecommendation:
    """Capacity planning recommendation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: str = "medium"  # low, medium, high, critical
    category: str = ""  # upgrade, optimize, redistribute, decommission

    device_id: str = ""
    device_name: str = ""
    resource_type: ResourceType = ResourceType.CUSTOM
    resource_name: str = ""

    title: str = ""
    description: str = ""
    impact: str = ""  # What happens if not addressed
    action: str = ""  # Recommended action

    # Cost estimate (optional)
    estimated_cost: Optional[float] = None
    cost_currency: str = "USD"

    # Timeframe
    urgency_days: int = 30  # Days until action needed

    # Status
    status: str = "pending"  # pending, acknowledged, in_progress, completed, dismissed

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "priority": self.priority,
            "category": self.category,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "resource_type": self.resource_type.value,
            "resource_name": self.resource_name,
            "title": self.title,
            "description": self.description,
            "impact": self.impact,
            "action": self.action,
            "estimated_cost": self.estimated_cost,
            "cost_currency": self.cost_currency,
            "urgency_days": self.urgency_days,
            "status": self.status,
            "created_at": self.created_at
        }


class CapacityPlanner:
    """
    Network capacity planning and forecasting.

    Tracks resource utilization, generates forecasts, and provides
    recommendations for capacity planning.
    """

    def __init__(self):
        self._metrics: Dict[str, ResourceMetric] = {}
        self._thresholds: Dict[str, CapacityThreshold] = {}
        self._forecasts: Dict[str, CapacityForecast] = {}
        self._recommendations: Dict[str, CapacityRecommendation] = {}

        # Initialize default thresholds
        self._init_default_thresholds()

    def _init_default_thresholds(self):
        """Initialize default capacity thresholds."""
        defaults = [
            (ResourceType.BANDWIDTH, 70, 90),
            (ResourceType.CPU, 75, 90),
            (ResourceType.MEMORY, 80, 95),
            (ResourceType.STORAGE, 80, 95),
            (ResourceType.PORTS, 80, 95),
            (ResourceType.CONNECTIONS, 70, 85),
            (ResourceType.ROUTES, 75, 90),
            (ResourceType.PREFIXES, 80, 95),
        ]

        for rtype, warn, crit in defaults:
            threshold = CapacityThreshold(
                resource_type=rtype,
                warning_pct=warn,
                critical_pct=crit
            )
            self._thresholds[threshold.id] = threshold

    # ==================== Metrics ====================

    def record_metric(
        self,
        resource_type: ResourceType,
        device_id: str,
        device_name: str,
        resource_name: str,
        current_value: float,
        max_capacity: float,
        unit: str = ""
    ) -> ResourceMetric:
        """Record a capacity metric."""
        # Create unique key
        key = f"{device_id}:{resource_type.value}:{resource_name}"

        # Get or create metric
        metric = self._metrics.get(key)
        if not metric:
            metric = ResourceMetric(
                resource_type=resource_type,
                device_id=device_id,
                device_name=device_name,
                resource_name=resource_name,
                max_capacity=max_capacity,
                unit=unit
            )
            self._metrics[key] = metric

        # Add to history
        timestamp = datetime.utcnow().isoformat()
        metric.history.append((timestamp, current_value))

        # Keep only last 24 data points
        if len(metric.history) > 24:
            metric.history = metric.history[-24:]

        # Update current values
        metric.current_value = current_value
        metric.max_capacity = max_capacity
        metric.timestamp = timestamp
        metric.calculate_utilization()

        return metric

    def get_metric(self, metric_id: str) -> Optional[ResourceMetric]:
        """Get a specific metric by ID."""
        return self._metrics.get(metric_id)

    def get_metrics(
        self,
        resource_type: Optional[ResourceType] = None,
        device_id: Optional[str] = None,
        min_utilization: Optional[float] = None
    ) -> List[ResourceMetric]:
        """Get metrics with optional filtering."""
        metrics = list(self._metrics.values())

        if resource_type:
            metrics = [m for m in metrics if m.resource_type == resource_type]

        if device_id:
            metrics = [m for m in metrics if m.device_id == device_id]

        if min_utilization is not None:
            metrics = [m for m in metrics if m.utilization_pct >= min_utilization]

        return sorted(metrics, key=lambda m: m.utilization_pct, reverse=True)

    def get_critical_metrics(self) -> List[ResourceMetric]:
        """Get all metrics at critical or exhausted level."""
        return [m for m in self._metrics.values()
                if m.utilization_level in (UtilizationLevel.CRITICAL, UtilizationLevel.EXHAUSTED)]

    # ==================== Thresholds ====================

    def add_threshold(self, threshold: CapacityThreshold) -> CapacityThreshold:
        """Add a custom threshold."""
        self._thresholds[threshold.id] = threshold
        return threshold

    def update_threshold(self, threshold_id: str, updates: Dict) -> Optional[CapacityThreshold]:
        """Update a threshold."""
        threshold = self._thresholds.get(threshold_id)
        if not threshold:
            return None

        for key, value in updates.items():
            if hasattr(threshold, key):
                if key == "resource_type" and isinstance(value, str):
                    value = ResourceType(value)
                setattr(threshold, key, value)

        return threshold

    def delete_threshold(self, threshold_id: str) -> bool:
        """Delete a threshold."""
        if threshold_id in self._thresholds:
            del self._thresholds[threshold_id]
            return True
        return False

    def get_thresholds(self) -> List[CapacityThreshold]:
        """Get all thresholds."""
        return list(self._thresholds.values())

    # ==================== Forecasting ====================

    def generate_forecast(self, metric_key: str) -> Optional[CapacityForecast]:
        """Generate a capacity forecast for a metric."""
        metric = self._metrics.get(metric_key)
        if not metric or len(metric.history) < 3:
            return None

        forecast = CapacityForecast(
            resource_type=metric.resource_type,
            device_id=metric.device_id,
            device_name=metric.device_name,
            resource_name=metric.resource_name,
            current_utilization=metric.utilization_pct,
            current_value=metric.current_value,
            max_capacity=metric.max_capacity,
            unit=metric.unit
        )

        # Calculate trend using linear regression
        values = [v for _, v in metric.history]
        n = len(values)
        x = list(range(n))

        # Simple linear regression
        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator > 0:
            slope = numerator / denominator
            # Convert to daily rate (assuming hourly samples)
            forecast.trend_slope = slope * 24
        else:
            forecast.trend_slope = 0

        # Calculate R-squared (confidence)
        if len(values) > 1:
            try:
                ss_tot = sum((v - y_mean) ** 2 for v in values)
                intercept = y_mean - slope * x_mean
                ss_res = sum((values[i] - (slope * x[i] + intercept)) ** 2 for i in range(n))
                if ss_tot > 0:
                    forecast.trend_confidence = max(0, 1 - (ss_res / ss_tot))
            except:
                forecast.trend_confidence = 0

        # Determine trend direction
        if forecast.trend_slope > 1:
            forecast.trend_direction = TrendDirection.RAPIDLY_INCREASING
        elif forecast.trend_slope > 0.1:
            forecast.trend_direction = TrendDirection.INCREASING
        elif forecast.trend_slope < -0.1:
            forecast.trend_direction = TrendDirection.DECREASING
        else:
            forecast.trend_direction = TrendDirection.STABLE

        # Predict future values
        current = metric.current_value
        forecast.predicted_7d = min(current + forecast.trend_slope * 7, metric.max_capacity)
        forecast.predicted_30d = min(current + forecast.trend_slope * 30, metric.max_capacity)
        forecast.predicted_90d = min(current + forecast.trend_slope * 90, metric.max_capacity)

        # Calculate days to thresholds
        if forecast.trend_slope > 0:
            warning_value = metric.max_capacity * (metric.warning_threshold / 100)
            critical_value = metric.max_capacity * (metric.critical_threshold / 100)

            if current < warning_value:
                forecast.days_to_warning = int((warning_value - current) / forecast.trend_slope)
            if current < critical_value:
                forecast.days_to_critical = int((critical_value - current) / forecast.trend_slope)
            if current < metric.max_capacity:
                forecast.days_to_exhaustion = int((metric.max_capacity - current) / forecast.trend_slope)

        self._forecasts[metric_key] = forecast
        return forecast

    def generate_all_forecasts(self) -> List[CapacityForecast]:
        """Generate forecasts for all metrics."""
        forecasts = []
        for key in self._metrics.keys():
            forecast = self.generate_forecast(key)
            if forecast:
                forecasts.append(forecast)
        return forecasts

    def get_forecasts(self) -> List[CapacityForecast]:
        """Get all forecasts."""
        return list(self._forecasts.values())

    def get_urgent_forecasts(self, days: int = 30) -> List[CapacityForecast]:
        """Get forecasts that will hit thresholds within specified days."""
        urgent = []
        for forecast in self._forecasts.values():
            if (forecast.days_to_critical and forecast.days_to_critical <= days) or \
               (forecast.days_to_exhaustion and forecast.days_to_exhaustion <= days):
                urgent.append(forecast)
        return sorted(urgent, key=lambda f: f.days_to_critical or f.days_to_exhaustion or 999)

    # ==================== Recommendations ====================

    def generate_recommendations(self) -> List[CapacityRecommendation]:
        """Generate capacity planning recommendations."""
        recommendations = []

        # Check critical metrics
        for metric in self.get_critical_metrics():
            if metric.utilization_level == UtilizationLevel.EXHAUSTED:
                rec = CapacityRecommendation(
                    priority="critical",
                    category="upgrade",
                    device_id=metric.device_id,
                    device_name=metric.device_name,
                    resource_type=metric.resource_type,
                    resource_name=metric.resource_name,
                    title=f"URGENT: {metric.resource_name} Exhausted",
                    description=f"{metric.resource_type.value.title()} on {metric.device_name} is at {metric.utilization_pct:.1f}% utilization",
                    impact="Service degradation or outage imminent",
                    action=f"Immediately upgrade {metric.resource_type.value} capacity or redistribute load",
                    urgency_days=1
                )
                recommendations.append(rec)
            else:  # Critical
                rec = CapacityRecommendation(
                    priority="high",
                    category="upgrade",
                    device_id=metric.device_id,
                    device_name=metric.device_name,
                    resource_type=metric.resource_type,
                    resource_name=metric.resource_name,
                    title=f"Critical: {metric.resource_name} Near Capacity",
                    description=f"{metric.resource_type.value.title()} on {metric.device_name} is at {metric.utilization_pct:.1f}% utilization",
                    impact="May impact performance under load spikes",
                    action=f"Plan {metric.resource_type.value} capacity upgrade within 7 days",
                    urgency_days=7
                )
                recommendations.append(rec)

        # Check forecasts
        for forecast in self.get_urgent_forecasts(30):
            days = forecast.days_to_critical or forecast.days_to_exhaustion or 30
            if days <= 7:
                priority = "high"
                urgency = days
            elif days <= 14:
                priority = "medium"
                urgency = days
            else:
                priority = "low"
                urgency = days

            rec = CapacityRecommendation(
                priority=priority,
                category="upgrade",
                device_id=forecast.device_id,
                device_name=forecast.device_name,
                resource_type=forecast.resource_type,
                resource_name=forecast.resource_name,
                title=f"Forecast: {forecast.resource_name} Growth",
                description=f"{forecast.resource_type.value.title()} trending {forecast.trend_direction.value} at {forecast.trend_slope:.2f}/day",
                impact=f"Expected to reach critical level in {days} days",
                action=f"Plan capacity increase before {days} days",
                urgency_days=urgency
            )
            recommendations.append(rec)

        # Check for underutilized resources
        idle_metrics = [m for m in self._metrics.values()
                       if m.utilization_level == UtilizationLevel.IDLE]
        for metric in idle_metrics:
            rec = CapacityRecommendation(
                priority="low",
                category="optimize",
                device_id=metric.device_id,
                device_name=metric.device_name,
                resource_type=metric.resource_type,
                resource_name=metric.resource_name,
                title=f"Underutilized: {metric.resource_name}",
                description=f"{metric.resource_type.value.title()} on {metric.device_name} is only at {metric.utilization_pct:.1f}%",
                impact="Potential cost savings opportunity",
                action="Consider consolidating workloads or right-sizing resources",
                urgency_days=90
            )
            recommendations.append(rec)

        # Store and return
        for rec in recommendations:
            self._recommendations[rec.id] = rec

        return sorted(recommendations, key=lambda r: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(r.priority, 4),
            r.urgency_days
        ))

    def get_recommendations(self, status: Optional[str] = None) -> List[CapacityRecommendation]:
        """Get all recommendations with optional status filter."""
        recs = list(self._recommendations.values())
        if status:
            recs = [r for r in recs if r.status == status]
        return recs

    def update_recommendation(self, rec_id: str, status: str) -> Optional[CapacityRecommendation]:
        """Update recommendation status."""
        rec = self._recommendations.get(rec_id)
        if rec:
            rec.status = status
        return rec

    # ==================== Statistics ====================

    def get_statistics(self) -> Dict[str, Any]:
        """Get capacity planning statistics."""
        metrics = list(self._metrics.values())
        forecasts = list(self._forecasts.values())

        # Count by utilization level
        by_level = {}
        for level in UtilizationLevel:
            count = len([m for m in metrics if m.utilization_level == level])
            if count > 0:
                by_level[level.value] = count

        # Count by resource type
        by_type = {}
        for rtype in ResourceType:
            count = len([m for m in metrics if m.resource_type == rtype])
            if count > 0:
                by_type[rtype.value] = count

        # Count urgent
        urgent_forecasts = len(self.get_urgent_forecasts(30))
        critical_metrics = len(self.get_critical_metrics())

        # Average utilization
        avg_util = statistics.mean([m.utilization_pct for m in metrics]) if metrics else 0

        return {
            "total_metrics": len(metrics),
            "total_forecasts": len(forecasts),
            "total_recommendations": len(self._recommendations),
            "pending_recommendations": len([r for r in self._recommendations.values() if r.status == "pending"]),
            "by_utilization_level": by_level,
            "by_resource_type": by_type,
            "critical_metrics": critical_metrics,
            "urgent_forecasts_30d": urgent_forecasts,
            "average_utilization": round(avg_util, 1),
            "thresholds_configured": len(self._thresholds)
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get a high-level capacity summary."""
        metrics = list(self._metrics.values())

        # Top 5 most utilized
        top_utilized = sorted(metrics, key=lambda m: m.utilization_pct, reverse=True)[:5]

        # Resources by status
        status_counts = {
            "healthy": len([m for m in metrics if m.utilization_pct < 70]),
            "warning": len([m for m in metrics if 70 <= m.utilization_pct < 90]),
            "critical": len([m for m in metrics if m.utilization_pct >= 90])
        }

        # Upcoming capacity issues
        urgent = self.get_urgent_forecasts(30)

        return {
            "overall_health": "critical" if status_counts["critical"] > 0 else
                             ("warning" if status_counts["warning"] > 0 else "healthy"),
            "status_counts": status_counts,
            "top_utilized": [m.to_dict() for m in top_utilized],
            "upcoming_issues": len(urgent),
            "days_to_first_issue": urgent[0].days_to_critical if urgent else None
        }


# Singleton instance
_capacity_planner: Optional[CapacityPlanner] = None


def get_capacity_planner() -> CapacityPlanner:
    """Get the singleton capacity planner instance."""
    global _capacity_planner
    if _capacity_planner is None:
        _capacity_planner = CapacityPlanner()
    return _capacity_planner
