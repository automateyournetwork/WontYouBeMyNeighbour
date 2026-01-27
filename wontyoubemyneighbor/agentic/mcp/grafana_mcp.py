"""
Grafana MCP Client - Dashboard and Visualization Integration

Provides integration with Grafana for visualizing agent metrics.

Features:
- Pre-built dashboard templates for each protocol
- Auto-provisioning of dashboards when agents are created
- Embedded Grafana panels in agent dashboard
- Custom dashboard creation

This MCP works with Prometheus MCP to visualize metrics collected from agents.
"""

import asyncio
import logging
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import time

logger = logging.getLogger("Grafana_MCP")

# Singleton client instance
_grafana_client: Optional["GrafanaClient"] = None


class PanelType(Enum):
    """Grafana panel types"""
    GRAPH = "graph"
    STAT = "stat"
    GAUGE = "gauge"
    TABLE = "table"
    TIMESERIES = "timeseries"
    HEATMAP = "heatmap"
    PIECHART = "piechart"
    TEXT = "text"
    LOG = "logs"


@dataclass
class GrafanaQuery:
    """A Grafana/Prometheus query"""
    ref_id: str
    expr: str  # PromQL expression
    legend_format: str = ""
    interval: str = "15s"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "refId": self.ref_id,
            "expr": self.expr,
            "legendFormat": self.legend_format,
            "interval": self.interval
        }


@dataclass
class GrafanaPanel:
    """A Grafana dashboard panel"""
    id: int
    title: str
    panel_type: PanelType
    queries: List[GrafanaQuery]
    grid_pos: Dict[str, int]  # {"x": 0, "y": 0, "w": 12, "h": 8}
    options: Dict[str, Any] = field(default_factory=dict)
    field_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.panel_type.value,
            "targets": [q.to_dict() for q in self.queries],
            "gridPos": self.grid_pos,
            "options": self.options,
            "fieldConfig": self.field_config
        }


