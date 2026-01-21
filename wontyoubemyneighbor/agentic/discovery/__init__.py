"""
Service Discovery Module

Provides:
- Service registration
- Service discovery
- Health checking
- Load balancing
- IPv6 Neighbor Discovery for ASI overlay
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
    "get_discovered_neighbors"
]
