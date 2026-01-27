"""
MCP (Model Context Protocol) Server Integrations

This module provides integrations with various MCP servers:
- RFC: IETF RFC standards reference and lookup
- GAIT: AI session tracking and context management (audit trails)
- Markmap: Network topology visualization (mind maps)
- pyATS: Network testing and validation
- Prometheus: Metrics collection and querying
- Grafana: Dashboard visualization
- SMTP: Email notifications and alerts
- NetBox: DCIM/IPAM network source of truth

Each MCP server provides specialized capabilities that can be
queried by agents to enhance their decision-making.

The 7 Mandatory MCPs for every agent:
1. GAIT MCP - Complete audit trail of all interactions
2. pyATS MCP - Network state testing and validation
3. RFC MCP - Protocol standards knowledge base
4. Markmap MCP - Self-diagramming network visualization
5. Prometheus MCP - Metrics collection and querying
6. Grafana MCP - Dashboard visualization
7. SMTP MCP - Email notifications and alerts

Optional MCPs:
- NetBox MCP - DCIM/IPAM integration with auto-registration
"""

from .rfc_mcp import RFCClient, RFCLookup, RFCSearch, get_rfc_client
from .gait_mcp import (
    GAITClient,
    GAITCommit,
    GAITEventType,
    GAITActor,
    GAITMemoryItem,
    get_gait_client,
    init_gait_for_agent,
)
from .markmap_mcp import (
    MarkmapClient,
    MarkmapGenerator,
    MarkmapOptions,
    MarkmapTheme,
    AgentStateCollector,
    get_markmap_client,
)
from .pyats_mcp import (
    PyATSMCPClient,
    DeviceInfo,
    CommandResult,
    PingResult,
    ConfigResult,
    TestResult,
    CommandType,
    ParseMode,
    get_pyats_client,
    init_pyats_for_agent,
)
from .prometheus_mcp import (
    PrometheusClient,
    PrometheusExporter,
    Metric,
    MetricType,
    MetricFamily,
    QueryResult,
    get_prometheus_client,
    init_prometheus_for_agent,
    collect_system_metrics,
    collect_interface_metrics,
)
from .grafana_mcp import (
    GrafanaClient,
    GrafanaDashboard,
    GrafanaPanel,
    GrafanaQuery,
    PanelType,
    DashboardTemplates,
    get_grafana_client,
    init_grafana_for_agent,
)
from .smtp_mcp import (
    SMTPClient,
    SMTPConfig,
    Email,
    EmailPriority,
    EmailStatus,
    AlertType,
    AlertRule,
    EmailTemplates,
    get_smtp_client,
    start_smtp_client,
    stop_smtp_client,
    get_email_history,
    get_smtp_statistics,
)
from .netbox_mcp import (
    NetBoxClient,
    NetBoxConfig,
    DeviceInfo,
    DeviceStatus,
    get_netbox_client,
    configure_netbox,
    auto_register_agent,
)

__all__ = [
    # RFC MCP
    'RFCClient',
    'RFCLookup',
    'RFCSearch',
    'get_rfc_client',
    # GAIT MCP
    'GAITClient',
    'GAITCommit',
    'GAITEventType',
    'GAITActor',
    'GAITMemoryItem',
    'get_gait_client',
    'init_gait_for_agent',
    # Markmap MCP
    'MarkmapClient',
    'MarkmapGenerator',
    'MarkmapOptions',
    'MarkmapTheme',
    'AgentStateCollector',
    'get_markmap_client',
    # pyATS MCP
    'PyATSMCPClient',
    'DeviceInfo',
    'CommandResult',
    'PingResult',
    'ConfigResult',
    'TestResult',
    'CommandType',
    'ParseMode',
    'get_pyats_client',
    'init_pyats_for_agent',
    # Prometheus MCP
    'PrometheusClient',
    'PrometheusExporter',
    'Metric',
    'MetricType',
    'MetricFamily',
    'QueryResult',
    'get_prometheus_client',
    'init_prometheus_for_agent',
    'collect_system_metrics',
    'collect_interface_metrics',
    # Grafana MCP
    'GrafanaClient',
    'GrafanaDashboard',
    'GrafanaPanel',
    'GrafanaQuery',
    'PanelType',
    'DashboardTemplates',
    'get_grafana_client',
    'init_grafana_for_agent',
    # SMTP MCP
    'SMTPClient',
    'SMTPConfig',
    'Email',
    'EmailPriority',
    'EmailStatus',
    'AlertType',
    'AlertRule',
    'EmailTemplates',
    'get_smtp_client',
    'start_smtp_client',
    'stop_smtp_client',
    'get_email_history',
    'get_smtp_statistics',
    # NetBox MCP
    'NetBoxClient',
    'NetBoxConfig',
    'DeviceInfo',
    'DeviceStatus',
    'get_netbox_client',
    'configure_netbox',
    'auto_register_agent',
]
