"""
Intent Executor - Translates intents into configuration actions

Converts high-level intents into:
- Execution plans with ordered steps
- Protocol-specific configurations
- Multi-agent coordination
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from collections import deque
import uuid

from .parser import Intent, IntentType, get_intent_parser

logger = logging.getLogger("IntentExecutor")


class StepStatus(Enum):
    """Execution step status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


@dataclass
class ExecutionStep:
    """
    Single step in an execution plan

    Attributes:
        step_id: Unique step identifier
        step_number: Order in plan
        action: Action to perform
        target_agent: Agent to execute on
        parameters: Action parameters
        protocol: Affected protocol
        dependencies: Steps that must complete first
        rollback_action: Action to undo this step
        status: Current status
    """
    step_id: str
    step_number: int
    action: str
    target_agent: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    protocol: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    rollback_action: Optional[str] = None
    rollback_params: Dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_number": self.step_number,
            "action": self.action,
            "target_agent": self.target_agent,
            "parameters": self.parameters,
            "protocol": self.protocol,
            "dependencies": self.dependencies,
            "rollback_action": self.rollback_action,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "result": self.result
        }


@dataclass
class ExecutionPlan:
    """
    Complete execution plan for an intent

    Attributes:
        plan_id: Unique plan identifier
        intent: Source intent
        steps: Ordered execution steps
        status: Plan execution status
        created_at: Plan creation time
    """
    plan_id: str
    intent: Intent
    steps: List[ExecutionStep] = field(default_factory=list)
    status: str = "created"
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    validation_passed: bool = False
    dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "intent": self.intent.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "validation_passed": self.validation_passed,
            "dry_run": self.dry_run
        }

    def add_step(
        self,
        action: str,
        target_agent: str,
        parameters: Dict[str, Any] = None,
        protocol: str = None,
        dependencies: List[str] = None,
        rollback_action: str = None,
        rollback_params: Dict[str, Any] = None
    ) -> ExecutionStep:
        """Add a step to the plan"""
        step_number = len(self.steps) + 1
        step = ExecutionStep(
            step_id=f"{self.plan_id}-step-{step_number}",
            step_number=step_number,
            action=action,
            target_agent=target_agent,
            parameters=parameters or {},
            protocol=protocol,
            dependencies=dependencies or [],
            rollback_action=rollback_action,
            rollback_params=rollback_params or {}
        )
        self.steps.append(step)
        return step

    def get_pending_steps(self) -> List[ExecutionStep]:
        """Get steps ready to execute (dependencies met)"""
        completed_ids = {s.step_id for s in self.steps if s.status == StepStatus.COMPLETED}
        pending = []
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                if all(dep in completed_ids for dep in step.dependencies):
                    pending.append(step)
        return pending


@dataclass
class ExecutionResult:
    """
    Result of intent execution

    Attributes:
        plan: Executed plan
        success: Whether execution succeeded
        steps_completed: Number of steps completed
        steps_failed: Number of steps failed
        duration_ms: Execution duration
        changes_made: Summary of changes made
    """
    plan: ExecutionPlan
    success: bool
    steps_completed: int = 0
    steps_failed: int = 0
    steps_skipped: int = 0
    duration_ms: float = 0
    changes_made: List[str] = field(default_factory=list)
    rollback_performed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "success": self.success,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "steps_skipped": self.steps_skipped,
            "duration_ms": self.duration_ms,
            "changes_made": self.changes_made,
            "rollback_performed": self.rollback_performed
        }


