"""
Rules Engine

Provides:
- Rule definitions
- Rule sets
- Rule evaluation and execution
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from .conditions import (
    Condition,
    ConditionGroup,
    ConditionManager,
    get_condition_manager
)
from .actions import (
    Action,
    ActionResult,
    ActionStatus,
    ActionManager,
    get_action_manager
)


class RulePriority(Enum):
    """Rule priority levels"""
    LOWEST = 1
    LOW = 2
    NORMAL = 3
    HIGH = 4
    HIGHEST = 5
    CRITICAL = 6


class RuleStatus(Enum):
    """Rule execution status"""
    NOT_EVALUATED = "not_evaluated"
    EVALUATING = "evaluating"
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RuleConfig:
    """Rule configuration"""

    stop_on_match: bool = False  # Stop evaluating other rules
    stop_on_failure: bool = False  # Stop on action failure
    require_all_conditions: bool = True  # AND vs OR for conditions
    max_executions: int = 0  # 0 = unlimited
    cooldown_seconds: int = 0  # Cooldown between executions
    execution_window_start: Optional[str] = None  # Time window start (HH:MM)
    execution_window_end: Optional[str] = None  # Time window end (HH:MM)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "stop_on_match": self.stop_on_match,
            "stop_on_failure": self.stop_on_failure,
            "require_all_conditions": self.require_all_conditions,
            "max_executions": self.max_executions,
            "cooldown_seconds": self.cooldown_seconds,
            "execution_window_start": self.execution_window_start,
            "execution_window_end": self.execution_window_end,
            "extra": self.extra
        }


@dataclass
class RuleResult:
    """Result of rule evaluation"""

    rule_id: str
    status: RuleStatus
    matched: bool = False
    action_results: List[ActionResult] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "status": self.status.value,
            "matched": self.matched,
            "action_results": [r.to_dict() for r in self.action_results],
            "evaluated_at": self.evaluated_at.isoformat(),
            "duration_ms": self.duration_ms,
            "error": self.error
        }


@dataclass
class Rule:
    """Rule definition"""

    id: str
    name: str
    description: str = ""
    priority: RulePriority = RulePriority.NORMAL
    config: RuleConfig = field(default_factory=RuleConfig)
    condition_ids: List[str] = field(default_factory=list)  # Condition IDs
    condition_group_id: Optional[str] = None  # Optional condition group
    action_ids: List[str] = field(default_factory=list)  # Action IDs (when matched)
    else_action_ids: List[str] = field(default_factory=list)  # Action IDs (when not matched)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Statistics
    evaluation_count: int = 0
    match_count: int = 0
    execution_count: int = 0
    failure_count: int = 0
    last_evaluated_at: Optional[datetime] = None
    last_matched_at: Optional[datetime] = None
    last_status: Optional[RuleStatus] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority.value,
            "config": self.config.to_dict(),
            "condition_ids": self.condition_ids,
            "condition_group_id": self.condition_group_id,
            "action_ids": self.action_ids,
            "else_action_ids": self.else_action_ids,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags,
            "metadata": self.metadata,
            "evaluation_count": self.evaluation_count,
            "match_count": self.match_count,
            "execution_count": self.execution_count,
            "failure_count": self.failure_count,
            "last_evaluated_at": self.last_evaluated_at.isoformat() if self.last_evaluated_at else None,
            "last_matched_at": self.last_matched_at.isoformat() if self.last_matched_at else None,
            "last_status": self.last_status.value if self.last_status else None,
            "match_rate": self.match_count / self.evaluation_count if self.evaluation_count > 0 else 0.0
        }


@dataclass
class RuleSet:
    """Collection of rules"""

    id: str
    name: str
    description: str = ""
    rule_ids: List[str] = field(default_factory=list)
    enabled: bool = True
    evaluate_all: bool = False  # Evaluate all rules even after match
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)

    # Statistics
    evaluation_count: int = 0
    last_evaluated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "rule_ids": self.rule_ids,
            "enabled": self.enabled,
            "evaluate_all": self.evaluate_all,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags,
            "evaluation_count": self.evaluation_count,
            "last_evaluated_at": self.last_evaluated_at.isoformat() if self.last_evaluated_at else None
        }


class RuleEngine:
    """Rules engine for policy evaluation"""

    def __init__(self):
        self.rules: Dict[str, Rule] = {}
        self.rule_sets: Dict[str, RuleSet] = {}
        self._condition_manager = get_condition_manager()
        self._action_manager = get_action_manager()
        self._init_builtin_rules()

    def _init_builtin_rules(self) -> None:
        """Initialize built-in rules"""

        # Network health rules
        self.create_rule(
            name="High CPU Alert",
            description="Alert when CPU usage exceeds threshold",
            priority=RulePriority.HIGH,
            tags=["system", "performance", "alert"]
        )

        self.create_rule(
            name="Interface Down Alert",
            description="Alert when interface goes down",
            priority=RulePriority.CRITICAL,
            tags=["network", "interface", "alert"]
        )

        self.create_rule(
            name="BGP Peer Down",
            description="Handle BGP peer down event",
            priority=RulePriority.CRITICAL,
            tags=["bgp", "peer", "alert"]
        )

        self.create_rule(
            name="OSPF Neighbor Lost",
            description="Handle OSPF neighbor loss",
            priority=RulePriority.HIGH,
            tags=["ospf", "neighbor", "alert"]
        )

        self.create_rule(
            name="Route Table Full",
            description="Alert when route table nears capacity",
            priority=RulePriority.HIGH,
            tags=["routing", "capacity", "alert"]
        )

        # Security rules
        self.create_rule(
            name="Unauthorized Access",
            description="Block unauthorized access attempts",
            priority=RulePriority.CRITICAL,
            tags=["security", "access"]
        )

        # Create default rule set
        self.create_rule_set(
            name="Default Rules",
            description="Default rule set for all evaluations",
            rule_ids=[r.id for r in list(self.rules.values())[:3]],
            tags=["default"]
        )

    def create_rule(
        self,
        name: str,
        description: str = "",
        priority: RulePriority = RulePriority.NORMAL,
        config: Optional[RuleConfig] = None,
        condition_ids: Optional[List[str]] = None,
        condition_group_id: Optional[str] = None,
        action_ids: Optional[List[str]] = None,
        else_action_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Rule:
        """Create a new rule"""
        rule_id = f"rule_{uuid.uuid4().hex[:8]}"

        rule = Rule(
            id=rule_id,
            name=name,
            description=description,
            priority=priority,
            config=config or RuleConfig(),
            condition_ids=condition_ids or [],
            condition_group_id=condition_group_id,
            action_ids=action_ids or [],
            else_action_ids=else_action_ids or [],
            tags=tags or [],
            metadata=metadata or {}
        )

        self.rules[rule_id] = rule
        return rule

    def get_rule(self, rule_id: str) -> Optional[Rule]:
        """Get rule by ID"""
        return self.rules.get(rule_id)

    def get_rule_by_name(self, name: str) -> Optional[Rule]:
        """Get rule by name"""
        for rule in self.rules.values():
            if rule.name == name:
                return rule
        return None

    def update_rule(
        self,
        rule_id: str,
        **kwargs
    ) -> Optional[Rule]:
        """Update rule properties"""
        rule = self.rules.get(rule_id)
        if not rule:
            return None

        for key, value in kwargs.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        return rule

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False

    def enable_rule(self, rule_id: str) -> bool:
        """Enable a rule"""
        rule = self.rules.get(rule_id)
        if rule:
            rule.enabled = True
            return True
        return False

    def disable_rule(self, rule_id: str) -> bool:
        """Disable a rule"""
        rule = self.rules.get(rule_id)
        if rule:
            rule.enabled = False
            return True
        return False

    def add_condition(
        self,
        rule_id: str,
        condition_id: str
    ) -> bool:
        """Add condition to rule"""
        rule = self.rules.get(rule_id)
        if not rule:
            return False

        if condition_id not in rule.condition_ids:
            rule.condition_ids.append(condition_id)

        return True

    def remove_condition(
        self,
        rule_id: str,
        condition_id: str
    ) -> bool:
        """Remove condition from rule"""
        rule = self.rules.get(rule_id)
        if not rule:
            return False

        if condition_id in rule.condition_ids:
            rule.condition_ids.remove(condition_id)

        return True

    def add_action(
        self,
        rule_id: str,
        action_id: str
    ) -> bool:
        """Add action to rule"""
        rule = self.rules.get(rule_id)
        if not rule:
            return False

        if action_id not in rule.action_ids:
            rule.action_ids.append(action_id)

        return True

    def remove_action(
        self,
        rule_id: str,
        action_id: str
    ) -> bool:
        """Remove action from rule"""
        rule = self.rules.get(rule_id)
        if not rule:
            return False

        if action_id in rule.action_ids:
            rule.action_ids.remove(action_id)

        return True

    def create_rule_set(
        self,
        name: str,
        description: str = "",
        rule_ids: Optional[List[str]] = None,
        evaluate_all: bool = False,
        tags: Optional[List[str]] = None
    ) -> RuleSet:
        """Create a new rule set"""
        rule_set_id = f"rs_{uuid.uuid4().hex[:8]}"

        rule_set = RuleSet(
            id=rule_set_id,
            name=name,
            description=description,
            rule_ids=rule_ids or [],
            evaluate_all=evaluate_all,
            tags=tags or []
        )

        self.rule_sets[rule_set_id] = rule_set
        return rule_set

    def get_rule_set(self, rule_set_id: str) -> Optional[RuleSet]:
        """Get rule set by ID"""
        return self.rule_sets.get(rule_set_id)

    def delete_rule_set(self, rule_set_id: str) -> bool:
        """Delete a rule set"""
        if rule_set_id in self.rule_sets:
            del self.rule_sets[rule_set_id]
            return True
        return False

    def add_rule_to_set(
        self,
        rule_set_id: str,
        rule_id: str
    ) -> bool:
        """Add rule to rule set"""
        rule_set = self.rule_sets.get(rule_set_id)
        if not rule_set:
            return False

        if rule_id not in rule_set.rule_ids:
            rule_set.rule_ids.append(rule_id)

        return True

    def remove_rule_from_set(
        self,
        rule_set_id: str,
        rule_id: str
    ) -> bool:
        """Remove rule from rule set"""
        rule_set = self.rule_sets.get(rule_set_id)
        if not rule_set:
            return False

        if rule_id in rule_set.rule_ids:
            rule_set.rule_ids.remove(rule_id)

        return True

    def evaluate_rule(
        self,
        rule_id: str,
        context: Dict[str, Any]
    ) -> RuleResult:
        """Evaluate a single rule"""
        rule = self.rules.get(rule_id)
        if not rule:
            return RuleResult(
                rule_id=rule_id,
                status=RuleStatus.FAILED,
                error="Rule not found"
            )

        if not rule.enabled:
            return RuleResult(
                rule_id=rule_id,
                status=RuleStatus.SKIPPED,
                matched=False
            )

        start_time = datetime.now()
        rule.evaluation_count += 1
        rule.last_evaluated_at = start_time

        try:
            # Evaluate conditions
            matched = self._evaluate_conditions(rule, context)

            # Execute actions
            action_results = []
            if matched:
                rule.match_count += 1
                rule.last_matched_at = datetime.now()
                if rule.action_ids:
                    action_results = self._action_manager.execute_actions(rule.action_ids, context)
            else:
                if rule.else_action_ids:
                    action_results = self._action_manager.execute_actions(rule.else_action_ids, context)

            # Check for failures
            has_failure = any(r.status == ActionStatus.FAILED for r in action_results)
            if has_failure:
                rule.failure_count += 1

            rule.execution_count += 1
            end_time = datetime.now()

            status = RuleStatus.EXECUTED if matched else RuleStatus.NOT_MATCHED
            if has_failure:
                status = RuleStatus.FAILED

            rule.last_status = status

            return RuleResult(
                rule_id=rule_id,
                status=status,
                matched=matched,
                action_results=action_results,
                evaluated_at=start_time,
                duration_ms=(end_time - start_time).total_seconds() * 1000
            )

        except Exception as e:
            rule.failure_count += 1
            rule.last_status = RuleStatus.FAILED
            return RuleResult(
                rule_id=rule_id,
                status=RuleStatus.FAILED,
                matched=False,
                error=str(e),
                evaluated_at=start_time,
                duration_ms=(datetime.now() - start_time).total_seconds() * 1000
            )

    def _evaluate_conditions(self, rule: Rule, context: Dict[str, Any]) -> bool:
        """Evaluate rule conditions"""
        # If condition group specified, use it
        if rule.condition_group_id:
            return self._condition_manager.evaluate_group(rule.condition_group_id, context)

        # Otherwise evaluate individual conditions
        if not rule.condition_ids:
            return True

        results = []
        for cond_id in rule.condition_ids:
            results.append(self._condition_manager.evaluate_condition(cond_id, context))

        if rule.config.require_all_conditions:
            return all(results)
        else:
            return any(results)

    def evaluate_rule_set(
        self,
        rule_set_id: str,
        context: Dict[str, Any]
    ) -> List[RuleResult]:
        """Evaluate a rule set"""
        rule_set = self.rule_sets.get(rule_set_id)
        if not rule_set or not rule_set.enabled:
            return []

        rule_set.evaluation_count += 1
        rule_set.last_evaluated_at = datetime.now()

        results = []

        # Get and sort rules by priority
        rules = [
            self.rules.get(rid)
            for rid in rule_set.rule_ids
            if self.rules.get(rid) and self.rules.get(rid).enabled
        ]
        rules.sort(key=lambda r: r.priority.value, reverse=True)

        for rule in rules:
            result = self.evaluate_rule(rule.id, context)
            results.append(result)

            # Check stop conditions
            if not rule_set.evaluate_all:
                if result.matched and rule.config.stop_on_match:
                    break
                if result.status == RuleStatus.FAILED and rule.config.stop_on_failure:
                    break

        return results

    def evaluate_all(
        self,
        context: Dict[str, Any],
        tags: Optional[List[str]] = None
    ) -> List[RuleResult]:
        """Evaluate all enabled rules"""
        rules = list(self.rules.values())

        # Filter by tags
        if tags:
            rules = [r for r in rules if any(t in r.tags for t in tags)]

        # Filter enabled and sort by priority
        rules = [r for r in rules if r.enabled]
        rules.sort(key=lambda r: r.priority.value, reverse=True)

        results = []
        for rule in rules:
            result = self.evaluate_rule(rule.id, context)
            results.append(result)

        return results

    def get_rules(
        self,
        priority: Optional[RulePriority] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[Rule]:
        """Get rules with filtering"""
        rules = list(self.rules.values())

        if priority:
            rules = [r for r in rules if r.priority == priority]
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        if tag:
            rules = [r for r in rules if tag in r.tags]

        return rules

    def get_rule_sets(
        self,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[RuleSet]:
        """Get rule sets with filtering"""
        rule_sets = list(self.rule_sets.values())

        if enabled_only:
            rule_sets = [rs for rs in rule_sets if rs.enabled]
        if tag:
            rule_sets = [rs for rs in rule_sets if tag in rs.tags]

        return rule_sets

    def get_statistics(self) -> dict:
        """Get engine statistics"""
        total_evaluations = 0
        total_matches = 0
        total_executions = 0
        total_failures = 0
        by_priority = {}

        for rule in self.rules.values():
            total_evaluations += rule.evaluation_count
            total_matches += rule.match_count
            total_executions += rule.execution_count
            total_failures += rule.failure_count
            by_priority[rule.priority.value] = by_priority.get(rule.priority.value, 0) + 1

        return {
            "total_rules": len(self.rules),
            "enabled_rules": len([r for r in self.rules.values() if r.enabled]),
            "total_rule_sets": len(self.rule_sets),
            "enabled_rule_sets": len([rs for rs in self.rule_sets.values() if rs.enabled]),
            "total_evaluations": total_evaluations,
            "total_matches": total_matches,
            "total_executions": total_executions,
            "total_failures": total_failures,
            "match_rate": total_matches / total_evaluations if total_evaluations > 0 else 0.0,
            "by_priority": by_priority,
            "condition_stats": self._condition_manager.get_statistics(),
            "action_stats": self._action_manager.get_statistics()
        }


# Global rule engine instance
_rule_engine: Optional[RuleEngine] = None


def get_rule_engine() -> RuleEngine:
    """Get or create the global rule engine"""
    global _rule_engine
    if _rule_engine is None:
        _rule_engine = RuleEngine()
    return _rule_engine
