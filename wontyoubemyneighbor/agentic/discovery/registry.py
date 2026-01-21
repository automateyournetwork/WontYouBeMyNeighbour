"""
Service Registry

Provides:
- Service registration
- Service discovery
- Instance management
- Service metadata
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum


class ServiceStatus(Enum):
    """Service status"""
    REGISTERED = "registered"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"
    DEREGISTERED = "deregistered"


class ServiceType(Enum):
    """Service types"""
    API = "api"
    GRPC = "grpc"
    WEB = "web"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    WORKER = "worker"
    AGENT = "agent"
    MONITOR = "monitor"
    GATEWAY = "gateway"
    CUSTOM = "custom"


@dataclass
class ServiceInstance:
    """Service instance"""

    id: str
    service_name: str
    host: str
    port: int
    status: ServiceStatus = ServiceStatus.REGISTERED

    # Network
    protocol: str = "http"
    path: str = ""
    weight: int = 100

    # Metadata
    version: str = "1.0.0"
    region: str = ""
    zone: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Health
    health_check_url: Optional[str] = None
    last_health_check: Optional[datetime] = None
    consecutive_failures: int = 0

    # Lifecycle
    registered_at: datetime = field(default_factory=datetime.now)
    last_seen_at: datetime = field(default_factory=datetime.now)
    deregistered_at: Optional[datetime] = None

    @property
    def address(self) -> str:
        """Get full address"""
        return f"{self.protocol}://{self.host}:{self.port}{self.path}"

    @property
    def endpoint(self) -> str:
        """Get host:port endpoint"""
        return f"{self.host}:{self.port}"

    def mark_healthy(self) -> None:
        """Mark instance as healthy"""
        self.status = ServiceStatus.HEALTHY
        self.consecutive_failures = 0
        self.last_health_check = datetime.now()
        self.last_seen_at = datetime.now()

    def mark_unhealthy(self) -> None:
        """Mark instance as unhealthy"""
        self.consecutive_failures += 1
        self.last_health_check = datetime.now()
        if self.consecutive_failures >= 3:
            self.status = ServiceStatus.UNHEALTHY

    def heartbeat(self) -> None:
        """Record heartbeat"""
        self.last_seen_at = datetime.now()

    def is_available(self) -> bool:
        """Check if instance is available"""
        return self.status in (ServiceStatus.REGISTERED, ServiceStatus.HEALTHY)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "service_name": self.service_name,
            "host": self.host,
            "port": self.port,
            "status": self.status.value,
            "protocol": self.protocol,
            "path": self.path,
            "weight": self.weight,
            "address": self.address,
            "endpoint": self.endpoint,
            "version": self.version,
            "region": self.region,
            "zone": self.zone,
            "tags": self.tags,
            "metadata": self.metadata,
            "health_check_url": self.health_check_url,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "consecutive_failures": self.consecutive_failures,
            "registered_at": self.registered_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "deregistered_at": self.deregistered_at.isoformat() if self.deregistered_at else None,
            "is_available": self.is_available()
        }


@dataclass
class Service:
    """Service definition"""

    name: str
    service_type: ServiceType = ServiceType.API
    description: str = ""

    # Instances
    instances: Dict[str, ServiceInstance] = field(default_factory=dict)

    # Discovery settings
    ttl_seconds: int = 30
    deregister_critical_after: int = 300

    # Metadata
    version: str = "1.0.0"
    owner: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Lifecycle
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def get_healthy_instances(self) -> List[ServiceInstance]:
        """Get healthy instances"""
        return [i for i in self.instances.values() if i.status == ServiceStatus.HEALTHY]

    def get_available_instances(self) -> List[ServiceInstance]:
        """Get available instances"""
        return [i for i in self.instances.values() if i.is_available()]

    def get_instance_count(self) -> Dict[str, int]:
        """Get instance count by status"""
        counts = {s.value: 0 for s in ServiceStatus}
        for instance in self.instances.values():
            counts[instance.status.value] += 1
        return counts

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "service_type": self.service_type.value,
            "description": self.description,
            "instance_count": len(self.instances),
            "healthy_count": len(self.get_healthy_instances()),
            "available_count": len(self.get_available_instances()),
            "instances": [i.to_dict() for i in self.instances.values()],
            "ttl_seconds": self.ttl_seconds,
            "deregister_critical_after": self.deregister_critical_after,
            "version": self.version,
            "owner": self.owner,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class ServiceRegistry:
    """Service registry for service discovery"""

    def __init__(self):
        self.services: Dict[str, Service] = {}
        self._listeners: List[Callable] = []
        self._init_builtin_services()

    def _init_builtin_services(self) -> None:
        """Initialize built-in services"""
        # API Gateway
        self.register_service(
            name="api-gateway",
            service_type=ServiceType.GATEWAY,
            description="Main API gateway",
            tags=["core", "gateway"]
        )

        # Agent Manager
        self.register_service(
            name="agent-manager",
            service_type=ServiceType.AGENT,
            description="Network agent manager",
            tags=["core", "agents"]
        )

        # Monitoring Service
        self.register_service(
            name="monitoring",
            service_type=ServiceType.MONITOR,
            description="Monitoring and metrics service",
            tags=["core", "monitoring"]
        )

    def register_service(
        self,
        name: str,
        service_type: ServiceType = ServiceType.API,
        description: str = "",
        ttl_seconds: int = 30,
        version: str = "1.0.0",
        owner: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Service:
        """Register a service"""
        if name in self.services:
            service = self.services[name]
            service.updated_at = datetime.now()
            return service

        service = Service(
            name=name,
            service_type=service_type,
            description=description,
            ttl_seconds=ttl_seconds,
            version=version,
            owner=owner,
            tags=tags or [],
            metadata=metadata or {}
        )

        self.services[name] = service
        self._notify("service_registered", service)
        return service

    def deregister_service(self, name: str) -> bool:
        """Deregister a service"""
        if name in self.services:
            service = self.services[name]
            del self.services[name]
            self._notify("service_deregistered", service)
            return True
        return False

    def register_instance(
        self,
        service_name: str,
        host: str,
        port: int,
        protocol: str = "http",
        path: str = "",
        weight: int = 100,
        version: str = "1.0.0",
        region: str = "",
        zone: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        health_check_url: Optional[str] = None
    ) -> ServiceInstance:
        """Register a service instance"""
        # Ensure service exists
        if service_name not in self.services:
            self.register_service(service_name)

        service = self.services[service_name]
        instance_id = f"{service_name}_{uuid.uuid4().hex[:8]}"

        instance = ServiceInstance(
            id=instance_id,
            service_name=service_name,
            host=host,
            port=port,
            protocol=protocol,
            path=path,
            weight=weight,
            version=version,
            region=region,
            zone=zone,
            tags=tags or [],
            metadata=metadata or {},
            health_check_url=health_check_url or f"{protocol}://{host}:{port}/health"
        )

        service.instances[instance_id] = instance
        service.updated_at = datetime.now()

        self._notify("instance_registered", instance)
        return instance

    def deregister_instance(
        self,
        service_name: str,
        instance_id: str
    ) -> bool:
        """Deregister a service instance"""
        service = self.services.get(service_name)
        if not service:
            return False

        instance = service.instances.get(instance_id)
        if not instance:
            return False

        instance.status = ServiceStatus.DEREGISTERED
        instance.deregistered_at = datetime.now()
        del service.instances[instance_id]
        service.updated_at = datetime.now()

        self._notify("instance_deregistered", instance)
        return True

    def heartbeat(
        self,
        service_name: str,
        instance_id: str
    ) -> bool:
        """Record instance heartbeat"""
        service = self.services.get(service_name)
        if not service:
            return False

        instance = service.instances.get(instance_id)
        if not instance:
            return False

        instance.heartbeat()
        return True

    def get_service(self, name: str) -> Optional[Service]:
        """Get service by name"""
        return self.services.get(name)

    def get_instance(
        self,
        service_name: str,
        instance_id: str
    ) -> Optional[ServiceInstance]:
        """Get instance by ID"""
        service = self.services.get(service_name)
        if not service:
            return None
        return service.instances.get(instance_id)

    def discover(
        self,
        service_name: str,
        healthy_only: bool = True,
        tags: Optional[List[str]] = None,
        region: Optional[str] = None,
        zone: Optional[str] = None
    ) -> List[ServiceInstance]:
        """Discover service instances"""
        service = self.services.get(service_name)
        if not service:
            return []

        if healthy_only:
            instances = service.get_healthy_instances()
        else:
            instances = list(service.instances.values())

        # Filter by tags
        if tags:
            instances = [i for i in instances if any(t in i.tags for t in tags)]

        # Filter by region
        if region:
            instances = [i for i in instances if i.region == region]

        # Filter by zone
        if zone:
            instances = [i for i in instances if i.zone == zone]

        return instances

    def get_services(
        self,
        service_type: Optional[ServiceType] = None,
        tags: Optional[List[str]] = None
    ) -> List[Service]:
        """Get services with filtering"""
        services = list(self.services.values())

        if service_type:
            services = [s for s in services if s.service_type == service_type]

        if tags:
            services = [s for s in services if any(t in s.tags for t in tags)]

        return services

    def cleanup_stale_instances(self, max_age_seconds: int = 60) -> int:
        """Cleanup stale instances"""
        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
        removed = 0

        for service in self.services.values():
            stale = [
                inst_id for inst_id, inst in service.instances.items()
                if inst.last_seen_at < cutoff
            ]
            for inst_id in stale:
                del service.instances[inst_id]
                removed += 1

        return removed

    def add_listener(self, listener: Callable) -> None:
        """Add registry event listener"""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable) -> None:
        """Remove registry event listener"""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify(self, event_type: str, data: Any) -> None:
        """Notify listeners of registry event"""
        for listener in self._listeners:
            try:
                listener(event_type, data)
            except Exception:
                pass

    def get_statistics(self) -> dict:
        """Get registry statistics"""
        total_instances = sum(len(s.instances) for s in self.services.values())
        healthy_instances = sum(len(s.get_healthy_instances()) for s in self.services.values())

        by_type = {}
        for service in self.services.values():
            stype = service.service_type.value
            if stype not in by_type:
                by_type[stype] = 0
            by_type[stype] += 1

        return {
            "total_services": len(self.services),
            "total_instances": total_instances,
            "healthy_instances": healthy_instances,
            "unhealthy_instances": total_instances - healthy_instances,
            "services_by_type": by_type
        }


# Global registry instance
_service_registry: Optional[ServiceRegistry] = None


def get_service_registry() -> ServiceRegistry:
    """Get or create the global service registry"""
    global _service_registry
    if _service_registry is None:
        _service_registry = ServiceRegistry()
    return _service_registry
