"""
Escalation Policies

Provides:
- Escalation rules
- Level definitions
- Automatic escalation
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum

from .definitions import Alert, AlertSeverity, AlertStatus


class EscalationTrigger(Enum):
    """What triggers escalation"""
    TIME = "time"  # After N minutes
    NO_ACK = "no_ack"  # Not acknowledged
    NO_RESOLVE = "no_resolve"  # Not resolved
    FLAPPING = "flapping"  # Alert is flapping
    THRESHOLD = "threshold"  # Metric threshold
    MANUAL = "manual"  # Manual escalation
    CUSTOM = "custom"  # Custom trigger


class EscalationAction(Enum):
    """Actions to take on escalation"""
    NOTIFY = "notify"  # Notify additional channels
    REASSIGN = "reassign"  # Reassign to different team
    PAGE = "page"  # Page on-call
    CREATE_TICKET = "create_ticket"  # Create incident ticket
    CALL = "call"  # Phone call
    CUSTOM = "custom"  # Custom action


@dataclass
class EscalationLevel:
    """Escalation level definition"""
    
    level: int  # 1, 2, 3, etc.
    name: str
    description: str = ""
    
    # Trigger conditions
    trigger: EscalationTrigger = EscalationTrigger.TIME
    trigger_minutes: int = 30  # Minutes before escalation
    min_severity: AlertSeverity = AlertSeverity.HIGH
    
    # Actions
    actions: List[EscalationAction] = field(default_factory=list)
    channel_ids: List[str] = field(default_factory=list)  # Channels to notify
    assignee: Optional[str] = None  # Team or user to assign
    
    # Notification
    notify_previous: bool = True  # Also notify previous level
    message_template: Optional[str] = None
    
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger.value,
            "trigger_minutes": self.trigger_minutes,
            "min_severity": self.min_severity.value,
            "actions": [a.value for a in self.actions],
            "channel_ids": self.channel_ids,
            "assignee": self.assignee,
            "notify_previous": self.notify_previous,
            "message_template": self.message_template,
            "enabled": self.enabled,
            "metadata": self.metadata
        }


@dataclass
class EscalationPolicy:
    """Escalation policy definition"""
    
    id: str
    name: str
    description: str = ""
    enabled: bool = True
    
    # Levels
    levels: List[EscalationLevel] = field(default_factory=list)
    
    # Scope
    severities: List[AlertSeverity] = field(default_factory=list)  # Empty = all
    categories: List[str] = field(default_factory=list)  # Empty = all
    sources: List[str] = field(default_factory=list)  # Empty = all
    labels: Dict[str, str] = field(default_factory=dict)  # Required labels
    
    # Lifecycle
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Statistics
    escalation_count: int = 0
    last_escalation_at: Optional[datetime] = None
    
    def applies_to_alert(self, alert: Alert) -> bool:
        """Check if policy applies to alert"""
        if not self.enabled:
            return False
        
        # Severity filter
        if self.severities and alert.severity not in self.severities:
            return False
        
        # Category filter
        if self.categories and alert.category.value not in self.categories:
            return False
        
        # Source filter
        if self.sources and alert.source not in self.sources:
            return False
        
        # Label filter
        for key, value in self.labels.items():
            if alert.labels.get(key) != value:
                return False
        
        return True
    
    def get_next_level(self, current_level: int) -> Optional[EscalationLevel]:
        """Get next escalation level"""
        for level in self.levels:
            if level.level > current_level and level.enabled:
                return level
        return None
    
    def get_level(self, level_num: int) -> Optional[EscalationLevel]:
        """Get specific level"""
        for level in self.levels:
            if level.level == level_num:
                return level
        return None
    
    def should_escalate(self, alert: Alert) -> Optional[EscalationLevel]:
        """Check if alert should be escalated"""
        if not self.applies_to_alert(alert):
            return None
        
        # Get current level
        current_level = alert.escalation_level
        next_level = self.get_next_level(current_level)
        
        if not next_level:
            return None
        
        # Check trigger conditions
        now = datetime.now()
        
        if next_level.trigger == EscalationTrigger.TIME:
            age_minutes = (now - alert.created_at).total_seconds() / 60
            if age_minutes >= next_level.trigger_minutes:
                return next_level
        
        elif next_level.trigger == EscalationTrigger.NO_ACK:
            if alert.status == AlertStatus.ACTIVE:
                age_minutes = (now - alert.created_at).total_seconds() / 60
                if age_minutes >= next_level.trigger_minutes:
                    return next_level
        
        elif next_level.trigger == EscalationTrigger.NO_RESOLVE:
            if alert.status in (AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED):
                age_minutes = (now - alert.created_at).total_seconds() / 60
                if age_minutes >= next_level.trigger_minutes:
                    return next_level
        
        elif next_level.trigger == EscalationTrigger.FLAPPING:
            if alert.is_flapping():
                return next_level
        
        return None
    
    def record_escalation(self) -> None:
        """Record an escalation"""
        self.escalation_count += 1
        self.last_escalation_at = datetime.now()
        self.updated_at = datetime.now()
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "levels": [l.to_dict() for l in self.levels],
            "severities": [s.value for s in self.severities],
            "categories": self.categories,
            "sources": self.sources,
            "labels": self.labels,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "escalation_count": self.escalation_count,
            "last_escalation_at": self.last_escalation_at.isoformat() if self.last_escalation_at else None
        }


class EscalationManager:
    """Manages escalation policies"""
    
    def __init__(self):
        self.policies: Dict[str, EscalationPolicy] = {}
        self._init_builtin_policies()
    
    def _init_builtin_policies(self) -> None:
        """Initialize built-in escalation policies"""
        
        # Critical alert policy
        self.create_policy(
            name="Critical Alerts",
            description="Escalation for critical alerts",
            severities=[AlertSeverity.CRITICAL],
            levels=[
                EscalationLevel(
                    level=1,
                    name="On-Call Engineer",
                    trigger=EscalationTrigger.TIME,
                    trigger_minutes=5,
                    actions=[EscalationAction.NOTIFY, EscalationAction.PAGE]
                ),
                EscalationLevel(
                    level=2,
                    name="Team Lead",
                    trigger=EscalationTrigger.NO_ACK,
                    trigger_minutes=15,
                    actions=[EscalationAction.NOTIFY, EscalationAction.PAGE, EscalationAction.CREATE_TICKET]
                ),
                EscalationLevel(
                    level=3,
                    name="Management",
                    trigger=EscalationTrigger.NO_RESOLVE,
                    trigger_minutes=60,
                    actions=[EscalationAction.NOTIFY, EscalationAction.CALL]
                )
            ]
        )
        
        # High severity policy
        self.create_policy(
            name="High Severity",
            description="Escalation for high severity alerts",
            severities=[AlertSeverity.HIGH],
            levels=[
                EscalationLevel(
                    level=1,
                    name="Team Notification",
                    trigger=EscalationTrigger.TIME,
                    trigger_minutes=15,
                    actions=[EscalationAction.NOTIFY]
                ),
                EscalationLevel(
                    level=2,
                    name="On-Call Page",
                    trigger=EscalationTrigger.NO_ACK,
                    trigger_minutes=30,
                    actions=[EscalationAction.PAGE]
                )
            ]
        )
        
        # Flapping alert policy
        self.create_policy(
            name="Flapping Alerts",
            description="Escalation for flapping alerts",
            levels=[
                EscalationLevel(
                    level=1,
                    name="Flap Detection",
                    trigger=EscalationTrigger.FLAPPING,
                    trigger_minutes=0,
                    actions=[EscalationAction.NOTIFY, EscalationAction.CREATE_TICKET]
                )
            ]
        )
    
    def create_policy(
        self,
        name: str,
        description: str = "",
        enabled: bool = True,
        levels: Optional[List[EscalationLevel]] = None,
        severities: Optional[List[AlertSeverity]] = None,
        categories: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> EscalationPolicy:
        """Create escalation policy"""
        policy_id = f"esc_{uuid.uuid4().hex[:8]}"
        
        policy = EscalationPolicy(
            id=policy_id,
            name=name,
            description=description,
            enabled=enabled,
            levels=levels or [],
            severities=severities or [],
            categories=categories or [],
            sources=sources or [],
            labels=labels or {}
        )
        
        self.policies[policy_id] = policy
        return policy
    
    def get_policy(self, policy_id: str) -> Optional[EscalationPolicy]:
        """Get policy by ID"""
        return self.policies.get(policy_id)
    
    def get_policy_by_name(self, name: str) -> Optional[EscalationPolicy]:
        """Get policy by name"""
        for policy in self.policies.values():
            if policy.name == name:
                return policy
        return None
    
    def update_policy(
        self,
        policy_id: str,
        **kwargs
    ) -> Optional[EscalationPolicy]:
        """Update policy"""
        policy = self.policies.get(policy_id)
        if not policy:
            return None
        
        for key, value in kwargs.items():
            if hasattr(policy, key):
                setattr(policy, key, value)
        
        policy.updated_at = datetime.now()
        return policy
    
    def delete_policy(self, policy_id: str) -> bool:
        """Delete policy"""
        if policy_id in self.policies:
            del self.policies[policy_id]
            return True
        return False
    
    def enable_policy(self, policy_id: str) -> bool:
        """Enable policy"""
        policy = self.policies.get(policy_id)
        if policy:
            policy.enabled = True
            policy.updated_at = datetime.now()
            return True
        return False
    
    def disable_policy(self, policy_id: str) -> bool:
        """Disable policy"""
        policy = self.policies.get(policy_id)
        if policy:
            policy.enabled = False
            policy.updated_at = datetime.now()
            return True
        return False
    
    def add_level(
        self,
        policy_id: str,
        level: EscalationLevel
    ) -> bool:
        """Add level to policy"""
        policy = self.policies.get(policy_id)
        if policy:
            # Check for duplicate level number
            for existing in policy.levels:
                if existing.level == level.level:
                    return False
            policy.levels.append(level)
            policy.levels.sort(key=lambda l: l.level)
            policy.updated_at = datetime.now()
            return True
        return False
    
    def remove_level(
        self,
        policy_id: str,
        level_num: int
    ) -> bool:
        """Remove level from policy"""
        policy = self.policies.get(policy_id)
        if policy:
            policy.levels = [l for l in policy.levels if l.level != level_num]
            policy.updated_at = datetime.now()
            return True
        return False
    
    def check_escalation(
        self,
        alert: Alert
    ) -> Optional[tuple]:
        """Check if alert should be escalated"""
        for policy in self.policies.values():
            if not policy.enabled:
                continue
            
            level = policy.should_escalate(alert)
            if level:
                return (policy, level)
        
        return None
    
    def process_escalation(
        self,
        alert: Alert,
        policy: EscalationPolicy,
        level: EscalationLevel
    ) -> Dict[str, Any]:
        """Process escalation for alert"""
        result = {
            "alert_id": alert.id,
            "policy_id": policy.id,
            "policy_name": policy.name,
            "level": level.level,
            "level_name": level.name,
            "actions": [],
            "timestamp": datetime.now().isoformat()
        }
        
        # Update alert
        alert.escalate(level.level)
        
        # Record on policy
        policy.record_escalation()
        
        # Execute actions (simulated)
        for action in level.actions:
            result["actions"].append({
                "action": action.value,
                "status": "executed"
            })
        
        return result
    
    def get_policies(
        self,
        enabled_only: bool = False,
        severity: Optional[AlertSeverity] = None
    ) -> List[EscalationPolicy]:
        """Get policies with filtering"""
        policies = list(self.policies.values())
        
        if enabled_only:
            policies = [p for p in policies if p.enabled]
        if severity:
            policies = [p for p in policies if not p.severities or severity in p.severities]
        
        return policies
    
    def get_applicable_policies(
        self,
        alert: Alert
    ) -> List[EscalationPolicy]:
        """Get policies that apply to alert"""
        return [p for p in self.policies.values() if p.applies_to_alert(alert)]
    
    def get_statistics(self) -> dict:
        """Get escalation statistics"""
        total_escalations = sum(p.escalation_count for p in self.policies.values())
        
        return {
            "total_policies": len(self.policies),
            "enabled_policies": len([p for p in self.policies.values() if p.enabled]),
            "total_escalations": total_escalations,
            "policies_with_escalations": len([p for p in self.policies.values() if p.escalation_count > 0])
        }


# Global escalation manager instance
_escalation_manager: Optional[EscalationManager] = None


def get_escalation_manager() -> EscalationManager:
    """Get or create the global escalation manager"""
    global _escalation_manager
    if _escalation_manager is None:
        _escalation_manager = EscalationManager()
    return _escalation_manager
