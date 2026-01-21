"""
Role Management - Roles and permissions for RBAC

Provides:
- Permission definitions
- Role creation and management
- Role-permission associations
- Hierarchical role support
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Set

logger = logging.getLogger("RoleManager")


class PermissionScope(Enum):
    """Scope of a permission"""
    GLOBAL = "global"             # System-wide permission
    TENANT = "tenant"             # Tenant-scoped permission
    NETWORK = "network"           # Network-scoped permission
    AGENT = "agent"               # Agent-scoped permission


class PermissionAction(Enum):
    """Types of actions for permissions"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    ADMIN = "admin"


@dataclass
class Permission:
    """
    A permission definition

    Attributes:
        permission_id: Unique identifier
        name: Permission name
        description: What this permission allows
        resource: Resource type this applies to
        action: Allowed action
        scope: Permission scope
    """
    permission_id: str
    name: str
    description: str
    resource: str
    action: PermissionAction
    scope: PermissionScope = PermissionScope.GLOBAL
    metadata: Dict[str, Any] = field(default_factory=dict)

    def matches(self, resource: str, action: str) -> bool:
        """Check if this permission matches a resource/action"""
        if self.resource == "*" or self.resource == resource:
            if self.action.value == action or self.action == PermissionAction.ADMIN:
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "permission_id": self.permission_id,
            "name": self.name,
            "description": self.description,
            "resource": self.resource,
            "action": self.action.value,
            "scope": self.scope.value,
            "metadata": self.metadata
        }


@dataclass
class Role:
    """
    A role that groups permissions

    Attributes:
        role_id: Unique identifier
        name: Role name
        description: Role description
        permission_ids: Permissions included in this role
        parent_role_ids: Parent roles (for inheritance)
        is_system: Whether this is a built-in role
    """
    role_id: str
    name: str
    description: str = ""
    permission_ids: Set[str] = field(default_factory=set)
    parent_role_ids: Set[str] = field(default_factory=set)
    is_system: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission_id: str) -> bool:
        """Check if role has a specific permission"""
        return permission_id in self.permission_ids

    def add_permission(self, permission_id: str):
        """Add a permission to this role"""
        self.permission_ids.add(permission_id)

    def remove_permission(self, permission_id: str):
        """Remove a permission from this role"""
        self.permission_ids.discard(permission_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "description": self.description,
            "permission_ids": list(self.permission_ids),
            "parent_role_ids": list(self.parent_role_ids),
            "is_system": self.is_system,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata
        }


