"""Tests for rules engine module"""

import pytest
from agentic.rules import (
    Condition, ConditionType, ConditionGroup, LogicalOperator, ConditionManager, get_condition_manager,
    Action, ActionType, ActionConfig, ActionManager, get_action_manager,
    Rule, RuleConfig, RuleSet, RuleEngine, get_rule_engine
)


class TestConditionManager:
    """Tests for ConditionManager"""

    def test_create_condition(self):
        """Test condition creation"""
        manager = ConditionManager()
        condition = manager.create_condition(
            name="test-condition",
            condition_type=ConditionType.EQUALS,
            field="status",
            value="active"
        )
        assert condition.name == "test-condition"
        assert condition.condition_type == ConditionType.EQUALS

    def test_get_condition(self):
        """Test getting condition by ID"""
        manager = ConditionManager()
        condition = manager.create_condition("test", ConditionType.GREATER_THAN, "count", 5)

        retrieved = manager.get_condition(condition.id)
        assert retrieved is not None
        assert retrieved.id == condition.id


class TestActionManager:
    """Tests for ActionManager"""

    def test_create_action(self):
        """Test action creation"""
        manager = ActionManager()
        action = manager.create_action(
            name="test-action",
            action_type=ActionType.LOG,
            description="Test action"
        )
        assert action.name == "test-action"
        assert action.action_type == ActionType.LOG

    def test_get_action(self):
        """Test getting action by ID"""
        manager = ActionManager()
        action = manager.create_action("test", ActionType.ALERT)

        retrieved = manager.get_action(action.id)
        assert retrieved is not None
        assert retrieved.id == action.id


class TestRuleEngine:
    """Tests for RuleEngine"""

    def test_create_rule(self):
        """Test rule creation"""
        engine = RuleEngine()
        rule = engine.create_rule(
            name="test-rule",
            description="Test rule"
        )
        assert rule.name == "test-rule"
        assert rule.enabled

    def test_enable_disable_rule(self):
        """Test rule enable/disable"""
        engine = RuleEngine()
        rule = engine.create_rule("test")

        assert engine.disable_rule(rule.id)
        assert not rule.enabled

        assert engine.enable_rule(rule.id)
        assert rule.enabled

    def test_builtin_rules_exist(self):
        """Test built-in rules are created"""
        engine = RuleEngine()
        assert len(engine.rules) >= 6  # At least 6 built-in rules


class TestConditionType:
    """Tests for ConditionType enum"""

    def test_condition_types_exist(self):
        """Test condition types are defined"""
        assert hasattr(ConditionType, "EQUALS")
        assert hasattr(ConditionType, "NOT_EQUALS")
        assert hasattr(ConditionType, "GREATER_THAN")
        assert hasattr(ConditionType, "LESS_THAN")
        assert hasattr(ConditionType, "CONTAINS")
        assert hasattr(ConditionType, "MATCHES")


class TestActionType:
    """Tests for ActionType enum"""

    def test_action_types_exist(self):
        """Test action types are defined"""
        assert hasattr(ActionType, "LOG")
        assert hasattr(ActionType, "ALERT")
        assert hasattr(ActionType, "EMAIL")
        assert hasattr(ActionType, "WEBHOOK")
        assert hasattr(ActionType, "SCRIPT")
