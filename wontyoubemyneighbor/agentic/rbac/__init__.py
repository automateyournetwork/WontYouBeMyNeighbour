"""
Role-Based Access Control (RBAC) Module

Provides access control for network operations:
- User and role management
- Permission definitions
- Access policy enforcement
- Audit logging
"""

from .users import (
    User,
    UserManager,
    UserStatus,
    get_user_manager
)

from .roles import (
    Role,
    Permission,
    RoleManager,
    get_role_manager
)

from .policy import (
    AccessPolicy,
    PolicyEngine,
    AccessDecision,
    get_policy_engine
)

__all__ = [
    # Users
    "User",
    "UserManager",
    "UserStatus",
    "get_user_manager",
    # Roles
    "Role",
    "Permission",
    "RoleManager",
    "get_role_manager",
    # Policy
    "AccessPolicy",
    "PolicyEngine",
    "AccessDecision",
    "get_policy_engine"
]
