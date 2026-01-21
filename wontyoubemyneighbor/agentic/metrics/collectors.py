"""
Metric Collectors

Provides:
- Metric definitions
- Collection configuration
- Built-in metric types
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum
import random


class MetricType(Enum):
    """Types of metrics"""
    COUNTER = "counter"  # Monotonically increasing
    GAUGE = "gauge"  # Point-in-time value
    HISTOGRAM = "histogram"  # Distribution of values
    SUMMARY = "summary"  # Statistical summary
    RATE = "rate"  # Rate of change
    PERCENTAGE = "percentage"  # Percentage value
    TIMER = "timer"  # Duration measurement


class MetricUnit(Enum):
    """Units of measurement"""
    # None
    NONE = ""
    COUNT = "count"
    
    # Time
    NANOSECONDS = "ns"
    MICROSECONDS = "us"
    MILLISECONDS = "ms"
    SECONDS = "s"
    MINUTES = "m"
    HOURS = "h"
    
    # Data
    BYTES = "B"
    KILOBYTES = "KB"
    MEGABYTES = "MB"
    GIGABYTES = "GB"
    TERABYTES = "TB"
    
    # Rate
    BITS_PER_SECOND = "bps"
    KILOBITS_PER_SECOND = "Kbps"
    MEGABITS_PER_SECOND = "Mbps"
    GIGABITS_PER_SECOND = "Gbps"
    PACKETS_PER_SECOND = "pps"
    REQUESTS_PER_SECOND = "rps"
    
    # Percentage
    PERCENT = "%"
    
    # Network
    HOPS = "hops"
    
    # Temperature
    CELSIUS = "C"
    FAHRENHEIT = "F"
    
    # Power
    WATTS = "W"
    KILOWATTS = "kW"


class MetricCategory(Enum):
    """Metric categories"""
    SYSTEM = "system"  # CPU, memory, disk
    NETWORK = "network"  # Interfaces, traffic
    PROTOCOL = "protocol"  # BGP, OSPF, IS-IS
    APPLICATION = "application"  # App-specific
    CUSTOM = "custom"  # User-defined


@dataclass
class MetricConfig:
    """Metric configuration"""
    
    collection_interval_seconds: int = 60
    retention_hours: int = 24
    max_data_points: int = 10000
    enable_alerts: bool = True
    alert_threshold_high: Optional[float] = None
    alert_threshold_low: Optional[float] = None
    alert_threshold_critical: Optional[float] = None
    enable_aggregation: bool = True
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "collection_interval_seconds": self.collection_interval_seconds,
            "retention_hours": self.retention_hours,
            "max_data_points": self.max_data_points,
            "enable_alerts": self.enable_alerts,
            "alert_threshold_high": self.alert_threshold_high,
            "alert_threshold_low": self.alert_threshold_low,
            "alert_threshold_critical": self.alert_threshold_critical,
            "enable_aggregation": self.enable_aggregation,
            "tags": self.tags,
            "extra": self.extra
        }


@dataclass
class Metric:
    """Metric definition"""
    
    id: str
    name: str
    metric_type: MetricType
    unit: MetricUnit
    category: MetricCategory
    description: str = ""
    config: MetricConfig = field(default_factory=MetricConfig)
    labels: Dict[str, str] = field(default_factory=dict)  # Static labels
    enabled: bool = True
    collector_func: Optional[str] = None  # Name of collector function
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Statistics
    collection_count: int = 0
    last_collected_at: Optional[datetime] = None
    last_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    avg_value: float = 0.0
    
    def record_value(self, value: float) -> None:
        """Record a collected value"""
        self.collection_count += 1
        self.last_collected_at = datetime.now()
        self.last_value = value
        
        if self.min_value is None or value < self.min_value:
            self.min_value = value
        if self.max_value is None or value > self.max_value:
            self.max_value = value
        
        # Running average
        if self.collection_count == 1:
            self.avg_value = value
        else:
            self.avg_value = (self.avg_value * 0.9) + (value * 0.1)
        
        self.updated_at = datetime.now()
    
    def check_alert(self, value: float) -> Optional[str]:
        """Check if value triggers an alert"""
        if not self.config.enable_alerts:
            return None
        
        if self.config.alert_threshold_critical is not None:
            if value >= self.config.alert_threshold_critical:
                return "critical"
        
        if self.config.alert_threshold_high is not None:
            if value >= self.config.alert_threshold_high:
                return "high"
        
        if self.config.alert_threshold_low is not None:
            if value <= self.config.alert_threshold_low:
                return "low"
        
        return None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "metric_type": self.metric_type.value,
            "unit": self.unit.value,
            "category": self.category.value,
            "description": self.description,
            "config": self.config.to_dict(),
            "labels": self.labels,
            "enabled": self.enabled,
            "collector_func": self.collector_func,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "collection_count": self.collection_count,
            "last_collected_at": self.last_collected_at.isoformat() if self.last_collected_at else None,
            "last_value": self.last_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "avg_value": self.avg_value
        }


class MetricCollector:
    """Manages metric collection"""
    
    def __init__(self):
        self.metrics: Dict[str, Metric] = {}
        self._collectors: Dict[str, Callable] = {}
        self._init_builtin_collectors()
        self._init_builtin_metrics()
    
    def _init_builtin_collectors(self) -> None:
        """Initialize built-in collector functions"""
        
        def collect_cpu_percent() -> float:
            """Collect CPU percentage"""
            return random.uniform(5, 95)
        
        def collect_memory_percent() -> float:
            """Collect memory percentage"""
            return random.uniform(20, 80)
        
        def collect_disk_percent() -> float:
            """Collect disk usage percentage"""
            return random.uniform(30, 70)
        
        def collect_network_in_bytes() -> float:
            """Collect network bytes in"""
            return random.uniform(1000000, 100000000)
        
        def collect_network_out_bytes() -> float:
            """Collect network bytes out"""
            return random.uniform(500000, 50000000)
        
        def collect_interface_up() -> float:
            """Collect interface up status"""
            return 1.0 if random.random() > 0.1 else 0.0
        
        def collect_bgp_prefixes() -> float:
            """Collect BGP prefix count"""
            return random.uniform(100, 10000)
        
        def collect_ospf_neighbors() -> float:
            """Collect OSPF neighbor count"""
            return random.randint(1, 10)
        
        def collect_latency_ms() -> float:
            """Collect latency in ms"""
            return random.uniform(1, 100)
        
        def collect_packet_loss() -> float:
            """Collect packet loss percentage"""
            return random.uniform(0, 5)
        
        def collect_queue_depth() -> float:
            """Collect queue depth"""
            return random.randint(0, 100)
        
        def collect_error_count() -> float:
            """Collect error count"""
            return random.randint(0, 10)
        
        self._collectors = {
            "cpu_percent": collect_cpu_percent,
            "memory_percent": collect_memory_percent,
            "disk_percent": collect_disk_percent,
            "network_in_bytes": collect_network_in_bytes,
            "network_out_bytes": collect_network_out_bytes,
            "interface_up": collect_interface_up,
            "bgp_prefixes": collect_bgp_prefixes,
            "ospf_neighbors": collect_ospf_neighbors,
            "latency_ms": collect_latency_ms,
            "packet_loss": collect_packet_loss,
            "queue_depth": collect_queue_depth,
            "error_count": collect_error_count
        }
    
    def _init_builtin_metrics(self) -> None:
        """Initialize built-in metrics"""
        
        # System metrics
        self.create_metric(
            name="cpu_percent",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.PERCENT,
            category=MetricCategory.SYSTEM,
            description="CPU utilization percentage",
            collector_func="cpu_percent",
            config=MetricConfig(
                alert_threshold_high=80,
                alert_threshold_critical=95,
                tags=["system", "cpu"]
            )
        )
        
        self.create_metric(
            name="memory_percent",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.PERCENT,
            category=MetricCategory.SYSTEM,
            description="Memory utilization percentage",
            collector_func="memory_percent",
            config=MetricConfig(
                alert_threshold_high=85,
                alert_threshold_critical=95,
                tags=["system", "memory"]
            )
        )
        
        self.create_metric(
            name="disk_percent",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.PERCENT,
            category=MetricCategory.SYSTEM,
            description="Disk utilization percentage",
            collector_func="disk_percent",
            config=MetricConfig(
                alert_threshold_high=80,
                alert_threshold_critical=90,
                tags=["system", "disk"]
            )
        )
        
        # Network metrics
        self.create_metric(
            name="network_in_bytes",
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.BYTES,
            category=MetricCategory.NETWORK,
            description="Network bytes received",
            collector_func="network_in_bytes",
            config=MetricConfig(tags=["network", "traffic"])
        )
        
        self.create_metric(
            name="network_out_bytes",
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.BYTES,
            category=MetricCategory.NETWORK,
            description="Network bytes transmitted",
            collector_func="network_out_bytes",
            config=MetricConfig(tags=["network", "traffic"])
        )
        
        self.create_metric(
            name="interface_up",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.COUNT,
            category=MetricCategory.NETWORK,
            description="Interface up status (1=up, 0=down)",
            collector_func="interface_up",
            config=MetricConfig(
                alert_threshold_low=0.5,
                tags=["network", "interface"]
            )
        )
        
        self.create_metric(
            name="latency_ms",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.MILLISECONDS,
            category=MetricCategory.NETWORK,
            description="Network latency",
            collector_func="latency_ms",
            config=MetricConfig(
                alert_threshold_high=50,
                alert_threshold_critical=100,
                tags=["network", "latency"]
            )
        )
        
        self.create_metric(
            name="packet_loss",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.PERCENT,
            category=MetricCategory.NETWORK,
            description="Packet loss percentage",
            collector_func="packet_loss",
            config=MetricConfig(
                alert_threshold_high=1,
                alert_threshold_critical=5,
                tags=["network", "quality"]
            )
        )
        
        # Protocol metrics
        self.create_metric(
            name="bgp_prefixes",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.COUNT,
            category=MetricCategory.PROTOCOL,
            description="BGP received prefixes",
            collector_func="bgp_prefixes",
            config=MetricConfig(tags=["protocol", "bgp"])
        )
        
        self.create_metric(
            name="ospf_neighbors",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.COUNT,
            category=MetricCategory.PROTOCOL,
            description="OSPF neighbor count",
            collector_func="ospf_neighbors",
            config=MetricConfig(
                alert_threshold_low=1,
                tags=["protocol", "ospf"]
            )
        )
        
        # Application metrics
        self.create_metric(
            name="queue_depth",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.COUNT,
            category=MetricCategory.APPLICATION,
            description="Queue depth",
            collector_func="queue_depth",
            config=MetricConfig(
                alert_threshold_high=80,
                tags=["application", "queue"]
            )
        )
        
        self.create_metric(
            name="error_count",
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.COUNT,
            category=MetricCategory.APPLICATION,
            description="Error count",
            collector_func="error_count",
            config=MetricConfig(
                alert_threshold_high=5,
                tags=["application", "errors"]
            )
        )
    
    def register_collector(
        self,
        name: str,
        collector: Callable
    ) -> None:
        """Register a collector function"""
        self._collectors[name] = collector
    
    def get_collector(self, name: str) -> Optional[Callable]:
        """Get collector function by name"""
        return self._collectors.get(name)
    
    def get_collectors(self) -> List[str]:
        """Get all collector names"""
        return list(self._collectors.keys())
    
    def create_metric(
        self,
        name: str,
        metric_type: MetricType,
        unit: MetricUnit,
        category: MetricCategory,
        description: str = "",
        config: Optional[MetricConfig] = None,
        labels: Optional[Dict[str, str]] = None,
        collector_func: Optional[str] = None,
        enabled: bool = True
    ) -> Metric:
        """Create a new metric"""
        metric_id = f"met_{uuid.uuid4().hex[:8]}"
        
        metric = Metric(
            id=metric_id,
            name=name,
            metric_type=metric_type,
            unit=unit,
            category=category,
            description=description,
            config=config or MetricConfig(),
            labels=labels or {},
            collector_func=collector_func,
            enabled=enabled
        )
        
        self.metrics[metric_id] = metric
        return metric
    
    def get_metric(self, metric_id: str) -> Optional[Metric]:
        """Get metric by ID"""
        return self.metrics.get(metric_id)
    
    def get_metric_by_name(self, name: str) -> Optional[Metric]:
        """Get metric by name"""
        for metric in self.metrics.values():
            if metric.name == name:
                return metric
        return None
    
    def update_metric(
        self,
        metric_id: str,
        **kwargs
    ) -> Optional[Metric]:
        """Update metric properties"""
        metric = self.metrics.get(metric_id)
        if not metric:
            return None
        
        for key, value in kwargs.items():
            if hasattr(metric, key):
                setattr(metric, key, value)
        
        metric.updated_at = datetime.now()
        return metric
    
    def delete_metric(self, metric_id: str) -> bool:
        """Delete a metric"""
        if metric_id in self.metrics:
            del self.metrics[metric_id]
            return True
        return False
    
    def enable_metric(self, metric_id: str) -> bool:
        """Enable a metric"""
        metric = self.metrics.get(metric_id)
        if metric:
            metric.enabled = True
            metric.updated_at = datetime.now()
            return True
        return False
    
    def disable_metric(self, metric_id: str) -> bool:
        """Disable a metric"""
        metric = self.metrics.get(metric_id)
        if metric:
            metric.enabled = False
            metric.updated_at = datetime.now()
            return True
        return False
    
    def collect(self, metric_id: str) -> Optional[float]:
        """Collect a single metric value"""
        metric = self.metrics.get(metric_id)
        if not metric or not metric.enabled:
            return None
        
        collector = self._collectors.get(metric.collector_func) if metric.collector_func else None
        if not collector:
            return None
        
        try:
            value = collector()
            metric.record_value(value)
            return value
        except Exception:
            return None
    
    def collect_all(self) -> Dict[str, float]:
        """Collect all enabled metrics"""
        results = {}
        for metric_id, metric in self.metrics.items():
            if metric.enabled:
                value = self.collect(metric_id)
                if value is not None:
                    results[metric_id] = value
        return results
    
    def get_metrics(
        self,
        metric_type: Optional[MetricType] = None,
        category: Optional[MetricCategory] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[Metric]:
        """Get metrics with filtering"""
        metrics = list(self.metrics.values())
        
        if metric_type:
            metrics = [m for m in metrics if m.metric_type == metric_type]
        if category:
            metrics = [m for m in metrics if m.category == category]
        if enabled_only:
            metrics = [m for m in metrics if m.enabled]
        if tag:
            metrics = [m for m in metrics if tag in m.config.tags]
        
        return metrics
    
    def get_statistics(self) -> dict:
        """Get collector statistics"""
        total_collections = 0
        by_type = {}
        by_category = {}
        alerts_triggered = 0
        
        for metric in self.metrics.values():
            total_collections += metric.collection_count
            by_type[metric.metric_type.value] = by_type.get(metric.metric_type.value, 0) + 1
            by_category[metric.category.value] = by_category.get(metric.category.value, 0) + 1
            
            if metric.last_value is not None and metric.check_alert(metric.last_value):
                alerts_triggered += 1
        
        return {
            "total_metrics": len(self.metrics),
            "enabled_metrics": len([m for m in self.metrics.values() if m.enabled]),
            "total_collections": total_collections,
            "alerts_triggered": alerts_triggered,
            "by_type": by_type,
            "by_category": by_category,
            "registered_collectors": len(self._collectors)
        }


# Global metric collector instance
_metric_collector: Optional[MetricCollector] = None


def get_metric_collector() -> MetricCollector:
    """Get or create the global metric collector"""
    global _metric_collector
    if _metric_collector is None:
        _metric_collector = MetricCollector()
    return _metric_collector