class RoleManager:
    """
    Manages roles and permissions
    """

    def __init__(self):
        """Initialize role manager"""
        self._permissions: Dict[str, Permission] = {}
        self._roles: Dict[str, Role] = {}
        self._permission_counter = 0
        self._role_counter = 0

        # Create default permissions and roles
        self._create_default_permissions()
        self._create_default_roles()

    def _generate_permission_id(self) -> str:
        """Generate unique permission ID"""
        self._permission_counter += 1
        return f"perm-{self._permission_counter:06d}"

    def _generate_role_id(self) -> str:
        """Generate unique role ID"""
        self._role_counter += 1
        return f"role-{self._role_counter:06d}"

    def _create_default_permissions(self):
        """Create default system permissions"""
        defaults = [
            # Network permissions
            ("network:read", "Read Networks", "View network configurations", "network", PermissionAction.READ),
            ("network:create", "Create Networks", "Create new networks", "network", PermissionAction.CREATE),
            ("network:update", "Update Networks", "Modify network configurations", "network", PermissionAction.UPDATE),
            ("network:delete", "Delete Networks", "Delete networks", "network", PermissionAction.DELETE),

            # Agent permissions
            ("agent:read", "Read Agents", "View agent status and config", "agent", PermissionAction.READ),
            ("agent:create", "Create Agents", "Create new agents", "agent", PermissionAction.CREATE),
            ("agent:update", "Update Agents", "Modify agent configurations", "agent", PermissionAction.UPDATE),
            ("agent:delete", "Delete Agents", "Delete agents", "agent", PermissionAction.DELETE),
            ("agent:execute", "Execute Agent Commands", "Run commands on agents", "agent", PermissionAction.EXECUTE),

            # Protocol permissions
            ("protocol:read", "Read Protocols", "View protocol state", "protocol", PermissionAction.READ),
            ("protocol:update", "Configure Protocols", "Modify protocol config", "protocol", PermissionAction.UPDATE),

            # Traffic permissions
            ("traffic:read", "Read Traffic", "View traffic data", "traffic", PermissionAction.READ),
            ("traffic:execute", "Generate Traffic", "Create traffic flows", "traffic", PermissionAction.EXECUTE),

            # Chaos permissions
            ("chaos:read", "Read Chaos", "View chaos scenarios", "chaos", PermissionAction.READ),
            ("chaos:execute", "Run Chaos", "Execute chaos scenarios", "chaos", PermissionAction.EXECUTE),

            # Tenant permissions
            ("tenant:read", "Read Tenants", "View tenant info", "tenant", PermissionAction.READ),
            ("tenant:create", "Create Tenants", "Create new tenants", "tenant", PermissionAction.CREATE),
            ("tenant:update", "Update Tenants", "Modify tenant config", "tenant", PermissionAction.UPDATE),
            ("tenant:delete", "Delete Tenants", "Delete tenants", "tenant", PermissionAction.DELETE),

            # User permissions
            ("user:read", "Read Users", "View user accounts", "user", PermissionAction.READ),
            ("user:create", "Create Users", "Create user accounts", "user", PermissionAction.CREATE),
            ("user:update", "Update Users", "Modify user accounts", "user", PermissionAction.UPDATE),
            ("user:delete", "Delete Users", "Delete user accounts", "user", PermissionAction.DELETE),

            # Admin permission
            ("admin:all", "Full Admin", "Full administrative access", "*", PermissionAction.ADMIN),
        ]

        for perm_id, name, desc, resource, action in defaults:
            self._permissions[perm_id] = Permission(
                permission_id=perm_id,
                name=name,
                description=desc,
                resource=resource,
                action=action
            )

    def _create_default_roles(self):
        """Create default system roles"""
        # Viewer role - read-only access
        viewer = Role(
            role_id="role-viewer",
            name="Viewer",
            description="Read-only access to view network state",
            permission_ids={
                "network:read", "agent:read", "protocol:read", "traffic:read"
            },
            is_system=True
        )
        self._roles[viewer.role_id] = viewer

        # Operator role - can execute but not configure
        operator = Role(
            role_id="role-operator",
            name="Operator",
            description="Can view and execute operations",
            permission_ids={
                "network:read", "agent:read", "agent:execute",
                "protocol:read", "traffic:read", "traffic:execute",
                "chaos:read"
            },
            parent_role_ids={"role-viewer"},
            is_system=True
        )
        self._roles[operator.role_id] = operator

        # Network Admin role - full network control
        network_admin = Role(
            role_id="role-network-admin",
            name="Network Administrator",
            description="Full control over networks and agents",
            permission_ids={
                "network:read", "network:create", "network:update", "network:delete",
                "agent:read", "agent:create", "agent:update", "agent:delete", "agent:execute",
                "protocol:read", "protocol:update",
                "traffic:read", "traffic:execute",
                "chaos:read", "chaos:execute"
            },
            parent_role_ids={"role-operator"},
            is_system=True
        )
        self._roles[network_admin.role_id] = network_admin

        # Tenant Admin role - manages users within tenant
        tenant_admin = Role(
            role_id="role-tenant-admin",
            name="Tenant Administrator",
            description="Manages users and resources within a tenant",
            permission_ids={
                "user:read", "user:create", "user:update",
                "tenant:read"
            },
            parent_role_ids={"role-network-admin"},
            is_system=True
        )
        self._roles[tenant_admin.role_id] = tenant_admin

        # Super Admin role - full system access
        admin = Role(
            role_id="role-admin",
            name="Administrator",
            description="Full system administrative access",
            permission_ids={"admin:all"},
            parent_role_ids={"role-tenant-admin"},
            is_system=True
        )
        self._roles[admin.role_id] = admin

        logger.info("Created default roles: viewer, operator, network-admin, tenant-admin, admin")

    def create_permission(
        self,
        name: str,
        description: str,
        resource: str,
        action: PermissionAction,
        scope: PermissionScope = PermissionScope.GLOBAL
    ) -> Permission:
        """
        Create a new permission

        Args:
            name: Permission name
            description: Description
            resource: Resource type
            action: Allowed action
            scope: Permission scope

        Returns:
            Created Permission
        """
        permission = Permission(
            permission_id=self._generate_permission_id(),
            name=name,
            description=description,
            resource=resource,
            action=action,
            scope=scope
        )
        self._permissions[permission.permission_id] = permission
        logger.info(f"Created permission: {name}")
        return permission

    def get_permission(self, permission_id: str) -> Optional[Permission]:
        """Get a permission by ID"""
        return self._permissions.get(permission_id)

    def get_all_permissions(self) -> List[Permission]:
        """Get all permissions"""
        return list(self._permissions.values())

    def create_role(
        self,
        name: str,
        description: str = "",
        permission_ids: Optional[Set[str]] = None,
        parent_role_ids: Optional[Set[str]] = None
    ) -> Role:
        """
        Create a new role

        Args:
            name: Role name
            description: Role description
            permission_ids: Permissions to include
            parent_role_ids: Parent roles for inheritance

        Returns:
            Created Role
        """
        role = Role(
            role_id=self._generate_role_id(),
            name=name,
            description=description,
            permission_ids=permission_ids or set(),
            parent_role_ids=parent_role_ids or set()
        )
        self._roles[role.role_id] = role
        logger.info(f"Created role: {name}")
        return role

    def get_role(self, role_id: str) -> Optional[Role]:
        """Get a role by ID"""
        return self._roles.get(role_id)

    def get_role_by_name(self, name: str) -> Optional[Role]:
        """Get a role by name"""
        for role in self._roles.values():
            if role.name == name:
                return role
        return None

    def get_all_roles(self) -> List[Role]:
        """Get all roles"""
        return list(self._roles.values())

    def get_effective_permissions(self, role_id: str) -> Set[str]:
        """
        Get all effective permissions for a role, including inherited

        Args:
            role_id: Role to check

        Returns:
            Set of all effective permission IDs
        """
        role = self._roles.get(role_id)
        if not role:
            return set()

        permissions = set(role.permission_ids)

        # Add inherited permissions
        for parent_id in role.parent_role_ids:
            permissions.update(self.get_effective_permissions(parent_id))

        return permissions

    def role_has_permission(
        self,
        role_id: str,
        resource: str,
        action: str
    ) -> bool:
        """
        Check if a role has permission for an action

        Args:
            role_id: Role to check
            resource: Resource type
            action: Action type

        Returns:
            True if permission exists
        """
        effective_perms = self.get_effective_permissions(role_id)

        for perm_id in effective_perms:
            perm = self._permissions.get(perm_id)
            if perm and perm.matches(resource, action):
                return True

        return False

    def add_permission_to_role(self, role_id: str, permission_id: str) -> bool:
        """Add a permission to a role"""
        role = self._roles.get(role_id)
        if not role or role.is_system:
            return False
        if permission_id not in self._permissions:
            return False
        role.add_permission(permission_id)
        logger.info(f"Added permission {permission_id} to role {role.name}")
        return True

    def remove_permission_from_role(self, role_id: str, permission_id: str) -> bool:
        """Remove a permission from a role"""
        role = self._roles.get(role_id)
        if not role or role.is_system:
            return False
        role.remove_permission(permission_id)
        logger.info(f"Removed permission {permission_id} from role {role.name}")
        return True

    def get_statistics(self) -> Dict[str, Any]:
        """Get role manager statistics"""
        return {
            "total_permissions": len(self._permissions),
            "total_roles": len(self._roles),
            "system_roles": len([r for r in self._roles.values() if r.is_system])
        }


# Global manager instance
_global_manager: Optional[RoleManager] = None


def get_role_manager() -> RoleManager:
    """Get or create the global role manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = RoleManager()
    return _global_manager
