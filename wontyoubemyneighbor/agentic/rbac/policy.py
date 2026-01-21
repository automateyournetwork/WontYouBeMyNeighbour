"""
Access Policy Engine - Enforces RBAC policies

Provides:
- Access decision evaluation
- Policy enforcement
- Audit logging
- Context-aware authorization
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

from .users import User, get_user_manager
from .roles import get_role_manager

logger = logging.getLogger("PolicyEngine")


class AccessDecision(Enum):
    """Result of an access check"""
    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"


class DenyReason(Enum):
    """Reasons for access denial"""
    NO_PERMISSION = "no_permission"
    USER_INACTIVE = "user_inactive"
    USER_LOCKED = "user_locked"
    TENANT_MISMATCH = "tenant_mismatch"
    RESOURCE_NOT_FOUND = "resource_not_found"
    QUOTA_EXCEEDED = "quota_exceeded"
    POLICY_VIOLATION = "policy_violation"


@dataclass
class AccessRequest:
    """
    An access request to be evaluated

    Attributes:
        user_id: Requesting user
        resource: Resource being accessed
        action: Action being performed
        resource_owner: Owner of the resource
        context: Additional context
    """
    user_id: str
    resource: str
    action: str
    resource_owner: Optional[str] = None
    tenant_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "resource": self.resource,
            "action": self.action,
            "resource_owner": self.resource_owner,
            "tenant_id": self.tenant_id,
            "context": self.context
        }


@dataclass
class AccessResult:
    """
    Result of an access evaluation

    Attributes:
        decision: Allow or deny
        reason: Reason for the decision
        matched_permission: Permission that allowed access
        evaluated_at: When decision was made
    """
    decision: AccessDecision
    reason: Optional[DenyReason] = None
    matched_permission: Optional[str] = None
    evaluated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_allowed(self) -> bool:
        return self.decision == AccessDecision.ALLOW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "is_allowed": self.is_allowed,
            "reason": self.reason.value if self.reason else None,
            "matched_permission": self.matched_permission,
            "evaluated_at": self.evaluated_at.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class AccessPolicy:
    """
    An access control policy

    Attributes:
        policy_id: Unique identifier
        name: Policy name
        description: Policy description
        resource_pattern: Resource pattern to match
        action_pattern: Action pattern to match
        effect: Allow or deny effect
        conditions: Additional conditions
        priority: Policy priority (higher = evaluated first)
    """
    policy_id: str
    name: str
    description: str
    resource_pattern: str
    action_pattern: str
    effect: AccessDecision
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def matches(self, resource: str, action: str) -> bool:
        """Check if this policy matches a resource/action"""
        resource_match = (
            self.resource_pattern == "*" or
            self.resource_pattern == resource or
            resource.startswith(self.resource_pattern.rstrip("*"))
        )
        action_match = (
            self.action_pattern == "*" or
            self.action_pattern == action
        )
        return resource_match and action_match

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "resource_pattern": self.resource_pattern,
            "action_pattern": self.action_pattern,
            "effect": self.effect.value,
            "conditions": self.conditions,
            "priority": self.priority,
            "enabled": self.enabled,
            "metadata": self.metadata
        }


@dataclass
class AuditEntry:
    """
    Audit log entry for access decisions

    Attributes:
        entry_id: Unique identifier
        request: The access request
        result: The access result
        timestamp: When the request was made
    """
    entry_id: str
    request: AccessRequest
    result: AccessResult
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "request": self.request.to_dict(),
            "result": self.result.to_dict(),
            "timestamp": self.timestamp.isoformat()
        }


class PolicyEngine:
    """
    Evaluates access control policies
    """

    def __init__(self, audit_limit: int = 10000):
        """
        Initialize policy engine

        Args:
            audit_limit: Maximum audit entries to keep
        """
        self._policies: Dict[str, AccessPolicy] = {}
        self._audit_log: List[AuditEntry] = []
        self._audit_limit = audit_limit
        self._policy_counter = 0
        self._audit_counter = 0
        self._enforcement_enabled = True

    def _generate_policy_id(self) -> str:
        """Generate unique policy ID"""
        self._policy_counter += 1
        return f"policy-{self._policy_counter:06d}"

    def _generate_audit_id(self) -> str:
        """Generate unique audit entry ID"""
        self._audit_counter += 1
        return f"audit-{self._audit_counter:06d}"

    def set_enforcement(self, enabled: bool):
        """Enable or disable policy enforcement"""
        self._enforcement_enabled = enabled
        logger.info(f"Policy enforcement {'enabled' if enabled else 'disabled'}")

    def is_enforcement_enabled(self) -> bool:
        """Check if enforcement is enabled"""
        return self._enforcement_enabled

    def create_policy(
        self,
        name: str,
        description: str,
        resource_pattern: str,
        action_pattern: str,
        effect: AccessDecision,
        conditions: Optional[Dict[str, Any]] = None,
        priority: int = 0
    ) -> AccessPolicy:
        """
        Create a new access policy

        Args:
            name: Policy name
            description: Description
            resource_pattern: Resource pattern to match
            action_pattern: Action pattern to match
            effect: Allow or deny
            conditions: Additional conditions
            priority: Policy priority

        Returns:
            Created AccessPolicy
        """
        policy = AccessPolicy(
            policy_id=self._generate_policy_id(),
            name=name,
            description=description,
            resource_pattern=resource_pattern,
            action_pattern=action_pattern,
            effect=effect,
            conditions=conditions or {},
            priority=priority
        )
        self._policies[policy.policy_id] = policy
        logger.info(f"Created policy: {name}")
        return policy

    def get_policy(self, policy_id: str) -> Optional[AccessPolicy]:
        """Get a policy by ID"""
        return self._policies.get(policy_id)

    def get_all_policies(self) -> List[AccessPolicy]:
        """Get all policies sorted by priority"""
        return sorted(
            self._policies.values(),
            key=lambda p: p.priority,
            reverse=True
        )

    def enable_policy(self, policy_id: str) -> bool:
        """Enable a policy"""
        policy = self._policies.get(policy_id)
        if policy:
            policy.enabled = True
            return True
        return False

    def disable_policy(self, policy_id: str) -> bool:
        """Disable a policy"""
        policy = self._policies.get(policy_id)
        if policy:
            policy.enabled = False
            return True
        return False

    def delete_policy(self, policy_id: str) -> bool:
        """Delete a policy"""
        if policy_id in self._policies:
            del self._policies[policy_id]
            return True
        return False

    def evaluate(self, request: AccessRequest) -> AccessResult:
        """
        Evaluate an access request

        Args:
            request: The access request to evaluate

        Returns:
            AccessResult with decision
        """
        # If enforcement disabled, allow everything
        if not self._enforcement_enabled:
            result = AccessResult(
                decision=AccessDecision.ALLOW,
                metadata={"enforcement_disabled": True}
            )
            self._log_audit(request, result)
            return result

        user_manager = get_user_manager()
        role_manager = get_role_manager()

        # Get user
        user = user_manager.get_user(request.user_id)
        if not user:
            result = AccessResult(
                decision=AccessDecision.DENY,
                reason=DenyReason.RESOURCE_NOT_FOUND,
                metadata={"error": "User not found"}
            )
            self._log_audit(request, result)
            return result

        # Check user status
        if not user.is_active:
            reason = DenyReason.USER_LOCKED if user.is_locked else DenyReason.USER_INACTIVE
            result = AccessResult(
                decision=AccessDecision.DENY,
                reason=reason
            )
            self._log_audit(request, result)
            return result

        # Check tenant isolation
        if request.tenant_id and user.tenant_id:
            if request.tenant_id != user.tenant_id:
                result = AccessResult(
                    decision=AccessDecision.DENY,
                    reason=DenyReason.TENANT_MISMATCH
                )
                self._log_audit(request, result)
                return result

        # Check explicit policies first
        for policy in self.get_all_policies():
            if not policy.enabled:
                continue
            if policy.matches(request.resource, request.action):
                result = AccessResult(
                    decision=policy.effect,
                    matched_permission=policy.policy_id,
                    metadata={"policy_name": policy.name}
                )
                if policy.effect == AccessDecision.DENY:
                    result.reason = DenyReason.POLICY_VIOLATION
                self._log_audit(request, result)
                return result

        # Check role-based permissions
        for role_id in user.role_ids:
            if role_manager.role_has_permission(role_id, request.resource, request.action):
                result = AccessResult(
                    decision=AccessDecision.ALLOW,
                    matched_permission=f"role:{role_id}",
                    metadata={"via_role": role_id}
                )
                self._log_audit(request, result)
                return result

        # Default deny
        result = AccessResult(
            decision=AccessDecision.DENY,
            reason=DenyReason.NO_PERMISSION
        )
        self._log_audit(request, result)
        return result

    def check_permission(
        self,
        user_id: str,
        resource: str,
        action: str,
        tenant_id: Optional[str] = None
    ) -> bool:
        """
        Simple permission check

        Args:
            user_id: User to check
            resource: Resource type
            action: Action type
            tenant_id: Optional tenant context

        Returns:
            True if allowed
        """
        request = AccessRequest(
            user_id=user_id,
            resource=resource,
            action=action,
            tenant_id=tenant_id
        )
        result = self.evaluate(request)
        return result.is_allowed

    def _log_audit(self, request: AccessRequest, result: AccessResult):
        """Log an audit entry"""
        entry = AuditEntry(
            entry_id=self._generate_audit_id(),
            request=request,
            result=result
        )
        self._audit_log.append(entry)

        # Trim if over limit
        if len(self._audit_log) > self._audit_limit:
            self._audit_log = self._audit_log[-self._audit_limit:]

        # Log decision
        if result.is_allowed:
            logger.debug(f"ACCESS ALLOWED: {request.user_id} -> {request.resource}:{request.action}")
        else:
            logger.info(f"ACCESS DENIED: {request.user_id} -> {request.resource}:{request.action} ({result.reason})")

    def get_audit_log(
        self,
        limit: int = 100,
        user_id: Optional[str] = None,
        decision: Optional[AccessDecision] = None
    ) -> List[AuditEntry]:
        """
        Get audit log entries

        Args:
            limit: Maximum entries to return
            user_id: Filter by user
            decision: Filter by decision

        Returns:
            List of audit entries
        """
        entries = self._audit_log

        if user_id:
            entries = [e for e in entries if e.request.user_id == user_id]

        if decision:
            entries = [e for e in entries if e.result.decision == decision]

        return entries[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """Get policy engine statistics"""
        decisions = {}
        for entry in self._audit_log:
            dec = entry.result.decision.value
            decisions[dec] = decisions.get(dec, 0) + 1

        return {
            "total_policies": len(self._policies),
            "enabled_policies": len([p for p in self._policies.values() if p.enabled]),
            "enforcement_enabled": self._enforcement_enabled,
            "audit_entries": len(self._audit_log),
            "decisions": decisions
        }


# Global engine instance
_global_engine: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    """Get or create the global policy engine"""
    global _global_engine
    if _global_engine is None:
        _global_engine = PolicyEngine()
    return _global_engine
