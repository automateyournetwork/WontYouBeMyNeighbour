"""
Example usage of Action Executor

Demonstrates safe action execution with human approval workflow.
"""

import asyncio
from .executor import ActionExecutor, ActionStatus
from .safety import SafetyConstraints


async def mock_approval_callback(action_result):
    """
    Mock approval callback - in real system, this would prompt human.
    """
    print(f"\n{'='*60}")
    print(f"ACTION REQUIRES APPROVAL")
    print(f"{'='*60}")
    print(f"Action ID: {action_result.action_id}")
    print(f"Type: {action_result.action_type}")
    print(f"Parameters: {action_result.parameters}")
    if action_result.safety_violation:
        print(f"Safety Warning: {action_result.safety_violation.message}")
    print(f"{'='*60}")

    # Auto-approve for demo
    print("Auto-approving for demo...")
    return True


async def example_safe_actions():
    """Example: Safe actions that execute autonomously"""
    print("=" * 60)
    print("Example: Safe Actions (Autonomous)")
    print("=" * 60)

    # Create executor with autonomous mode
    safety = SafetyConstraints()
    safety.set_autonomous_mode(True)
    executor = ActionExecutor(safety_constraints=safety)

    # Small metric adjustment (allowed)
    result = await executor.execute_action(
        action_type="metric_adjustment",
        parameters={
            "interface": "eth0",
            "current_metric": 10,
            "proposed_metric": 12  # 20% change - safe
        }
    )

    print(f"\nAction: {result.action_type}")
    print(f"Status: {result.status.value}")
    if result.status == ActionStatus.COMPLETED:
        print(f"Result: {result.result}")
    print(f"Execution time: {result.execution_time_ms:.2f}ms")


async def example_unsafe_actions():
    """Example: Unsafe actions requiring approval"""
    print("\n" + "=" * 60)
    print("Example: Unsafe Actions (Require Approval)")
    print("=" * 60)

    # Create executor with approval callback
    safety = SafetyConstraints()
    executor = ActionExecutor(
        safety_constraints=safety,
        approval_callback=mock_approval_callback
    )

    # Large metric change (requires approval)
    result = await executor.execute_action(
        action_type="metric_adjustment",
        parameters={
            "interface": "eth0",
            "current_metric": 10,
            "proposed_metric": 50  # 400% change - requires approval
        }
    )

    print(f"\nAction: {result.action_type}")
    print(f"Status: {result.status.value}")
    if result.safety_violation:
        print(f"Safety: {result.safety_violation.message}")


async def example_blocked_actions():
    """Example: Actions blocked by safety constraints"""
    print("\n" + "=" * 60)
    print("Example: Blocked Actions")
    print("=" * 60)

    safety = SafetyConstraints()
    executor = ActionExecutor(safety_constraints=safety)

    # Metric out of range (blocked)
    result = await executor.execute_action(
        action_type="metric_adjustment",
        parameters={
            "interface": "eth0",
            "current_metric": 10,
            "proposed_metric": 99999  # Out of range
        }
    )

    print(f"\nAction: {result.action_type}")
    print(f"Status: {result.status.value}")
    print(f"Error: {result.error}")
    if result.safety_violation:
        print(f"Violation: {result.safety_violation.violation_type.value}")
        print(f"Severity: {result.safety_violation.severity}")


async def example_rate_limiting():
    """Example: Rate limiting prevents rapid changes"""
    print("\n" + "=" * 60)
    print("Example: Rate Limiting")
    print("=" * 60)

    safety = SafetyConstraints()
    safety.set_autonomous_mode(True)
    executor = ActionExecutor(safety_constraints=safety)

    # First change (allowed)
    result1 = await executor.execute_action(
        action_type="metric_adjustment",
        parameters={
            "interface": "eth0",
            "current_metric": 10,
            "proposed_metric": 11
        }
    )
    print(f"\nFirst change: {result1.status.value}")

    # Immediate second change (blocked by rate limit)
    result2 = await executor.execute_action(
        action_type="metric_adjustment",
        parameters={
            "interface": "eth0",
            "current_metric": 11,
            "proposed_metric": 12
        }
    )
    print(f"Second change (immediate): {result2.status.value}")
    if result2.error:
        print(f"Error: {result2.error}")


async def example_route_injection():
    """Example: Route injection requires approval"""
    print("\n" + "=" * 60)
    print("Example: Route Injection")
    print("=" * 60)

    safety = SafetyConstraints()
    executor = ActionExecutor(
        safety_constraints=safety,
        approval_callback=mock_approval_callback
    )

    result = await executor.execute_action(
        action_type="route_injection",
        parameters={
            "network": "10.0.0.0/24",
            "protocol": "bgp"
        }
    )

    print(f"\nAction: {result.action_type}")
    print(f"Status: {result.status.value}")


async def example_action_history():
    """Example: Review action history"""
    print("\n" + "=" * 60)
    print("Example: Action History")
    print("=" * 60)

    safety = SafetyConstraints()
    safety.set_autonomous_mode(True)
    executor = ActionExecutor(safety_constraints=safety)

    # Execute several actions
    actions = [
        ("metric_adjustment", {"interface": "eth0", "current_metric": 10, "proposed_metric": 11}),
        ("metric_adjustment", {"interface": "eth1", "current_metric": 20, "proposed_metric": 21}),
        ("query_neighbors", {"protocol": "ospf"}),
    ]

    for action_type, params in actions:
        await executor.execute_action(action_type, params)
        await asyncio.sleep(0.1)  # Small delay to avoid rate limiting

    # Get history
    history = executor.get_action_history(limit=10)
    print(f"\nExecuted {len(history)} actions:")
    for action in history:
        print(f"  - {action['action_type']}: {action['status']}")
        if action.get('execution_time_ms'):
            print(f"    Execution time: {action['execution_time_ms']:.2f}ms")


async def main():
    """Run all examples"""
    await example_safe_actions()
    await example_unsafe_actions()
    await example_blocked_actions()
    await example_rate_limiting()
    await example_route_injection()
    await example_action_history()

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
