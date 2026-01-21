"""
Tenant Isolation - Resource isolation and quota management

Provides:
- Tenant context for request scoping
- Resource quota enforcement
- Cross-tenant access control
- Isolation verification
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from contextvars import ContextVar
from collections import defaultdict

logger = logging.getLogger("TenantIsolation")


# Context variable for current tenant
current_tenant: ContextVar[Optional[str]] = ContextVar("current_tenant", default=None)


class ResourceType(Enum):
    """Types of resources that can be quota-limited"""
    AGENTS = "agents"
    NETWORKS = "networks"
    FLOWS = "flows"
    API_CALLS = "api_calls"
    STORAGE_MB = "storage_mb"
    CHAOS_SCENARIOS = "chaos_scenarios"
    WHATIF_SIMULATIONS = "whatif_simulations"


class IsolationLevel(Enum):
    """Levels of tenant isolation"""
    NONE = "none"                 # No isolation (single-tenant mode)
    SOFT = "soft"                 # Logical isolation (data filtering)
    STRICT = "strict"             # Strict isolation (full separation)


@dataclass
class ResourceQuota:
    """
    Resource quota for a tenant

    Attributes:
        resource_type: Type of resource
        limit: Maximum allowed
        current_usage: Current usage
        reset_period_hours: How often to reset (0 = never)
        last_reset: Last reset timestamp
    """
    resource_type: ResourceType
    limit: int
    current_usage: int = 0
    reset_period_hours: int = 0
    last_reset: datetime = field(default_factory=datetime.now)

    @property
    def remaining(self) -> int:
        """Remaining quota"""
        return max(0, self.limit - self.current_usage)

    @property
    def usage_percent(self) -> float:
        """Usage as percentage"""
        if self.limit == 0:
            return 100.0
        return (self.current_usage / self.limit) * 100

    @property
    def is_exceeded(self) -> bool:
        """Check if quota is exceeded"""
        return self.current_usage >= self.limit

    def should_reset(self) -> bool:
        """Check if quota should be reset"""
        if self.reset_period_hours == 0:
            return False
        elapsed = datetime.now() - self.last_reset
        return elapsed >= timedelta(hours=self.reset_period_hours)

    def reset(self):
        """Reset the quota"""
        self.current_usage = 0
        self.last_reset = datetime.now()

    def consume(self, amount: int = 1) -> bool:
        """
        Consume quota

        Args:
            amount: Amount to consume

        Returns:
            True if successful, False if would exceed quota
        """
        if self.current_usage + amount > self.limit:
            return False
        self.current_usage += amount
        return True

    def release(self, amount: int = 1):
        """Release previously consumed quota"""
        self.current_usage = max(0, self.current_usage - amount)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_type": self.resource_type.value,
            "limit": self.limit,
            "current_usage": self.current_usage,
            "remaining": self.remaining,
            "usage_percent": self.usage_percent,
            "is_exceeded": self.is_exceeded,
            "reset_period_hours": self.reset_period_hours,
            "last_reset": self.last_reset.isoformat()
        }


@dataclass
class TenantContext:
    """
    Context for tenant-scoped operations

    Used to scope operations to a specific tenant and enforce isolation
    """
    tenant_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    permissions: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: str) -> bool:
        """Check if context has a permission"""
        return permission in self.permissions or "*" in self.permissions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "permissions": list(self.permissions),
            "metadata": self.metadata
        }


class TenantIsolation:
    """
    Manages tenant isolation and resource quotas
    """

    def __init__(self, isolation_level: IsolationLevel = IsolationLevel.SOFT):
        """
        Initialize tenant isolation

        Args:
            isolation_level: Level of isolation to enforce
        """
        self._isolation_level = isolation_level
        self._quotas: Dict[str, Dict[ResourceType, ResourceQuota]] = defaultdict(dict)
        self._access_log: List[Dict[str, Any]] = []
        self._cross_tenant_allowed: Set[tuple] = set()  # (from_tenant, to_tenant, resource_type)

    def set_isolation_level(self, level: IsolationLevel):
        """Set the isolation level"""
        self._isolation_level = level
        logger.info(f"Isolation level set to: {level.value}")

    def get_isolation_level(self) -> IsolationLevel:
        """Get current isolation level"""
        return self._isolation_level

    def create_context(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        permissions: Optional[Set[str]] = None
    ) -> TenantContext:
        """
        Create a tenant context for scoped operations

        Args:
            tenant_id: Tenant ID
            user_id: Optional user ID
            permissions: Optional permissions set

        Returns:
            TenantContext for use in operations
        """
        context = TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            request_id=f"req-{datetime.now().timestamp()}",
            permissions=permissions or set()
        )

        # Set context variable
        current_tenant.set(tenant_id)

        return context

    def get_current_tenant(self) -> Optional[str]:
        """Get the current tenant from context"""
        return current_tenant.get()

    def set_quota(
        self,
        tenant_id: str,
        resource_type: ResourceType,
        limit: int,
        reset_period_hours: int = 0
    ) -> ResourceQuota:
        """
        Set a quota for a tenant

        Args:
            tenant_id: Tenant to set quota for
            resource_type: Type of resource
            limit: Maximum allowed
            reset_period_hours: Reset period (0 = no reset)

        Returns:
            Created ResourceQuota
        """
        quota = ResourceQuota(
            resource_type=resource_type,
            limit=limit,
            reset_period_hours=reset_period_hours
        )
        self._quotas[tenant_id][resource_type] = quota
        logger.info(f"Set quota for {tenant_id}: {resource_type.value} = {limit}")
        return quota

    def get_quota(
        self,
        tenant_id: str,
        resource_type: ResourceType
    ) -> Optional[ResourceQuota]:
        """Get a quota for a tenant"""
        return self._quotas.get(tenant_id, {}).get(resource_type)

    def get_all_quotas(self, tenant_id: str) -> Dict[str, ResourceQuota]:
        """Get all quotas for a tenant"""
        return {
            rt.value: quota
            for rt, quota in self._quotas.get(tenant_id, {}).items()
        }

    def check_quota(
        self,
        tenant_id: str,
        resource_type: ResourceType,
        amount: int = 1
    ) -> bool:
        """
        Check if a quota allows the operation

        Args:
            tenant_id: Tenant to check
            resource_type: Resource type
            amount: Amount to check

        Returns:
            True if quota allows, False otherwise
        """
        quota = self.get_quota(tenant_id, resource_type)
        if not quota:
            return True  # No quota set = unlimited

        # Check for reset
        if quota.should_reset():
            quota.reset()

        return quota.current_usage + amount <= quota.limit

    def consume_quota(
        self,
        tenant_id: str,
        resource_type: ResourceType,
        amount: int = 1
    ) -> bool:
        """
        Consume quota for an operation

        Args:
            tenant_id: Tenant
            resource_type: Resource type
            amount: Amount to consume

        Returns:
            True if consumed successfully
        """
        quota = self.get_quota(tenant_id, resource_type)
        if not quota:
            return True  # No quota = allow

        if quota.should_reset():
            quota.reset()

        return quota.consume(amount)

    def release_quota(
        self,
        tenant_id: str,
        resource_type: ResourceType,
        amount: int = 1
    ):
        """Release previously consumed quota"""
        quota = self.get_quota(tenant_id, resource_type)
        if quota:
            quota.release(amount)

    def verify_access(
        self,
        tenant_id: str,
        resource_tenant_id: str,
        resource_type: str
    ) -> bool:
        """
        Verify tenant can access a resource

        Args:
            tenant_id: Requesting tenant
            resource_tenant_id: Tenant that owns the resource
            resource_type: Type of resource

        Returns:
            True if access is allowed
        """
        if self._isolation_level == IsolationLevel.NONE:
            return True

        # Same tenant always allowed
        if tenant_id == resource_tenant_id:
            return True

        # Check for explicit cross-tenant permission
        if (tenant_id, resource_tenant_id, resource_type) in self._cross_tenant_allowed:
            return True

        # Strict mode: no cross-tenant access
        if self._isolation_level == IsolationLevel.STRICT:
            self._log_access_denied(tenant_id, resource_tenant_id, resource_type)
            return False

        # Soft mode: log but allow (for debugging/migration)
        self._log_access_warning(tenant_id, resource_tenant_id, resource_type)
        return True

    def allow_cross_tenant_access(
        self,
        from_tenant: str,
        to_tenant: str,
        resource_type: str
    ):
        """
        Allow cross-tenant access for specific resource type

        Args:
            from_tenant: Requesting tenant
            to_tenant: Resource owner tenant
            resource_type: Type of resource
        """
        self._cross_tenant_allowed.add((from_tenant, to_tenant, resource_type))
        logger.info(f"Allowed cross-tenant access: {from_tenant} -> {to_tenant} ({resource_type})")

    def revoke_cross_tenant_access(
        self,
        from_tenant: str,
        to_tenant: str,
        resource_type: str
    ):
        """Revoke cross-tenant access"""
        self._cross_tenant_allowed.discard((from_tenant, to_tenant, resource_type))
        logger.info(f"Revoked cross-tenant access: {from_tenant} -> {to_tenant} ({resource_type})")

    def _log_access_denied(
        self,
        tenant_id: str,
        resource_tenant_id: str,
        resource_type: str
    ):
        """Log an access denied event"""
        entry = {
            "event": "access_denied",
            "tenant_id": tenant_id,
            "resource_tenant_id": resource_tenant_id,
            "resource_type": resource_type,
            "timestamp": datetime.now().isoformat()
        }
        self._access_log.append(entry)
        logger.warning(f"Access denied: {tenant_id} -> {resource_tenant_id} ({resource_type})")

    def _log_access_warning(
        self,
        tenant_id: str,
        resource_tenant_id: str,
        resource_type: str
    ):
        """Log a cross-tenant access warning"""
        entry = {
            "event": "cross_tenant_access",
            "tenant_id": tenant_id,
            "resource_tenant_id": resource_tenant_id,
            "resource_type": resource_type,
            "timestamp": datetime.now().isoformat()
        }
        self._access_log.append(entry)
        logger.debug(f"Cross-tenant access: {tenant_id} -> {resource_tenant_id} ({resource_type})")

    def get_access_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent access log entries"""
        return self._access_log[-limit:]

    def filter_by_tenant(
        self,
        items: List[Any],
        tenant_id: str,
        tenant_attr: str = "tenant_id"
    ) -> List[Any]:
        """
        Filter a list to only items belonging to a tenant

        Args:
            items: List to filter
            tenant_id: Tenant to filter for
            tenant_attr: Attribute name for tenant ID

        Returns:
            Filtered list
        """
        if self._isolation_level == IsolationLevel.NONE:
            return items

        return [
            item for item in items
            if getattr(item, tenant_attr, None) == tenant_id
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get isolation statistics"""
        return {
            "isolation_level": self._isolation_level.value,
            "tenants_with_quotas": len(self._quotas),
            "cross_tenant_rules": len(self._cross_tenant_allowed),
            "access_log_entries": len(self._access_log),
            "resource_types": [rt.value for rt in ResourceType]
        }


# Global isolation instance
_global_isolation: Optional[TenantIsolation] = None


def get_tenant_isolation() -> TenantIsolation:
    """Get or create the global tenant isolation"""
    global _global_isolation
    if _global_isolation is None:
        _global_isolation = TenantIsolation()
    return _global_isolation
