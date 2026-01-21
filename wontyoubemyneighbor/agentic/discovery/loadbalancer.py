"""
Load Balancer

Provides:
- Load balancing strategies
- Service endpoint selection
- Weighted routing
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from .registry import ServiceInstance, get_service_registry


class LoadBalanceStrategy(Enum):
    """Load balancing strategies"""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    WEIGHTED = "weighted"
    LEAST_CONNECTIONS = "least_connections"
    IP_HASH = "ip_hash"
    CONSISTENT_HASH = "consistent_hash"
    RESPONSE_TIME = "response_time"


@dataclass
class ServiceEndpoint:
    """Service endpoint for load balancing"""

    instance_id: str
    address: str
    weight: int = 100
    connections: int = 0
    response_time_ms: float = 0.0
    last_used_at: Optional[datetime] = None
    request_count: int = 0
    error_count: int = 0

    def use(self) -> None:
        """Mark endpoint as used"""
        self.last_used_at = datetime.now()
        self.request_count += 1
        self.connections += 1

    def release(self, success: bool = True, response_time_ms: float = 0.0) -> None:
        """Release connection"""
        self.connections = max(0, self.connections - 1)
        if not success:
            self.error_count += 1
        if response_time_ms > 0:
            # Exponential moving average
            self.response_time_ms = (self.response_time_ms * 0.8) + (response_time_ms * 0.2)

    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.request_count == 0:
            return 1.0
        return (self.request_count - self.error_count) / self.request_count

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "address": self.address,
            "weight": self.weight,
            "connections": self.connections,
            "response_time_ms": self.response_time_ms,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "success_rate": self.success_rate
        }


@dataclass
class LoadBalancerConfig:
    """Load balancer configuration"""

    strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN
    health_check_enabled: bool = True
    sticky_sessions: bool = False
    session_timeout_seconds: int = 3600
    max_connections_per_endpoint: int = 100
    circuit_breaker_enabled: bool = True
    circuit_breaker_threshold: float = 0.5
    circuit_breaker_timeout: int = 30

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy.value,
            "health_check_enabled": self.health_check_enabled,
            "sticky_sessions": self.sticky_sessions,
            "session_timeout_seconds": self.session_timeout_seconds,
            "max_connections_per_endpoint": self.max_connections_per_endpoint,
            "circuit_breaker_enabled": self.circuit_breaker_enabled,
            "circuit_breaker_threshold": self.circuit_breaker_threshold,
            "circuit_breaker_timeout": self.circuit_breaker_timeout
        }


class LoadBalancer:
    """Load balancer for service endpoints"""

    def __init__(self, config: Optional[LoadBalancerConfig] = None):
        self.config = config or LoadBalancerConfig()
        self._endpoints: Dict[str, Dict[str, ServiceEndpoint]] = {}  # service -> {instance_id -> endpoint}
        self._round_robin_index: Dict[str, int] = {}  # service -> current index
        self._sessions: Dict[str, str] = {}  # session_id -> instance_id
        self._circuit_breakers: Dict[str, datetime] = {}  # instance_id -> open_until

    def _get_endpoints(self, service_name: str) -> List[ServiceEndpoint]:
        """Get or create endpoints for service"""
        if service_name not in self._endpoints:
            self._refresh_endpoints(service_name)

        return list(self._endpoints.get(service_name, {}).values())

    def _refresh_endpoints(self, service_name: str) -> None:
        """Refresh endpoints from service registry"""
        registry = get_service_registry()
        instances = registry.discover(service_name, healthy_only=self.config.health_check_enabled)

        if service_name not in self._endpoints:
            self._endpoints[service_name] = {}

        current_ids = set(self._endpoints[service_name].keys())
        new_ids = {i.id for i in instances}

        # Remove stale endpoints
        for inst_id in current_ids - new_ids:
            del self._endpoints[service_name][inst_id]

        # Add/update endpoints
        for instance in instances:
            if instance.id not in self._endpoints[service_name]:
                self._endpoints[service_name][instance.id] = ServiceEndpoint(
                    instance_id=instance.id,
                    address=instance.address,
                    weight=instance.weight
                )
            else:
                # Update address and weight
                endpoint = self._endpoints[service_name][instance.id]
                endpoint.address = instance.address
                endpoint.weight = instance.weight

    def _is_circuit_open(self, instance_id: str) -> bool:
        """Check if circuit breaker is open"""
        if not self.config.circuit_breaker_enabled:
            return False

        if instance_id in self._circuit_breakers:
            if datetime.now() < self._circuit_breakers[instance_id]:
                return True
            else:
                del self._circuit_breakers[instance_id]
        return False

    def _check_circuit_breaker(self, endpoint: ServiceEndpoint) -> None:
        """Check and possibly open circuit breaker"""
        if not self.config.circuit_breaker_enabled:
            return

        if endpoint.request_count >= 10 and endpoint.success_rate < self.config.circuit_breaker_threshold:
            from datetime import timedelta
            self._circuit_breakers[endpoint.instance_id] = (
                datetime.now() + timedelta(seconds=self.config.circuit_breaker_timeout)
            )

    def select(
        self,
        service_name: str,
        session_id: Optional[str] = None,
        client_ip: Optional[str] = None
    ) -> Optional[ServiceEndpoint]:
        """Select an endpoint for service"""
        # Check sticky session
        if self.config.sticky_sessions and session_id and session_id in self._sessions:
            instance_id = self._sessions[session_id]
            endpoints = self._get_endpoints(service_name)
            for ep in endpoints:
                if ep.instance_id == instance_id and not self._is_circuit_open(ep.instance_id):
                    ep.use()
                    return ep

        # Get available endpoints
        endpoints = [
            ep for ep in self._get_endpoints(service_name)
            if not self._is_circuit_open(ep.instance_id) and
               ep.connections < self.config.max_connections_per_endpoint
        ]

        if not endpoints:
            return None

        # Select based on strategy
        endpoint = self._select_by_strategy(service_name, endpoints, client_ip)

        if endpoint:
            endpoint.use()

            # Store session
            if self.config.sticky_sessions and session_id:
                self._sessions[session_id] = endpoint.instance_id

        return endpoint

    def _select_by_strategy(
        self,
        service_name: str,
        endpoints: List[ServiceEndpoint],
        client_ip: Optional[str] = None
    ) -> Optional[ServiceEndpoint]:
        """Select endpoint based on strategy"""
        if not endpoints:
            return None

        strategy = self.config.strategy

        if strategy == LoadBalanceStrategy.ROUND_ROBIN:
            if service_name not in self._round_robin_index:
                self._round_robin_index[service_name] = 0

            index = self._round_robin_index[service_name] % len(endpoints)
            self._round_robin_index[service_name] = index + 1
            return endpoints[index]

        elif strategy == LoadBalanceStrategy.RANDOM:
            return random.choice(endpoints)

        elif strategy == LoadBalanceStrategy.WEIGHTED:
            total_weight = sum(ep.weight for ep in endpoints)
            r = random.uniform(0, total_weight)
            cumulative = 0
            for ep in endpoints:
                cumulative += ep.weight
                if r <= cumulative:
                    return ep
            return endpoints[-1]

        elif strategy == LoadBalanceStrategy.LEAST_CONNECTIONS:
            return min(endpoints, key=lambda ep: ep.connections)

        elif strategy == LoadBalanceStrategy.IP_HASH:
            if client_ip:
                hash_val = hash(client_ip)
                return endpoints[hash_val % len(endpoints)]
            return random.choice(endpoints)

        elif strategy == LoadBalanceStrategy.RESPONSE_TIME:
            # Prefer endpoints with lower response time
            return min(endpoints, key=lambda ep: ep.response_time_ms if ep.response_time_ms > 0 else float('inf'))

        return endpoints[0]

    def release(
        self,
        service_name: str,
        instance_id: str,
        success: bool = True,
        response_time_ms: float = 0.0
    ) -> None:
        """Release endpoint after use"""
        endpoints = self._endpoints.get(service_name, {})
        endpoint = endpoints.get(instance_id)

        if endpoint:
            endpoint.release(success, response_time_ms)
            self._check_circuit_breaker(endpoint)

    def refresh(self, service_name: str) -> None:
        """Manually refresh endpoints"""
        self._refresh_endpoints(service_name)

    def set_strategy(self, strategy: LoadBalanceStrategy) -> None:
        """Set load balancing strategy"""
        self.config.strategy = strategy

    def get_endpoints(self, service_name: str) -> List[ServiceEndpoint]:
        """Get all endpoints for service"""
        return self._get_endpoints(service_name)

    def get_circuit_breakers(self) -> Dict[str, datetime]:
        """Get open circuit breakers"""
        return {
            k: v for k, v in self._circuit_breakers.items()
            if datetime.now() < v
        }

    def reset_circuit_breaker(self, instance_id: str) -> bool:
        """Reset circuit breaker for instance"""
        if instance_id in self._circuit_breakers:
            del self._circuit_breakers[instance_id]
            return True
        return False

    def clear_sessions(self) -> int:
        """Clear all sticky sessions"""
        count = len(self._sessions)
        self._sessions.clear()
        return count

    def get_statistics(self) -> dict:
        """Get load balancer statistics"""
        total_endpoints = sum(len(eps) for eps in self._endpoints.values())
        total_connections = sum(
            ep.connections
            for eps in self._endpoints.values()
            for ep in eps.values()
        )
        total_requests = sum(
            ep.request_count
            for eps in self._endpoints.values()
            for ep in eps.values()
        )

        return {
            "strategy": self.config.strategy.value,
            "services": len(self._endpoints),
            "total_endpoints": total_endpoints,
            "active_connections": total_connections,
            "total_requests": total_requests,
            "sticky_sessions": len(self._sessions),
            "open_circuit_breakers": len(self.get_circuit_breakers()),
            "config": self.config.to_dict()
        }


# Global load balancer instance
_load_balancer: Optional[LoadBalancer] = None


def get_load_balancer() -> LoadBalancer:
    """Get or create the global load balancer"""
    global _load_balancer
    if _load_balancer is None:
        _load_balancer = LoadBalancer()
    return _load_balancer
