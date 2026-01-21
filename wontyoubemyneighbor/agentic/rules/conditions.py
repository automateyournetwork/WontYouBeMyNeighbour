"""
Rule Conditions

Provides:
- Condition definitions
- Condition operators
- Condition evaluation
- Condition grouping
"""

import uuid
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum


class ConditionType(Enum):
    """Types of conditions"""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES = "matches"  # Regex
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"
    BETWEEN = "between"
    NOT_BETWEEN = "not_between"
    EXISTS = "exists"
    CUSTOM = "custom"


class LogicalOperator(Enum):
    """Logical operators for combining conditions"""
    AND = "and"
    OR = "or"
    NOT = "not"
    XOR = "xor"
    NAND = "nand"
    NOR = "nor"


@dataclass
class Condition:
    """Rule condition"""

    id: str
    name: str
    condition_type: ConditionType
    field: str  # Field/path to evaluate
    value: Any = None  # Value to compare
    value2: Any = None  # Second value (for BETWEEN)
    case_sensitive: bool = True
    description: str = ""
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)

    # Statistics
    evaluation_count: int = 0
    true_count: int = 0
    false_count: int = 0

    def get_field_value(self, context: Dict[str, Any]) -> Any:
        """Get field value from context using dot notation"""
        parts = self.field.split(".")
        value = context

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                return None

            if value is None:
                return None

        return value

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate condition against context"""
        if not self.enabled:
            return True

        field_value = self.get_field_value(context)
        compare_value = self.value
        self.evaluation_count += 1

        result = self._evaluate_condition(field_value, compare_value)

        if result:
            self.true_count += 1
        else:
            self.false_count += 1

        return result

    def _evaluate_condition(self, field_value: Any, compare_value: Any) -> bool:
        """Internal condition evaluation"""
        # Handle string case sensitivity
        if not self.case_sensitive and isinstance(field_value, str):
            field_value = field_value.lower()
            if isinstance(compare_value, str):
                compare_value = compare_value.lower()

        if self.condition_type == ConditionType.EQUALS:
            return field_value == compare_value
        elif self.condition_type == ConditionType.NOT_EQUALS:
            return field_value != compare_value
        elif self.condition_type == ConditionType.GREATER_THAN:
            return field_value > compare_value if field_value is not None and compare_value is not None else False
        elif self.condition_type == ConditionType.LESS_THAN:
            return field_value < compare_value if field_value is not None and compare_value is not None else False
        elif self.condition_type == ConditionType.GREATER_EQUAL:
            return field_value >= compare_value if field_value is not None and compare_value is not None else False
        elif self.condition_type == ConditionType.LESS_EQUAL:
            return field_value <= compare_value if field_value is not None and compare_value is not None else False
        elif self.condition_type == ConditionType.CONTAINS:
            if isinstance(field_value, str):
                return compare_value in field_value
            elif isinstance(field_value, (list, tuple, set)):
                return compare_value in field_value
            return False
        elif self.condition_type == ConditionType.NOT_CONTAINS:
            if isinstance(field_value, str):
                return compare_value not in field_value
            elif isinstance(field_value, (list, tuple, set)):
                return compare_value not in field_value
            return True
        elif self.condition_type == ConditionType.STARTS_WITH:
            return str(field_value).startswith(str(compare_value)) if field_value is not None else False
        elif self.condition_type == ConditionType.ENDS_WITH:
            return str(field_value).endswith(str(compare_value)) if field_value is not None else False
        elif self.condition_type == ConditionType.MATCHES:
            try:
                return bool(re.match(str(compare_value), str(field_value))) if field_value is not None else False
            except re.error:
                return False
        elif self.condition_type == ConditionType.IN:
            return field_value in compare_value if isinstance(compare_value, (list, tuple, set)) else False
        elif self.condition_type == ConditionType.NOT_IN:
            return field_value not in compare_value if isinstance(compare_value, (list, tuple, set)) else True
        elif self.condition_type == ConditionType.IS_NULL:
            return field_value is None
        elif self.condition_type == ConditionType.IS_NOT_NULL:
            return field_value is not None
        elif self.condition_type == ConditionType.IS_TRUE:
            return bool(field_value) is True
        elif self.condition_type == ConditionType.IS_FALSE:
            return bool(field_value) is False
        elif self.condition_type == ConditionType.BETWEEN:
            if field_value is None or self.value is None or self.value2 is None:
                return False
            return self.value <= field_value <= self.value2
        elif self.condition_type == ConditionType.NOT_BETWEEN:
            if field_value is None or self.value is None or self.value2 is None:
                return True
            return not (self.value <= field_value <= self.value2)
        elif self.condition_type == ConditionType.EXISTS:
            return field_value is not None
        elif self.condition_type == ConditionType.CUSTOM:
            # Custom conditions need external handler
            return True

        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "condition_type": self.condition_type.value,
            "field": self.field,
            "value": self.value,
            "value2": self.value2,
            "case_sensitive": self.case_sensitive,
            "description": self.description,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags,
            "evaluation_count": self.evaluation_count,
            "true_count": self.true_count,
            "false_count": self.false_count,
            "true_rate": self.true_count / self.evaluation_count if self.evaluation_count > 0 else 0.0
        }


@dataclass
class ConditionGroup:
    """Group of conditions with logical operator"""

    id: str
    name: str
    operator: LogicalOperator
    conditions: List[str] = field(default_factory=list)  # Condition IDs
    groups: List[str] = field(default_factory=list)  # Nested group IDs
    description: str = ""
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "operator": self.operator.value,
            "conditions": self.conditions,
            "groups": self.groups,
            "description": self.description,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat()
        }


class ConditionManager:
    """Manages rule conditions"""

    def __init__(self):
        self.conditions: Dict[str, Condition] = {}
        self.groups: Dict[str, ConditionGroup] = {}
        self._custom_evaluators: Dict[str, Callable] = {}
        self._init_builtin_conditions()

    def _init_builtin_conditions(self) -> None:
        """Initialize built-in condition templates"""
        # Network-specific conditions
        self.create_condition(
            name="Interface Up",
            condition_type=ConditionType.EQUALS,
            field="interface.status",
            value="up",
            description="Check if interface is up",
            tags=["network", "interface"]
        )

        self.create_condition(
            name="OSPF Neighbor Full",
            condition_type=ConditionType.EQUALS,
            field="ospf.neighbor.state",
            value="Full",
            description="Check if OSPF neighbor is in Full state",
            tags=["ospf", "neighbor"]
        )

        self.create_condition(
            name="BGP Peer Established",
            condition_type=ConditionType.EQUALS,
            field="bgp.peer.state",
            value="Established",
            description="Check if BGP peer is established",
            tags=["bgp", "peer"]
        )

        self.create_condition(
            name="High CPU",
            condition_type=ConditionType.GREATER_THAN,
            field="system.cpu_percent",
            value=80,
            description="Check for high CPU utilization",
            tags=["system", "performance"]
        )

        self.create_condition(
            name="Low Memory",
            condition_type=ConditionType.LESS_THAN,
            field="system.memory_available_mb",
            value=100,
            description="Check for low available memory",
            tags=["system", "performance"]
        )

        self.create_condition(
            name="Route Count Threshold",
            condition_type=ConditionType.GREATER_THAN,
            field="routing.route_count",
            value=10000,
            description="Check if route count exceeds threshold",
            tags=["routing"]
        )

    def register_custom_evaluator(
        self,
        name: str,
        evaluator: Callable
    ) -> None:
        """Register a custom condition evaluator"""
        self._custom_evaluators[name] = evaluator

    def get_custom_evaluator(self, name: str) -> Optional[Callable]:
        """Get custom evaluator by name"""
        return self._custom_evaluators.get(name)

    def create_condition(
        self,
        name: str,
        condition_type: ConditionType,
        field: str,
        value: Any = None,
        value2: Any = None,
        case_sensitive: bool = True,
        description: str = "",
        tags: Optional[List[str]] = None
    ) -> Condition:
        """Create a new condition"""
        condition_id = f"cond_{uuid.uuid4().hex[:8]}"

        condition = Condition(
            id=condition_id,
            name=name,
            condition_type=condition_type,
            field=field,
            value=value,
            value2=value2,
            case_sensitive=case_sensitive,
            description=description,
            tags=tags or []
        )

        self.conditions[condition_id] = condition
        return condition

    def get_condition(self, condition_id: str) -> Optional[Condition]:
        """Get condition by ID"""
        return self.conditions.get(condition_id)

    def get_condition_by_name(self, name: str) -> Optional[Condition]:
        """Get condition by name"""
        for condition in self.conditions.values():
            if condition.name == name:
                return condition
        return None

    def update_condition(
        self,
        condition_id: str,
        **kwargs
    ) -> Optional[Condition]:
        """Update condition properties"""
        condition = self.conditions.get(condition_id)
        if not condition:
            return None

        for key, value in kwargs.items():
            if hasattr(condition, key):
                setattr(condition, key, value)

        return condition

    def delete_condition(self, condition_id: str) -> bool:
        """Delete a condition"""
        if condition_id in self.conditions:
            del self.conditions[condition_id]
            return True
        return False

    def enable_condition(self, condition_id: str) -> bool:
        """Enable a condition"""
        condition = self.conditions.get(condition_id)
        if condition:
            condition.enabled = True
            return True
        return False

    def disable_condition(self, condition_id: str) -> bool:
        """Disable a condition"""
        condition = self.conditions.get(condition_id)
        if condition:
            condition.enabled = False
            return True
        return False

    def create_group(
        self,
        name: str,
        operator: LogicalOperator,
        condition_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        description: str = ""
    ) -> ConditionGroup:
        """Create a condition group"""
        group_id = f"grp_{uuid.uuid4().hex[:8]}"

        group = ConditionGroup(
            id=group_id,
            name=name,
            operator=operator,
            conditions=condition_ids or [],
            groups=group_ids or [],
            description=description
        )

        self.groups[group_id] = group
        return group

    def get_group(self, group_id: str) -> Optional[ConditionGroup]:
        """Get group by ID"""
        return self.groups.get(group_id)

    def delete_group(self, group_id: str) -> bool:
        """Delete a group"""
        if group_id in self.groups:
            del self.groups[group_id]
            return True
        return False

    def add_condition_to_group(
        self,
        group_id: str,
        condition_id: str
    ) -> bool:
        """Add condition to group"""
        group = self.groups.get(group_id)
        if not group:
            return False

        if condition_id not in group.conditions:
            group.conditions.append(condition_id)

        return True

    def remove_condition_from_group(
        self,
        group_id: str,
        condition_id: str
    ) -> bool:
        """Remove condition from group"""
        group = self.groups.get(group_id)
        if not group:
            return False

        if condition_id in group.conditions:
            group.conditions.remove(condition_id)

        return True

    def evaluate_condition(
        self,
        condition_id: str,
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate a single condition"""
        condition = self.conditions.get(condition_id)
        if not condition:
            return False

        return condition.evaluate(context)

    def evaluate_group(
        self,
        group_id: str,
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate a condition group"""
        group = self.groups.get(group_id)
        if not group or not group.enabled:
            return True

        results = []

        # Evaluate conditions
        for cond_id in group.conditions:
            results.append(self.evaluate_condition(cond_id, context))

        # Evaluate nested groups
        for nested_id in group.groups:
            results.append(self.evaluate_group(nested_id, context))

        if not results:
            return True

        # Apply logical operator
        if group.operator == LogicalOperator.AND:
            return all(results)
        elif group.operator == LogicalOperator.OR:
            return any(results)
        elif group.operator == LogicalOperator.NOT:
            return not results[0] if results else True
        elif group.operator == LogicalOperator.XOR:
            return sum(results) == 1
        elif group.operator == LogicalOperator.NAND:
            return not all(results)
        elif group.operator == LogicalOperator.NOR:
            return not any(results)

        return True

    def get_conditions(
        self,
        condition_type: Optional[ConditionType] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[Condition]:
        """Get conditions with filtering"""
        conditions = list(self.conditions.values())

        if condition_type:
            conditions = [c for c in conditions if c.condition_type == condition_type]
        if enabled_only:
            conditions = [c for c in conditions if c.enabled]
        if tag:
            conditions = [c for c in conditions if tag in c.tags]

        return conditions

    def get_groups(self, operator: Optional[LogicalOperator] = None) -> List[ConditionGroup]:
        """Get groups with filtering"""
        groups = list(self.groups.values())

        if operator:
            groups = [g for g in groups if g.operator == operator]

        return groups

    def get_statistics(self) -> dict:
        """Get condition statistics"""
        total_evaluations = 0
        total_true = 0
        total_false = 0
        by_type = {}

        for condition in self.conditions.values():
            total_evaluations += condition.evaluation_count
            total_true += condition.true_count
            total_false += condition.false_count
            by_type[condition.condition_type.value] = by_type.get(condition.condition_type.value, 0) + 1

        return {
            "total_conditions": len(self.conditions),
            "enabled_conditions": len([c for c in self.conditions.values() if c.enabled]),
            "total_groups": len(self.groups),
            "total_evaluations": total_evaluations,
            "total_true": total_true,
            "total_false": total_false,
            "true_rate": total_true / total_evaluations if total_evaluations > 0 else 0.0,
            "by_type": by_type,
            "custom_evaluators": len(self._custom_evaluators)
        }


# Global condition manager instance
_condition_manager: Optional[ConditionManager] = None


def get_condition_manager() -> ConditionManager:
    """Get or create the global condition manager"""
    global _condition_manager
    if _condition_manager is None:
        _condition_manager = ConditionManager()
    return _condition_manager