class IntentExecutor:
    """
    Executes network intents by generating and running execution plans
    """

    def __init__(self, dry_run: bool = False, max_history: int = 100):
        """
        Initialize intent executor

        Args:
            dry_run: If True, generate plans but don't execute
            max_history: Maximum execution history to retain
        """
        self.dry_run = dry_run
        self._plan_counter = 0
        self._active_plans: Dict[str, ExecutionPlan] = {}
        self._history: deque = deque(maxlen=max_history)

    def _generate_plan_id(self) -> str:
        """Generate unique plan ID"""
        self._plan_counter += 1
        return f"plan-{self._plan_counter:04d}"

    def create_plan(self, intent: Intent) -> ExecutionPlan:
        """
        Create an execution plan for an intent

        Args:
            intent: Parsed intent

        Returns:
            Execution plan with steps
        """
        plan_id = self._generate_plan_id()
        plan = ExecutionPlan(
            plan_id=plan_id,
            intent=intent,
            dry_run=self.dry_run
        )

        # Generate steps based on intent type
        self._generate_steps(plan, intent)

        self._active_plans[plan_id] = plan
        logger.info(f"Created execution plan: {plan_id} with {len(plan.steps)} steps")

        return plan

    def _generate_steps(self, plan: ExecutionPlan, intent: Intent) -> None:
        """Generate execution steps based on intent type"""

        if intent.intent_type == IntentType.HIGH_AVAILABILITY:
            self._plan_high_availability(plan, intent)

        elif intent.intent_type == IntentType.REDUNDANCY:
            self._plan_redundancy(plan, intent)

        elif intent.intent_type == IntentType.TRAFFIC_OPTIMIZATION:
            self._plan_traffic_optimization(plan, intent)

        elif intent.intent_type == IntentType.LOAD_BALANCING:
            self._plan_load_balancing(plan, intent)

        elif intent.intent_type == IntentType.TRAFFIC_BLOCK:
            self._plan_traffic_block(plan, intent)

        elif intent.intent_type == IntentType.CONNECTIVITY:
            self._plan_connectivity(plan, intent)

        elif intent.intent_type == IntentType.LOW_LATENCY:
            self._plan_low_latency(plan, intent)

        elif intent.intent_type == IntentType.PROTOCOL_ENABLE:
            self._plan_protocol_enable(plan, intent)

        elif intent.intent_type == IntentType.PROTOCOL_CONFIGURE:
            self._plan_protocol_configure(plan, intent)

        else:
            # Generic plan for unknown intents
            self._plan_generic(plan, intent)

    def _plan_high_availability(self, plan: ExecutionPlan, intent: Intent) -> None:
        """Plan for high availability intent"""
        agents = intent.target_agents[:2] if intent.target_agents else ["agent1", "agent2"]

        # Step 1: Verify current connectivity
        step1 = plan.add_step(
            action="verify_connectivity",
            target_agent=agents[0],
            parameters={"peer": agents[1] if len(agents) > 1 else None},
            protocol="icmp"
        )

        # Step 2: Configure redundant OSPF paths on first agent
        step2 = plan.add_step(
            action="configure_ospf_backup",
            target_agent=agents[0],
            parameters={"backup_cost": 100, "primary_cost": 10},
            protocol="ospf",
            dependencies=[step1.step_id],
            rollback_action="remove_ospf_backup"
        )

        # Step 3: Configure redundant OSPF paths on second agent
        if len(agents) > 1:
            step3 = plan.add_step(
                action="configure_ospf_backup",
                target_agent=agents[1],
                parameters={"backup_cost": 100, "primary_cost": 10},
                protocol="ospf",
                dependencies=[step1.step_id],
                rollback_action="remove_ospf_backup"
            )

        # Step 4: Enable BFD for fast failure detection
        plan.add_step(
            action="enable_bfd",
            target_agent=agents[0],
            parameters={"peer": agents[1] if len(agents) > 1 else None, "interval_ms": 100},
            protocol="bfd",
            dependencies=[step2.step_id],
            rollback_action="disable_bfd"
        )

        # Step 5: Verify HA is working
        plan.add_step(
            action="verify_redundancy",
            target_agent=agents[0],
            parameters={"expected_paths": 2}
        )

    def _plan_redundancy(self, plan: ExecutionPlan, intent: Intent) -> None:
        """Plan for redundancy intent"""
        agents = intent.target_agents or ["all"]

        for agent in agents:
            # Configure ECMP
            plan.add_step(
                action="enable_ecmp",
                target_agent=agent,
                parameters={"max_paths": 4},
                protocol="routing",
                rollback_action="disable_ecmp"
            )

            # Verify multiple paths exist
            plan.add_step(
                action="verify_multipath",
                target_agent=agent,
                parameters={"min_paths": 2}
            )

    def _plan_traffic_optimization(self, plan: ExecutionPlan, intent: Intent) -> None:
        """Plan for traffic optimization intent"""
        agents = intent.target_agents or ["all"]
        metric = intent.get_parameter("metric") or 10
        bandwidth = intent.get_parameter("bandwidth")

        for agent in agents:
            # Adjust OSPF metrics
            plan.add_step(
                action="set_ospf_metric",
                target_agent=agent,
                parameters={"metric": metric, "interface": "preferred"},
                protocol="ospf",
                rollback_action="restore_ospf_metric"
            )

            # If bandwidth specified, configure interface
            if bandwidth:
                plan.add_step(
                    action="set_interface_bandwidth",
                    target_agent=agent,
                    parameters={"bandwidth": bandwidth},
                    rollback_action="restore_interface_bandwidth"
                )

    def _plan_load_balancing(self, plan: ExecutionPlan, intent: Intent) -> None:
        """Plan for load balancing intent"""
        agents = intent.target_agents or ["all"]

        for agent in agents:
            # Enable ECMP
            step1 = plan.add_step(
                action="enable_ecmp",
                target_agent=agent,
                parameters={"max_paths": 8},
                protocol="routing",
                rollback_action="disable_ecmp"
            )

            # Configure equal cost paths
            plan.add_step(
                action="equalize_path_costs",
                target_agent=agent,
                parameters={},
                protocol="ospf",
                dependencies=[step1.step_id]
            )

    def _plan_traffic_block(self, plan: ExecutionPlan, intent: Intent) -> None:
        """Plan for traffic blocking intent"""
        agents = intent.target_agents or ["all"]
        asn = intent.get_parameter("asn")
        network = intent.get_parameter("network")

        for agent in agents:
            if asn:
                # Create AS-path filter
                plan.add_step(
                    action="create_as_path_filter",
                    target_agent=agent,
                    parameters={"asn": asn, "action": "deny"},
                    protocol="bgp",
                    rollback_action="remove_as_path_filter"
                )

            if network:
                # Create prefix filter
                plan.add_step(
                    action="create_prefix_filter",
                    target_agent=agent,
                    parameters={"prefix": network, "action": "deny"},
                    protocol="bgp",
                    rollback_action="remove_prefix_filter"
                )

    def _plan_connectivity(self, plan: ExecutionPlan, intent: Intent) -> None:
        """Plan for connectivity intent"""
        agents = intent.target_agents[:2] if len(intent.target_agents) >= 2 else ["agent1", "agent2"]

        # Step 1: Configure OSPF on first agent
        step1 = plan.add_step(
            action="enable_ospf",
            target_agent=agents[0],
            parameters={"area": "0.0.0.0"},
            protocol="ospf",
            rollback_action="disable_ospf"
        )

        # Step 2: Configure OSPF on second agent
        if len(agents) > 1:
            step2 = plan.add_step(
                action="enable_ospf",
                target_agent=agents[1],
                parameters={"area": "0.0.0.0"},
                protocol="ospf",
                rollback_action="disable_ospf"
            )

            # Step 3: Verify adjacency
            plan.add_step(
                action="verify_adjacency",
                target_agent=agents[0],
                parameters={"peer": agents[1]},
                protocol="ospf",
                dependencies=[step1.step_id, step2.step_id]
            )

    def _plan_low_latency(self, plan: ExecutionPlan, intent: Intent) -> None:
        """Plan for low latency intent"""
        agents = intent.target_agents or ["all"]

        for agent in agents:
            # Set minimum OSPF delay metric
            plan.add_step(
                action="set_delay_metric",
                target_agent=agent,
                parameters={"optimize_for": "latency"},
                protocol="ospf",
                rollback_action="restore_delay_metric"
            )

            # Enable fast convergence
            plan.add_step(
                action="enable_fast_convergence",
                target_agent=agent,
                parameters={"spf_delay_ms": 50, "spf_hold_ms": 200},
                protocol="ospf",
                rollback_action="restore_convergence_timers"
            )

    def _plan_protocol_enable(self, plan: ExecutionPlan, intent: Intent) -> None:
        """Plan for protocol enable intent"""
        protocol = intent.protocols[0] if intent.protocols else "ospf"
        agents = intent.target_agents or ["all"]

        for agent in agents:
            plan.add_step(
                action=f"enable_{protocol}",
                target_agent=agent,
                parameters={"default_config": True},
                protocol=protocol,
                rollback_action=f"disable_{protocol}"
            )

    def _plan_protocol_configure(self, plan: ExecutionPlan, intent: Intent) -> None:
        """Plan for protocol configuration intent"""
        protocol = intent.protocols[0] if intent.protocols else "ospf"
        agents = intent.target_agents or ["all"]

        for agent in agents:
            # Get protocol-specific parameters
            params = {}
            if protocol == "ospf":
                params["area"] = intent.get_parameter("area") or "0.0.0.0"
            elif protocol == "bgp":
                params["asn"] = intent.get_parameter("asn")

            plan.add_step(
                action=f"configure_{protocol}",
                target_agent=agent,
                parameters=params,
                protocol=protocol,
                rollback_action=f"restore_{protocol}_config"
            )

    def _plan_generic(self, plan: ExecutionPlan, intent: Intent) -> None:
        """Generic plan for unrecognized intents"""
        agents = intent.target_agents or ["network"]

        # Add a verification step
        plan.add_step(
            action="analyze_intent",
            target_agent=agents[0] if agents else "network",
            parameters={"intent_text": intent.raw_text}
        )

    async def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        """
        Execute an intent plan

        Args:
            plan: Plan to execute

        Returns:
            Execution result
        """
        start_time = datetime.now()
        plan.status = "running"
        plan.started_at = start_time

        result = ExecutionResult(plan=plan, success=True)

        try:
            # Execute steps in order respecting dependencies
            while True:
                pending = plan.get_pending_steps()
                if not pending:
                    break

                # Execute pending steps (could be parallel if no dependencies)
                for step in pending:
                    step_result = await self._execute_step(step)

                    if step.status == StepStatus.COMPLETED:
                        result.steps_completed += 1
                        result.changes_made.append(f"{step.action} on {step.target_agent}")
                    elif step.status == StepStatus.FAILED:
                        result.steps_failed += 1
                        result.success = False

                        # Attempt rollback on failure
                        if not self.dry_run:
                            await self._rollback(plan, step)
                            result.rollback_performed = True
                        break

                if not result.success:
                    break

            # Mark skipped steps
            for step in plan.steps:
                if step.status == StepStatus.PENDING:
                    step.status = StepStatus.SKIPPED
                    result.steps_skipped += 1

            plan.status = "completed" if result.success else "failed"
            plan.completed_at = datetime.now()

        except Exception as e:
            logger.error(f"Plan execution error: {e}")
            plan.status = "error"
            result.success = False

        result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Archive
        self._history.append(result)
        if plan.plan_id in self._active_plans:
            del self._active_plans[plan.plan_id]

        return result

    async def _execute_step(self, step: ExecutionStep) -> Dict[str, Any]:
        """Execute a single step"""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now()

        logger.info(f"Executing step: {step.step_id} - {step.action} on {step.target_agent}")

        try:
            if self.dry_run:
                # Simulate execution
                await asyncio.sleep(0.1)
                step.result = {"simulated": True, "action": step.action}
            else:
                # In production, this would call actual configuration APIs
                # For now, simulate success
                await asyncio.sleep(0.1)
                step.result = {"executed": True, "action": step.action}

            step.status = StepStatus.COMPLETED
            step.completed_at = datetime.now()

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.completed_at = datetime.now()
            logger.error(f"Step failed: {step.step_id} - {e}")

        return step.result

    async def _rollback(self, plan: ExecutionPlan, failed_step: ExecutionStep) -> None:
        """Rollback completed steps after a failure"""
        logger.info(f"Rolling back plan: {plan.plan_id}")

        # Rollback completed steps in reverse order
        for step in reversed(plan.steps):
            if step.status == StepStatus.COMPLETED and step.rollback_action:
                try:
                    logger.info(f"Rolling back step: {step.step_id}")
                    # Execute rollback
                    await asyncio.sleep(0.1)  # Simulated
                    step.status = StepStatus.ROLLED_BACK
                except Exception as e:
                    logger.error(f"Rollback failed for {step.step_id}: {e}")

    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get an active plan"""
        return self._active_plans.get(plan_id)

    def list_plans(self, status: Optional[str] = None) -> List[ExecutionPlan]:
        """List active plans"""
        plans = list(self._active_plans.values())
        if status:
            plans = [p for p in plans if p.status == status]
        return plans

    def get_history(self, limit: int = 50) -> List[ExecutionResult]:
        """Get execution history"""
        return list(self._history)[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """Get executor statistics"""
        total_success = sum(1 for r in self._history if r.success)
        total_failed = len(self._history) - total_success

        return {
            "active_plans": len(self._active_plans),
            "history_size": len(self._history),
            "total_successful": total_success,
            "total_failed": total_failed,
            "dry_run_mode": self.dry_run
        }


# Global executor instance
_global_executor: Optional[IntentExecutor] = None


def get_intent_executor() -> IntentExecutor:
    """Get or create the global intent executor"""
    global _global_executor
    if _global_executor is None:
        _global_executor = IntentExecutor()
    return _global_executor