@dataclass
class GrafanaDashboard:
    """A Grafana dashboard"""
    uid: str
    title: str
    tags: List[str] = field(default_factory=list)
    panels: List[GrafanaPanel] = field(default_factory=list)
    time_from: str = "now-1h"
    time_to: str = "now"
    refresh: str = "10s"
    variables: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "title": self.title,
            "tags": self.tags,
            "panels": [p.to_dict() for p in self.panels],
            "time": {"from": self.time_from, "to": self.time_to},
            "refresh": self.refresh,
            "templating": {"list": self.variables},
            "schemaVersion": 38
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class DashboardTemplates:
    """Pre-built dashboard templates for agents"""

    @staticmethod
    def create_agent_overview(agent_id: str, router_id: str) -> GrafanaDashboard:
        """Create an overview dashboard for an agent"""
        dashboard = GrafanaDashboard(
            uid=f"agent-{agent_id}-overview",
            title=f"Agent Overview - {agent_id}",
            tags=["agent", "overview", agent_id]
        )

        panel_id = 1

        # Row 1: Status indicators
        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="Agent Status",
            panel_type=PanelType.STAT,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'agent_up{{agent_id="{agent_id}"}}',
                legend_format="Status"
            )],
            grid_pos={"x": 0, "y": 0, "w": 4, "h": 4},
            options={"colorMode": "background", "graphMode": "none"},
            field_config={"defaults": {"mappings": [
                {"type": "value", "options": {"0": {"text": "DOWN", "color": "red"}}},
                {"type": "value", "options": {"1": {"text": "UP", "color": "green"}}}
            ]}}
        ))
        panel_id += 1

        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="Uptime",
            panel_type=PanelType.STAT,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'agent_uptime_seconds{{agent_id="{agent_id}"}}',
                legend_format="Uptime"
            )],
            grid_pos={"x": 4, "y": 0, "w": 4, "h": 4},
            options={"colorMode": "value"},
            field_config={"defaults": {"unit": "s"}}
        ))
        panel_id += 1

        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="Total Routes",
            panel_type=PanelType.STAT,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'routing_table_size{{agent_id="{agent_id}"}}',
                legend_format="Routes"
            )],
            grid_pos={"x": 8, "y": 0, "w": 4, "h": 4}
        ))
        panel_id += 1

        # Row 2: System metrics
        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="CPU Usage",
            panel_type=PanelType.GAUGE,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'system_cpu_percent{{agent_id="{agent_id}"}}',
                legend_format="CPU %"
            )],
            grid_pos={"x": 0, "y": 4, "w": 4, "h": 6},
            field_config={"defaults": {"unit": "percent", "max": 100, "thresholds": {
                "steps": [
                    {"color": "green", "value": None},
                    {"color": "yellow", "value": 60},
                    {"color": "red", "value": 80}
                ]
            }}}
        ))
        panel_id += 1

        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="Memory Usage",
            panel_type=PanelType.GAUGE,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'system_memory_percent{{agent_id="{agent_id}"}}',
                legend_format="Memory %"
            )],
            grid_pos={"x": 4, "y": 4, "w": 4, "h": 6},
            field_config={"defaults": {"unit": "percent", "max": 100, "thresholds": {
                "steps": [
                    {"color": "green", "value": None},
                    {"color": "yellow", "value": 70},
                    {"color": "red", "value": 85}
                ]
            }}}
        ))
        panel_id += 1

        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="Disk Usage",
            panel_type=PanelType.GAUGE,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'system_disk_percent{{agent_id="{agent_id}"}}',
                legend_format="Disk %"
            )],
            grid_pos={"x": 8, "y": 4, "w": 4, "h": 6},
            field_config={"defaults": {"unit": "percent", "max": 100, "thresholds": {
                "steps": [
                    {"color": "green", "value": None},
                    {"color": "yellow", "value": 70},
                    {"color": "red", "value": 90}
                ]
            }}}
        ))
        panel_id += 1

        # Row 3: Interface traffic
        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="Interface Traffic",
            panel_type=PanelType.TIMESERIES,
            queries=[
                GrafanaQuery(
                    ref_id="A",
                    expr=f'rate(interface_rx_bytes_total{{agent_id="{agent_id}"}}[1m])',
                    legend_format="{{interface}} RX"
                ),
                GrafanaQuery(
                    ref_id="B",
                    expr=f'rate(interface_tx_bytes_total{{agent_id="{agent_id}"}}[1m])',
                    legend_format="{{interface}} TX"
                )
            ],
            grid_pos={"x": 0, "y": 10, "w": 12, "h": 8},
            field_config={"defaults": {"unit": "Bps"}}
        ))

        return dashboard

    @staticmethod
    def create_ospf_dashboard(agent_id: str) -> GrafanaDashboard:
        """Create OSPF-specific dashboard"""
        dashboard = GrafanaDashboard(
            uid=f"agent-{agent_id}-ospf",
            title=f"OSPF Metrics - {agent_id}",
            tags=["agent", "ospf", agent_id]
        )

        panel_id = 1

        # Neighbor stats
        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="OSPF Neighbors",
            panel_type=PanelType.STAT,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'ospf_neighbors_total{{agent_id="{agent_id}"}}',
                legend_format="Total"
            )],
            grid_pos={"x": 0, "y": 0, "w": 4, "h": 4}
        ))
        panel_id += 1

        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="OSPF Neighbors FULL",
            panel_type=PanelType.STAT,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'ospf_neighbors_full{{agent_id="{agent_id}"}}',
                legend_format="Full"
            )],
            grid_pos={"x": 4, "y": 0, "w": 4, "h": 4},
            field_config={"defaults": {"thresholds": {
                "steps": [
                    {"color": "red", "value": None},
                    {"color": "green", "value": 1}
                ]
            }}}
        ))
        panel_id += 1

        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="OSPF Routes",
            panel_type=PanelType.STAT,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'ospf_routes_total{{agent_id="{agent_id}"}}',
                legend_format="Routes"
            )],
            grid_pos={"x": 8, "y": 0, "w": 4, "h": 4}
        ))
        panel_id += 1

        # Neighbor history graph
        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="OSPF Neighbors Over Time",
            panel_type=PanelType.TIMESERIES,
            queries=[
                GrafanaQuery(
                    ref_id="A",
                    expr=f'ospf_neighbors_total{{agent_id="{agent_id}"}}',
                    legend_format="Total Neighbors"
                ),
                GrafanaQuery(
                    ref_id="B",
                    expr=f'ospf_neighbors_full{{agent_id="{agent_id}"}}',
                    legend_format="Full Neighbors"
                )
            ],
            grid_pos={"x": 0, "y": 4, "w": 12, "h": 8}
        ))
        panel_id += 1

        # SPF runs
        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="SPF Calculation Runs",
            panel_type=PanelType.TIMESERIES,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'rate(ospf_spf_runs_total{{agent_id="{agent_id}"}}[5m])',
                legend_format="SPF runs/sec"
            )],
            grid_pos={"x": 0, "y": 12, "w": 12, "h": 6}
        ))

        return dashboard

    @staticmethod
    def create_bgp_dashboard(agent_id: str) -> GrafanaDashboard:
        """Create BGP-specific dashboard"""
        dashboard = GrafanaDashboard(
            uid=f"agent-{agent_id}-bgp",
            title=f"BGP Metrics - {agent_id}",
            tags=["agent", "bgp", agent_id]
        )

        panel_id = 1

        # Peer stats
        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="BGP Peers Total",
            panel_type=PanelType.STAT,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'bgp_peers_total{{agent_id="{agent_id}"}}',
                legend_format="Total"
            )],
            grid_pos={"x": 0, "y": 0, "w": 3, "h": 4}
        ))
        panel_id += 1

        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="BGP Peers Established",
            panel_type=PanelType.STAT,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'bgp_peers_established{{agent_id="{agent_id}"}}',
                legend_format="Established"
            )],
            grid_pos={"x": 3, "y": 0, "w": 3, "h": 4},
            field_config={"defaults": {"thresholds": {
                "steps": [
                    {"color": "red", "value": None},
                    {"color": "green", "value": 1}
                ]
            }}}
        ))
        panel_id += 1

        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="Prefixes Received",
            panel_type=PanelType.STAT,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'bgp_prefixes_received_total{{agent_id="{agent_id}"}}',
                legend_format="Received"
            )],
            grid_pos={"x": 6, "y": 0, "w": 3, "h": 4}
        ))
        panel_id += 1

        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="Loc-RIB Routes",
            panel_type=PanelType.STAT,
            queries=[GrafanaQuery(
                ref_id="A",
                expr=f'bgp_loc_rib_routes{{agent_id="{agent_id}"}}',
                legend_format="Routes"
            )],
            grid_pos={"x": 9, "y": 0, "w": 3, "h": 4}
        ))
        panel_id += 1

        # Peer status over time
        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="BGP Peer Status Over Time",
            panel_type=PanelType.TIMESERIES,
            queries=[
                GrafanaQuery(
                    ref_id="A",
                    expr=f'bgp_peers_total{{agent_id="{agent_id}"}}',
                    legend_format="Total Peers"
                ),
                GrafanaQuery(
                    ref_id="B",
                    expr=f'bgp_peers_established{{agent_id="{agent_id}"}}',
                    legend_format="Established"
                )
            ],
            grid_pos={"x": 0, "y": 4, "w": 12, "h": 8}
        ))
        panel_id += 1

        # Prefix counts over time
        dashboard.panels.append(GrafanaPanel(
            id=panel_id,
            title="BGP Prefixes Over Time",
            panel_type=PanelType.TIMESERIES,
            queries=[
                GrafanaQuery(
                    ref_id="A",
                    expr=f'bgp_prefixes_received_total{{agent_id="{agent_id}"}}',
                    legend_format="Received"
                ),
                GrafanaQuery(
                    ref_id="B",
                    expr=f'bgp_prefixes_advertised_total{{agent_id="{agent_id}"}}',
                    legend_format="Advertised"
                )
            ],
            grid_pos={"x": 0, "y": 12, "w": 12, "h": 6}
        ))

        return dashboard


