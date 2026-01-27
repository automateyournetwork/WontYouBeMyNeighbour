"""
Prometheus MCP Client - Metrics Collection and Query Integration

Provides integration with Prometheus for agent metrics collection and querying.

Metrics exported by agents:
- Interface metrics (bytes in/out, packets, errors, drops)
- Protocol metrics (OSPF neighbors, BGP peers, routes)
- System metrics (CPU, memory, disk)
- Custom application metrics

This MCP allows agents to:
- Export their own metrics
- Query metrics from other agents
- Set up alerts based on metric thresholds
- Analyze trends over time
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from datetime import datetime
import json

logger = logging.getLogger("Prometheus_MCP")

# Singleton client instance
_prometheus_client: Optional["PrometheusClient"] = None


class MetricType(Enum):
    """Prometheus metric types"""
    COUNTER = "counter"      # Only increases (e.g., packets sent)
    GAUGE = "gauge"          # Can increase/decrease (e.g., CPU usage)
    HISTOGRAM = "histogram"  # Distribution of values
    SUMMARY = "summary"      # Percentiles of values


@dataclass
class MetricLabel:
    """Label for a Prometheus metric"""
    name: str
    value: str

    def to_dict(self) -> Dict[str, str]:
        return {self.name: self.value}


@dataclass
class Metric:
    """A single metric with labels and value"""
    name: str
    value: float
    metric_type: MetricType
    labels: Dict[str, str] = field(default_factory=dict)
    help_text: str = ""
    timestamp: Optional[float] = None

    def to_prometheus_format(self) -> str:
        """Format metric in Prometheus exposition format"""
        label_str = ""
        if self.labels:
            label_parts = [f'{k}="{v}"' for k, v in self.labels.items()]
            label_str = "{" + ",".join(label_parts) + "}"

        ts = ""
        if self.timestamp:
            ts = f" {int(self.timestamp * 1000)}"

        return f"{self.name}{label_str} {self.value}{ts}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "type": self.metric_type.value,
            "labels": self.labels,
            "help": self.help_text,
            "timestamp": self.timestamp or time.time()
        }


@dataclass
class MetricFamily:
    """A family of metrics with the same name but different labels"""
    name: str
    help_text: str
    metric_type: MetricType
    metrics: List[Metric] = field(default_factory=list)

    def to_prometheus_format(self) -> str:
        """Format metric family in Prometheus exposition format"""
        lines = []
        lines.append(f"# HELP {self.name} {self.help_text}")
        lines.append(f"# TYPE {self.name} {self.metric_type.value}")
        for metric in self.metrics:
            lines.append(metric.to_prometheus_format())
        return "\n".join(lines)


@dataclass
class QueryResult:
    """Result of a Prometheus query"""
    status: str  # "success" or "error"
    result_type: str  # "vector", "matrix", "scalar", "string"
    result: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "resultType": self.result_type,
            "result": self.result,
            "error": self.error
        }


class PrometheusExporter:
    """
    Exports metrics from an agent in Prometheus format.

    Each agent has its own exporter that collects metrics from:
    - Network interfaces (ip -s link)
    - Protocol state (OSPF, BGP, ISIS)
    - System resources (psutil)
    """

    def __init__(self, agent_id: str, router_id: str):
        self.agent_id = agent_id
        self.router_id = router_id
        self.metrics: Dict[str, MetricFamily] = {}
        self._custom_collectors: List[Callable] = []

    def register_gauge(self, name: str, help_text: str) -> None:
        """Register a gauge metric"""
        if name not in self.metrics:
            self.metrics[name] = MetricFamily(
                name=name,
                help_text=help_text,
                metric_type=MetricType.GAUGE
            )

    def register_counter(self, name: str, help_text: str) -> None:
        """Register a counter metric"""
        if name not in self.metrics:
            self.metrics[name] = MetricFamily(
                name=name,
                help_text=help_text,
                metric_type=MetricType.COUNTER
            )

    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None) -> None:
        """Set a gauge metric value"""
        labels = labels or {}
        labels["agent_id"] = self.agent_id
        labels["router_id"] = self.router_id

        if name not in self.metrics:
            self.register_gauge(name, f"Gauge metric {name}")

        family = self.metrics[name]
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.GAUGE,
            labels=labels,
            timestamp=time.time()
        )

        # Update or add metric
        for i, m in enumerate(family.metrics):
            if m.labels == labels:
                family.metrics[i] = metric
                return
        family.metrics.append(metric)

    def inc_counter(self, name: str, value: float = 1.0, labels: Dict[str, str] = None) -> None:
        """Increment a counter metric"""
        labels = labels or {}
        labels["agent_id"] = self.agent_id
        labels["router_id"] = self.router_id

        if name not in self.metrics:
            self.register_counter(name, f"Counter metric {name}")

        family = self.metrics[name]

        # Find existing metric or create new
        for m in family.metrics:
            if m.labels == labels:
                m.value += value
                m.timestamp = time.time()
                return

        # New counter
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.COUNTER,
            labels=labels,
            timestamp=time.time()
        )
        family.metrics.append(metric)

    def add_collector(self, collector: Callable) -> None:
        """Add a custom metric collector function"""
        self._custom_collectors.append(collector)

    async def collect(self) -> str:
        """Collect all metrics and return in Prometheus format"""
        # Run custom collectors
        for collector in self._custom_collectors:
            try:
                if asyncio.iscoroutinefunction(collector):
                    await collector(self)
                else:
                    collector(self)
            except Exception as e:
                logger.warning(f"Collector failed: {e}")

        # Format all metrics
        output = []
        for family in self.metrics.values():
            output.append(family.to_prometheus_format())

        return "\n\n".join(output)

    def get_metrics_dict(self) -> Dict[str, Any]:
        """Get all metrics as a dictionary"""
        result = {}
        for name, family in self.metrics.items():
            result[name] = {
                "type": family.metric_type.value,
                "help": family.help_text,
                "values": [m.to_dict() for m in family.metrics]
            }
        return result


class PrometheusClient:
    """
    Client for querying Prometheus metrics.

    Can query:
    - Local agent metrics
    - Remote Prometheus server (if configured)
    - Other agents via their exporters
    """

    def __init__(self, prometheus_url: Optional[str] = None):
        self.prometheus_url = prometheus_url
        self.exporters: Dict[str, PrometheusExporter] = {}
        self._metrics_history: Dict[str, List[Dict[str, Any]]] = {}
        self._max_history = 1000  # Keep last 1000 data points per metric

    def create_exporter(self, agent_id: str, router_id: str) -> PrometheusExporter:
        """Create or get an exporter for an agent"""
        if agent_id not in self.exporters:
            self.exporters[agent_id] = PrometheusExporter(agent_id, router_id)
        return self.exporters[agent_id]

    def get_exporter(self, agent_id: str) -> Optional[PrometheusExporter]:
        """Get exporter for an agent"""
        return self.exporters.get(agent_id)

    async def query(self, promql: str, time_range: Optional[str] = None) -> QueryResult:
        """
        Execute a PromQL query.

        For local metrics, implements basic PromQL parsing.
        For remote Prometheus, forwards to API.
        """
        # If remote Prometheus is configured, use it
        if self.prometheus_url:
            return await self._remote_query(promql, time_range)

        # Otherwise, query local metrics
        return self._local_query(promql, time_range)

    def _local_query(self, promql: str, time_range: Optional[str] = None) -> QueryResult:
        """
        Execute a simple PromQL query against local metrics.

        Supports basic queries like:
        - metric_name
        - metric_name{label="value"}
        - up
        """
        results = []

        # Parse the query (simplified - supports metric{labels})
        metric_name = promql.strip()
        label_filter = {}

        if "{" in metric_name:
            parts = metric_name.split("{")
            metric_name = parts[0]
            label_str = parts[1].rstrip("}")
            for pair in label_str.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    label_filter[k.strip()] = v.strip().strip('"')

        # Search all exporters
        for agent_id, exporter in self.exporters.items():
            if metric_name in exporter.metrics:
                family = exporter.metrics[metric_name]
                for metric in family.metrics:
                    # Check label filter
                    match = True
                    for k, v in label_filter.items():
                        if metric.labels.get(k) != v:
                            match = False
                            break

                    if match:
                        results.append({
                            "metric": {
                                "__name__": metric.name,
                                **metric.labels
                            },
                            "value": [metric.timestamp or time.time(), str(metric.value)]
                        })

        return QueryResult(
            status="success",
            result_type="vector",
            result=results
        )

    async def _remote_query(self, promql: str, time_range: Optional[str] = None) -> QueryResult:
        """Query remote Prometheus server"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                params = {"query": promql}
                if time_range:
                    params["time"] = time_range

                url = f"{self.prometheus_url}/api/v1/query"
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return QueryResult(
                            status=data.get("status", "success"),
                            result_type=data.get("data", {}).get("resultType", "vector"),
                            result=data.get("data", {}).get("result", [])
                        )
                    else:
                        return QueryResult(
                            status="error",
                            result_type="",
                            error=f"HTTP {response.status}"
                        )
        except Exception as e:
            return QueryResult(
                status="error",
                result_type="",
                error=str(e)
            )

    def record_metric(self, metric: Metric) -> None:
        """Record a metric value to history"""
        key = f"{metric.name}:{json.dumps(metric.labels, sort_keys=True)}"
        if key not in self._metrics_history:
            self._metrics_history[key] = []

        self._metrics_history[key].append({
            "value": metric.value,
            "timestamp": metric.timestamp or time.time()
        })

        # Trim history
        if len(self._metrics_history[key]) > self._max_history:
            self._metrics_history[key] = self._metrics_history[key][-self._max_history:]

    def get_metric_history(self, metric_name: str, labels: Dict[str, str] = None) -> List[Dict[str, Any]]:
        """Get historical values for a metric"""
        labels = labels or {}
        key = f"{metric_name}:{json.dumps(labels, sort_keys=True)}"
        return self._metrics_history.get(key, [])

    async def get_all_metrics(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Get all current metrics, optionally filtered by agent"""
        result = {}
        exporters = [self.exporters[agent_id]] if agent_id and agent_id in self.exporters else self.exporters.values()

        for exporter in exporters:
            result[exporter.agent_id] = exporter.get_metrics_dict()

        return result


def get_prometheus_client(prometheus_url: Optional[str] = None) -> PrometheusClient:
    """Get or create the singleton Prometheus client"""
    global _prometheus_client
    if _prometheus_client is None:
        _prometheus_client = PrometheusClient(prometheus_url)
    return _prometheus_client


async def init_prometheus_for_agent(agent_id: str, router_id: str) -> PrometheusExporter:
    """Initialize Prometheus metrics for an agent"""
    client = get_prometheus_client()
    exporter = client.create_exporter(agent_id, router_id)

    # Register standard metrics
    exporter.register_gauge("agent_up", "Whether the agent is up (1) or down (0)")
    exporter.register_gauge("agent_uptime_seconds", "Agent uptime in seconds")

    # Interface metrics
    exporter.register_counter("interface_rx_bytes_total", "Total bytes received on interface")
    exporter.register_counter("interface_tx_bytes_total", "Total bytes transmitted on interface")
    exporter.register_counter("interface_rx_packets_total", "Total packets received on interface")
    exporter.register_counter("interface_tx_packets_total", "Total packets transmitted on interface")
    exporter.register_counter("interface_rx_errors_total", "Total receive errors on interface")
    exporter.register_counter("interface_tx_errors_total", "Total transmit errors on interface")
    exporter.register_gauge("interface_up", "Whether interface is up (1) or down (0)")

    # OSPF metrics
    exporter.register_gauge("ospf_neighbors_total", "Total number of OSPF neighbors")
    exporter.register_gauge("ospf_neighbors_full", "Number of OSPF neighbors in FULL state")
    exporter.register_gauge("ospf_lsdb_count", "Number of LSAs in LSDB")
    exporter.register_counter("ospf_spf_runs_total", "Total SPF calculation runs")
    exporter.register_gauge("ospf_routes_total", "Number of OSPF routes")

    # OSPF message counters
    exporter.register_counter("ospf_hello_sent_total", "Total OSPF Hello packets sent")
    exporter.register_counter("ospf_hello_recv_total", "Total OSPF Hello packets received")
    exporter.register_counter("ospf_dbd_sent_total", "Total OSPF DBD packets sent")
    exporter.register_counter("ospf_dbd_recv_total", "Total OSPF DBD packets received")
    exporter.register_counter("ospf_lsr_sent_total", "Total OSPF LSR packets sent")
    exporter.register_counter("ospf_lsr_recv_total", "Total OSPF LSR packets received")
    exporter.register_counter("ospf_lsu_sent_total", "Total OSPF LSU packets sent")
    exporter.register_counter("ospf_lsu_recv_total", "Total OSPF LSU packets received")
    exporter.register_counter("ospf_lsack_sent_total", "Total OSPF LSAck packets sent")
    exporter.register_counter("ospf_lsack_recv_total", "Total OSPF LSAck packets received")

    # BGP metrics
    exporter.register_gauge("bgp_peers_total", "Total number of BGP peers")
    exporter.register_gauge("bgp_peers_established", "Number of BGP peers in Established state")
    exporter.register_gauge("bgp_prefixes_received_total", "Total prefixes received from all peers")
    exporter.register_gauge("bgp_prefixes_advertised_total", "Total prefixes advertised to all peers")
    exporter.register_gauge("bgp_loc_rib_routes", "Number of routes in Loc-RIB")

    # BGP message counters
    exporter.register_counter("bgp_open_sent_total", "Total BGP OPEN messages sent")
    exporter.register_counter("bgp_open_recv_total", "Total BGP OPEN messages received")
    exporter.register_counter("bgp_update_sent_total", "Total BGP UPDATE messages sent")
    exporter.register_counter("bgp_update_recv_total", "Total BGP UPDATE messages received")
    exporter.register_counter("bgp_keepalive_sent_total", "Total BGP KEEPALIVE messages sent")
    exporter.register_counter("bgp_keepalive_recv_total", "Total BGP KEEPALIVE messages received")
    exporter.register_counter("bgp_notification_sent_total", "Total BGP NOTIFICATION messages sent")
    exporter.register_counter("bgp_notification_recv_total", "Total BGP NOTIFICATION messages received")

    # ISIS metrics
    exporter.register_gauge("isis_adjacencies_total", "Total number of IS-IS adjacencies")
    exporter.register_gauge("isis_lsp_count", "Number of LSPs in database")
    exporter.register_gauge("isis_routes_total", "Number of IS-IS routes")

    # System metrics
    exporter.register_gauge("system_cpu_percent", "CPU usage percentage")
    exporter.register_gauge("system_memory_percent", "Memory usage percentage")
    exporter.register_gauge("system_disk_percent", "Disk usage percentage")

    # Routing metrics
    exporter.register_gauge("routing_table_size", "Total number of routes in routing table")

    # Set initial values
    exporter.set_gauge("agent_up", 1.0)

    logger.info(f"Prometheus metrics initialized for agent {agent_id}")
    return exporter


# Standard metric collectors that can be added to exporters

async def collect_system_metrics(exporter: PrometheusExporter) -> None:
    """Collect system metrics (CPU, memory, disk)"""
    try:
        import psutil
        exporter.set_gauge("system_cpu_percent", psutil.cpu_percent(interval=0.1))
        exporter.set_gauge("system_memory_percent", psutil.virtual_memory().percent)
        exporter.set_gauge("system_disk_percent", psutil.disk_usage('/').percent)
        logger.debug(f"Collected system metrics for {exporter.agent_id}")
    except ImportError:
        # Fallback - set placeholder values so UI shows something
        logger.warning("psutil not available, using placeholder system metrics")
        exporter.set_gauge("system_cpu_percent", 0.0)
        exporter.set_gauge("system_memory_percent", 0.0)
        exporter.set_gauge("system_disk_percent", 0.0)
    except Exception as e:
        logger.warning(f"System metrics collection failed: {e}")


async def collect_interface_metrics(exporter: PrometheusExporter) -> None:
    """Collect interface metrics"""
    try:
        import psutil
        net_io = psutil.net_io_counters(pernic=True)
        for iface, stats in net_io.items():
            labels = {"interface": iface}
            exporter.set_gauge("interface_rx_bytes_total", float(stats.bytes_recv), labels)
            exporter.set_gauge("interface_tx_bytes_total", float(stats.bytes_sent), labels)
            exporter.set_gauge("interface_rx_packets_total", float(stats.packets_recv), labels)
            exporter.set_gauge("interface_tx_packets_total", float(stats.packets_sent), labels)
            exporter.set_gauge("interface_rx_errors_total", float(stats.errin), labels)
            exporter.set_gauge("interface_tx_errors_total", float(stats.errout), labels)
        logger.debug(f"Collected interface metrics for {exporter.agent_id}: {len(net_io)} interfaces")
    except ImportError:
        # Fallback - set placeholder values for eth0
        logger.warning("psutil not available, using placeholder interface metrics")
        exporter.set_gauge("interface_rx_bytes_total", 0.0, {"interface": "eth0"})
        exporter.set_gauge("interface_tx_bytes_total", 0.0, {"interface": "eth0"})
    except Exception as e:
        logger.warning(f"Interface metrics collection failed: {e}")
