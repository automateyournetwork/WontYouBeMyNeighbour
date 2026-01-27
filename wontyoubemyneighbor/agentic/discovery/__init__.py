"""
Service Discovery Module

Provides:
- Service registration
- Service discovery
- Health checking
- Load balancing
- IPv6 Neighbor Discovery for ASI overlay
- LLDP (Link Layer Discovery Protocol) for Layer 2 neighbor discovery
- LACP (Link Aggregation Control Protocol) for interface bundling
"""

from .registry import (
    Service,
    ServiceStatus,
    ServiceType,
    ServiceInstance,
    ServiceRegistry,
    get_service_registry
)

from .health import (
    HealthCheck,
    HealthStatus,
    HealthCheckType,
    HealthChecker,
    get_health_checker
)

from .loadbalancer import (
    LoadBalancer,
    LoadBalanceStrategy,
    ServiceEndpoint,
    get_load_balancer
)

from .neighbor_discovery import (
    NeighborDiscoveryProtocol,
    NeighborDiscoveryConfig,
    NeighborEntry,
    NeighborState,
    ICMPv6Type,
    get_neighbor_discovery,
    start_neighbor_discovery,
    stop_neighbor_discovery,
    get_discovered_neighbors
)

from .lldp import (
    LLDPDaemon,
    LLDPConfig,
    LLDPNeighbor,
    LLDPCapability,
    LLDPChassisIDSubtype,
    LLDPPortIDSubtype,
    LLDPManagementAddress,
    get_lldp_daemon,
    start_lldp,
    stop_lldp,
    get_lldp_neighbors,
    get_lldp_statistics
)

from .lacp import (
    LACPManager,
    LACPMode,
    LACPState,
    LACPPortState,
    LoadBalanceAlgorithm,
    LinkAggregationGroup,
    LACPMemberPort,
    LACPPartnerInfo,
    get_lacp_manager,
    start_lacp,
    stop_lacp,
    get_lag_list,
    get_lacp_statistics
)

__all__ = [
    # Registry
    "Service",
    "ServiceStatus",
    "ServiceType",
    "ServiceInstance",
    "ServiceRegistry",
    "get_service_registry",
    # Health
    "HealthCheck",
    "HealthStatus",
    "HealthCheckType",
    "HealthChecker",
    "get_health_checker",
    # Load Balancer
    "LoadBalancer",
    "LoadBalanceStrategy",
    "ServiceEndpoint",
    "get_load_balancer",
    # Neighbor Discovery (IPv6 ASI Overlay)
    "NeighborDiscoveryProtocol",
    "NeighborDiscoveryConfig",
    "NeighborEntry",
    "NeighborState",
    "ICMPv6Type",
    "get_neighbor_discovery",
    "start_neighbor_discovery",
    "stop_neighbor_discovery",
    "get_discovered_neighbors",
    # LLDP (Link Layer Discovery Protocol)
    "LLDPDaemon",
    "LLDPConfig",
    "LLDPNeighbor",
    "LLDPCapability",
    "LLDPChassisIDSubtype",
    "LLDPPortIDSubtype",
    "LLDPManagementAddress",
    "get_lldp_daemon",
    "start_lldp",
    "stop_lldp",
    "get_lldp_neighbors",
    "get_lldp_statistics",
    # LACP (Link Aggregation Control Protocol)
    "LACPManager",
    "LACPMode",
    "LACPState",
    "LACPPortState",
    "LoadBalanceAlgorithm",
    "LinkAggregationGroup",
    "LACPMemberPort",
    "LACPPartnerInfo",
    "get_lacp_manager",
    "start_lacp",
    "stop_lacp",
    "get_lag_list",
    "get_lacp_statistics"
]