class GrafanaClient:
    """
    Client for managing Grafana dashboards and panels.

    Can work with:
    - Local dashboard templates (for embedding in agent dashboard)
    - Remote Grafana server (if configured)
    """

    def __init__(self, grafana_url: Optional[str] = None, api_key: Optional[str] = None):
        self.grafana_url = grafana_url
        self.api_key = api_key
        self.dashboards: Dict[str, GrafanaDashboard] = {}
        self.templates = DashboardTemplates()

    async def create_dashboard(self, dashboard: GrafanaDashboard) -> bool:
        """Create or update a dashboard"""
        self.dashboards[dashboard.uid] = dashboard

        # If remote Grafana is configured, push dashboard
        if self.grafana_url:
            return await self._push_dashboard(dashboard)

        return True

    async def _push_dashboard(self, dashboard: GrafanaDashboard) -> bool:
        """Push dashboard to remote Grafana server"""
        try:
            import aiohttp
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            payload = {
                "dashboard": dashboard.to_dict(),
                "overwrite": True
            }

            async with aiohttp.ClientSession() as session:
                url = f"{self.grafana_url}/api/dashboards/db"
                async with session.post(url, headers=headers, json=payload) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Failed to push dashboard to Grafana: {e}")
            return False

    def get_dashboard(self, uid: str) -> Optional[GrafanaDashboard]:
        """Get a dashboard by UID"""
        return self.dashboards.get(uid)

    def list_dashboards(self) -> List[Dict[str, str]]:
        """List all dashboards"""
        return [{"uid": uid, "title": db.title} for uid, db in self.dashboards.items()]

    async def provision_agent_dashboards(self, agent_id: str, router_id: str, protocols: List[str]) -> List[str]:
        """
        Provision all relevant dashboards for an agent.

        Returns list of dashboard UIDs created.
        """
        created = []

        # Always create overview dashboard
        overview = self.templates.create_agent_overview(agent_id, router_id)
        await self.create_dashboard(overview)
        created.append(overview.uid)

        # Create protocol-specific dashboards
        protocols_lower = [p.lower() for p in protocols]

        if "ospf" in protocols_lower or "ospfv3" in protocols_lower:
            ospf_db = self.templates.create_ospf_dashboard(agent_id)
            await self.create_dashboard(ospf_db)
            created.append(ospf_db.uid)

        if any(p in protocols_lower for p in ["bgp", "ibgp", "ebgp"]):
            bgp_db = self.templates.create_bgp_dashboard(agent_id)
            await self.create_dashboard(bgp_db)
            created.append(bgp_db.uid)

        logger.info(f"Provisioned {len(created)} dashboards for agent {agent_id}")
        return created

    def get_dashboard_json(self, uid: str) -> Optional[str]:
        """Get dashboard as JSON string for embedding"""
        dashboard = self.dashboards.get(uid)
        if dashboard:
            return dashboard.to_json()
        return None

    def get_panel_embed_url(self, dashboard_uid: str, panel_id: int) -> Optional[str]:
        """Get URL for embedding a panel in an iframe"""
        if not self.grafana_url:
            return None
        return f"{self.grafana_url}/d-solo/{dashboard_uid}?panelId={panel_id}&theme=dark"


def get_grafana_client(grafana_url: Optional[str] = None, api_key: Optional[str] = None) -> GrafanaClient:
    """Get or create the singleton Grafana client"""
    global _grafana_client
    if _grafana_client is None:
        _grafana_client = GrafanaClient(grafana_url, api_key)
    return _grafana_client


async def init_grafana_for_agent(agent_id: str, router_id: str, protocols: List[str]) -> List[str]:
    """Initialize Grafana dashboards for an agent"""
    client = get_grafana_client()
    return await client.provision_agent_dashboards(agent_id, router_id, protocols)
