"""
Tenant Management - Multi-tenant network management

Provides:
- Tenant creation and lifecycle management
- Tenant metadata and configuration
- Tenant status tracking
- Resource association per tenant
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Set

logger = logging.getLogger("TenantManager")


class TenantStatus(Enum):
    """Tenant lifecycle status"""
    PENDING = "pending"           # Tenant created, awaiting activation
    ACTIVE = "active"             # Tenant is active and operational
    SUSPENDED = "suspended"       # Tenant temporarily suspended
    DISABLED = "disabled"         # Tenant disabled (soft delete)
    DELETED = "deleted"           # Tenant marked for deletion


class TenantTier(Enum):
    """Tenant service tier"""
    FREE = "free"                 # Free tier with limited resources
    BASIC = "basic"               # Basic paid tier
    STANDARD = "standard"         # Standard tier
    PREMIUM = "premium"           # Premium tier with more resources
    ENTERPRISE = "enterprise"     # Enterprise tier with full features


@dataclass
class TenantConfig:
    """
    Tenant configuration settings

    Attributes:
        max_agents: Maximum number of agents
        max_networks: Maximum number of networks
        max_flows: Maximum concurrent traffic flows
        max_api_calls_per_hour: API rate limit
        features_enabled: List of enabled features
    """
    max_agents: int = 10
    max_networks: int = 5
    max_flows: int = 50
    max_api_calls_per_hour: int = 1000
    features_enabled: Set[str] = field(default_factory=lambda: {"basic"})
    custom_settings: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_agents": self.max_agents,
            "max_networks": self.max_networks,
            "max_flows": self.max_flows,
            "max_api_calls_per_hour": self.max_api_calls_per_hour,
            "features_enabled": list(self.features_enabled),
            "custom_settings": self.custom_settings
        }

    @classmethod
    def for_tier(cls, tier: TenantTier) -> "TenantConfig":
        """Create config based on tier"""
        configs = {
            TenantTier.FREE: cls(
                max_agents=3,
                max_networks=1,
                max_flows=10,
                max_api_calls_per_hour=100,
                features_enabled={"basic"}
            ),
            TenantTier.BASIC: cls(
                max_agents=10,
                max_networks=3,
                max_flows=50,
                max_api_calls_per_hour=500,
                features_enabled={"basic", "monitoring"}
            ),
            TenantTier.STANDARD: cls(
                max_agents=25,
                max_networks=10,
                max_flows=100,
                max_api_calls_per_hour=2000,
                features_enabled={"basic", "monitoring", "analytics", "automation"}
            ),
            TenantTier.PREMIUM: cls(
                max_agents=100,
                max_networks=50,
                max_flows=500,
                max_api_calls_per_hour=10000,
                features_enabled={"basic", "monitoring", "analytics", "automation", "chaos", "whatif"}
            ),
            TenantTier.ENTERPRISE: cls(
                max_agents=1000,
                max_networks=500,
                max_flows=5000,
                max_api_calls_per_hour=100000,
                features_enabled={"basic", "monitoring", "analytics", "automation", "chaos", "whatif", "custom", "sla"}
            )
        }
        return configs.get(tier, configs[TenantTier.FREE])


@dataclass
class Tenant:
    """
    A tenant in the multi-tenant system

    Attributes:
        tenant_id: Unique identifier
        name: Display name
        description: Tenant description
        tier: Service tier
        status: Current status
        config: Tenant configuration
        owner_email: Owner email address
        created_at: Creation timestamp
    """
    tenant_id: str
    name: str
    description: str = ""
    tier: TenantTier = TenantTier.FREE
    status: TenantStatus = TenantStatus.PENDING
    config: TenantConfig = field(default_factory=TenantConfig)
    owner_email: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    activated_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Resource tracking
    agent_ids: Set[str] = field(default_factory=set)
    network_ids: Set[str] = field(default_factory=set)
    user_ids: Set[str] = field(default_factory=set)

    @property
    def is_active(self) -> bool:
        """Check if tenant is active"""
        return self.status == TenantStatus.ACTIVE

    @property
    def agent_count(self) -> int:
        """Number of agents owned by tenant"""
        return len(self.agent_ids)

    @property
    def network_count(self) -> int:
        """Number of networks owned by tenant"""
        return len(self.network_ids)

    @property
    def can_create_agent(self) -> bool:
        """Check if tenant can create more agents"""
        return self.is_active and self.agent_count < self.config.max_agents

    @property
    def can_create_network(self) -> bool:
        """Check if tenant can create more networks"""
        return self.is_active and self.network_count < self.config.max_networks

    def has_feature(self, feature: str) -> bool:
        """Check if tenant has a feature enabled"""
        return feature in self.config.features_enabled

    def add_agent(self, agent_id: str) -> bool:
        """Add an agent to this tenant"""
        if not self.can_create_agent:
            return False
        self.agent_ids.add(agent_id)
        return True

    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent from this tenant"""
        if agent_id in self.agent_ids:
            self.agent_ids.discard(agent_id)
            return True
        return False

    def add_network(self, network_id: str) -> bool:
        """Add a network to this tenant"""
        if not self.can_create_network:
            return False
        self.network_ids.add(network_id)
        return True

    def remove_network(self, network_id: str) -> bool:
        """Remove a network from this tenant"""
        if network_id in self.network_ids:
            self.network_ids.discard(network_id)
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "tier": self.tier.value,
            "status": self.status.value,
            "config": self.config.to_dict(),
            "owner_email": self.owner_email,
            "created_at": self.created_at.isoformat(),
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "suspended_at": self.suspended_at.isoformat() if self.suspended_at else None,
            "agent_count": self.agent_count,
            "network_count": self.network_count,
            "user_count": len(self.user_ids),
            "agent_ids": list(self.agent_ids),
            "network_ids": list(self.network_ids),
            "metadata": self.metadata
        }


