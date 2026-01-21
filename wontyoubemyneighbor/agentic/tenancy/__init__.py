"""
Multi-Tenancy Module

Provides tenant isolation and management:
- Tenant definition and lifecycle
- Resource isolation and quotas
- Tenant-scoped data access
- Cross-tenant restrictions
"""

from .tenant import (
    Tenant,
    TenantManager,
    TenantStatus,
    get_tenant_manager
)

from .isolation import (
    TenantContext,
    ResourceQuota,
    TenantIsolation,
    get_tenant_isolation
)

__all__ = [
    # Tenant
    "Tenant",
    "TenantManager",
    "TenantStatus",
    "get_tenant_manager",
    # Isolation
    "TenantContext",
    "ResourceQuota",
    "TenantIsolation",
    "get_tenant_isolation"
]
