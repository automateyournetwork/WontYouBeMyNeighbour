"""
Tests for Action Executor and Safety
"""

import pytest
import asyncio

from ..actions.executor import ActionExecutor, ActionStatus
from ..actions.safety import SafetyConstraints, ViolationType


class TestSafetyConstraints:
    """Test SafetyConstraints"""

    def test_metric_range_validation(self):
        safety = SafetyConstraints()

        # Valid metric (within 50% change threshold)
        violation = safety.validate_metric_adjustment("eth0", 10, 14)
        assert violation is None

        # Too low
        violation = safety.validate_metric_adjustment("eth0", 10, 0)
        assert violation is not None
        assert violation.violation_type == ViolationType.METRIC_OUT_OF_RANGE

        # Too high
        violation = safety.validate_metric_adjustment("eth0", 10, 100000)
        assert violation is not None
        assert violation.violation_type == ViolationType.METRIC_OUT_OF_RANGE

    def test_critical_interface(self):
        safety = SafetyConstraints()
        safety.add_critical_interface("eth0")

        violation = safety.validate_metric_adjustment("eth0", 10, 20)
        assert violation is not None
        assert violation.violation_type == ViolationType.CRITICAL_INTERFACE

    def test_large_metric_change(self):
        safety = SafetyConstraints()

        # >50% change should trigger warning
        violation = safety.validate_metric_adjustment("eth0", 10, 100)
        assert violation is not None
        assert violation.violation_type == ViolationType.NETWORK_DISRUPTION

    def test_route_injection_limit(self):
        safety = SafetyConstraints()

        # First injection OK
        violation = safety.validate_route_injection("10.0.0.0/24")
        assert violation is not None  # Requires approval by default
        assert violation.violation_type == ViolationType.UNAUTHORIZED_ACTION

    def test_graceful_shutdown(self):
        safety = SafetyConstraints()

        violation = safety.validate_graceful_shutdown("bgp", "all")
        assert violation is not None
        assert violation.violation_type == ViolationType.NETWORK_DISRUPTION
        assert violation.action_blocked

    def test_autonomous_mode(self):
        safety = SafetyConstraints()

        # Not allowed by default
        allowed = safety.is_action_allowed(
            "metric_adjustment",
            {"interface": "eth0", "current_metric": 10, "proposed_metric": 15}
        )
        assert not allowed

        # Enable autonomous mode
        safety.set_autonomous_mode(True)
        allowed = safety.is_action_allowed(
            "metric_adjustment",
            {"interface": "eth0", "current_metric": 10, "proposed_metric": 15}
        )
        assert allowed


class TestActionExecutor:
    """Test ActionExecutor"""

    @pytest.mark.asyncio
    async def test_safe_metric_adjustment(self):
        safety = SafetyConstraints()
        safety.set_autonomous_mode(True)
        executor = ActionExecutor(safety_constraints=safety)

        # Mock OSPF interface
        class MockOSPF:
            pass
        executor.set_protocol_handlers(ospf_interface=MockOSPF())

        result = await executor.execute_action(
            "metric_adjustment",
            {
                "interface": "eth0",
                "current_metric": 10,
                "proposed_metric": 12
            }
        )

        assert result.status == ActionStatus.COMPLETED
        assert result.error is None

    @pytest.mark.asyncio
    async def test_blocked_action(self):
        safety = SafetyConstraints()
        executor = ActionExecutor(safety_constraints=safety)

        result = await executor.execute_action(
            "metric_adjustment",
            {
                "interface": "eth0",
                "current_metric": 10,
                "proposed_metric": 100000  # Out of range
            }
        )

        assert result.status == ActionStatus.BLOCKED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_action_history(self):
        safety = SafetyConstraints()
        safety.set_autonomous_mode(True)
        executor = ActionExecutor(safety_constraints=safety)

        # Mock OSPF interface
        class MockOSPF:
            pass
        executor.set_protocol_handlers(ospf_interface=MockOSPF())

        await executor.execute_action(
            "metric_adjustment",
            {"interface": "eth0", "current_metric": 10, "proposed_metric": 12}
        )

        await executor.execute_action(
            "metric_adjustment",
            {"interface": "eth1", "current_metric": 20, "proposed_metric": 22}
        )

        history = executor.get_action_history(limit=10)
        assert len(history) >= 2

    @pytest.mark.asyncio
    async def test_skip_safety(self):
        safety = SafetyConstraints()
        executor = ActionExecutor(safety_constraints=safety)

        # Mock OSPF interface
        class MockOSPF:
            pass
        executor.set_protocol_handlers(ospf_interface=MockOSPF())

        # Should be blocked normally
        result = await executor.execute_action(
            "metric_adjustment",
            {"interface": "eth0", "current_metric": 10, "proposed_metric": 12}
        )
        assert result.status == ActionStatus.BLOCKED

        # Should work with skip_safety
        result = await executor.execute_action(
            "metric_adjustment",
            {"interface": "eth0", "current_metric": 10, "proposed_metric": 12},
            skip_safety=True
        )
        assert result.status == ActionStatus.COMPLETED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