class TenantManager:
    """
    Manages tenants in the multi-tenant system
    """

    def __init__(self):
        """Initialize tenant manager"""
        self._tenants: Dict[str, Tenant] = {}
        self._tenant_counter = 0
        self._default_tenant: Optional[str] = None

        # Create default tenant
        self._create_default_tenant()

    def _generate_tenant_id(self) -> str:
        """Generate unique tenant ID"""
        self._tenant_counter += 1
        return f"tenant-{self._tenant_counter:06d}"

    def _create_default_tenant(self):
        """Create the default system tenant"""
        default = Tenant(
            tenant_id="tenant-default",
            name="Default Tenant",
            description="Default system tenant for single-tenant mode",
            tier=TenantTier.ENTERPRISE,
            status=TenantStatus.ACTIVE,
            config=TenantConfig.for_tier(TenantTier.ENTERPRISE),
            owner_email="admin@localhost"
        )
        default.activated_at = datetime.now()
        self._tenants[default.tenant_id] = default
        self._default_tenant = default.tenant_id
        logger.info("Created default tenant")

    def create_tenant(
        self,
        name: str,
        description: str = "",
        tier: TenantTier = TenantTier.FREE,
        owner_email: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tenant:
        """
        Create a new tenant

        Args:
            name: Tenant name
            description: Description
            tier: Service tier
            owner_email: Owner email
            metadata: Additional metadata

        Returns:
            Created Tenant
        """
        tenant = Tenant(
            tenant_id=self._generate_tenant_id(),
            name=name,
            description=description,
            tier=tier,
            config=TenantConfig.for_tier(tier),
            owner_email=owner_email,
            metadata=metadata or {}
        )

        self._tenants[tenant.tenant_id] = tenant
        logger.info(f"Created tenant: {name} (tier: {tier.value})")
        return tenant

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get a tenant by ID"""
        return self._tenants.get(tenant_id)

    def get_tenant_by_name(self, name: str) -> Optional[Tenant]:
        """Get a tenant by name"""
        for tenant in self._tenants.values():
            if tenant.name == name:
                return tenant
        return None

    def get_default_tenant(self) -> Optional[Tenant]:
        """Get the default tenant"""
        if self._default_tenant:
            return self._tenants.get(self._default_tenant)
        return None

    def get_all_tenants(self) -> List[Tenant]:
        """Get all tenants"""
        return list(self._tenants.values())

    def get_active_tenants(self) -> List[Tenant]:
        """Get all active tenants"""
        return [t for t in self._tenants.values() if t.is_active]

    def activate_tenant(self, tenant_id: str) -> bool:
        """
        Activate a tenant

        Args:
            tenant_id: Tenant to activate

        Returns:
            True if activated successfully
        """
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False

        if tenant.status in {TenantStatus.DELETED}:
            return False

        tenant.status = TenantStatus.ACTIVE
        tenant.activated_at = datetime.now()
        tenant.suspended_at = None
        logger.info(f"Activated tenant: {tenant.name}")
        return True

    def suspend_tenant(self, tenant_id: str, reason: str = "") -> bool:
        """
        Suspend a tenant

        Args:
            tenant_id: Tenant to suspend
            reason: Suspension reason

        Returns:
            True if suspended successfully
        """
        tenant = self._tenants.get(tenant_id)
        if not tenant or not tenant.is_active:
            return False

        tenant.status = TenantStatus.SUSPENDED
        tenant.suspended_at = datetime.now()
        tenant.metadata["suspension_reason"] = reason
        logger.info(f"Suspended tenant: {tenant.name} ({reason})")
        return True

    def disable_tenant(self, tenant_id: str) -> bool:
        """
        Disable a tenant (soft delete)

        Args:
            tenant_id: Tenant to disable

        Returns:
            True if disabled successfully
        """
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False

        tenant.status = TenantStatus.DISABLED
        logger.info(f"Disabled tenant: {tenant.name}")
        return True

    def delete_tenant(self, tenant_id: str) -> bool:
        """
        Mark a tenant for deletion

        Args:
            tenant_id: Tenant to delete

        Returns:
            True if marked for deletion
        """
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False

        # Don't delete default tenant
        if tenant_id == self._default_tenant:
            logger.warning("Cannot delete default tenant")
            return False

        tenant.status = TenantStatus.DELETED
        logger.info(f"Marked tenant for deletion: {tenant.name}")
        return True

    def update_tier(self, tenant_id: str, new_tier: TenantTier) -> bool:
        """
        Update a tenant's service tier

        Args:
            tenant_id: Tenant to update
            new_tier: New tier

        Returns:
            True if updated successfully
        """
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False

        old_tier = tenant.tier
        tenant.tier = new_tier
        tenant.config = TenantConfig.for_tier(new_tier)
        logger.info(f"Updated tenant tier: {tenant.name} ({old_tier.value} -> {new_tier.value})")
        return True

    def get_tenant_for_agent(self, agent_id: str) -> Optional[Tenant]:
        """Find the tenant that owns an agent"""
        for tenant in self._tenants.values():
            if agent_id in tenant.agent_ids:
                return tenant
        return None

    def get_tenant_for_network(self, network_id: str) -> Optional[Tenant]:
        """Find the tenant that owns a network"""
        for tenant in self._tenants.values():
            if network_id in tenant.network_ids:
                return tenant
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get tenant manager statistics"""
        tenants_by_tier = {}
        tenants_by_status = {}

        for tenant in self._tenants.values():
            tier = tenant.tier.value
            tenants_by_tier[tier] = tenants_by_tier.get(tier, 0) + 1

            status = tenant.status.value
            tenants_by_status[status] = tenants_by_status.get(status, 0) + 1

        return {
            "total_tenants": len(self._tenants),
            "active_tenants": len(self.get_active_tenants()),
            "default_tenant": self._default_tenant,
            "tenants_by_tier": tenants_by_tier,
            "tenants_by_status": tenants_by_status
        }


# Global manager instance
_global_manager: Optional[TenantManager] = None


def get_tenant_manager() -> TenantManager:
    """Get or create the global tenant manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = TenantManager()
    return _global_manager
