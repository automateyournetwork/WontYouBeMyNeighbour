"""
Network Scenario Builder

Create, manage, and execute network scenarios for testing,
validation, training, and what-if analysis.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import json

logger = logging.getLogger(__name__)


class ScenarioStepType(Enum):
    """Types of scenario steps."""
    # Configuration actions
    CONFIG_CHANGE = "config_change"      # Apply configuration
    INTERFACE_UP = "interface_up"         # Bring interface up
    INTERFACE_DOWN = "interface_down"     # Bring interface down
    LINK_FAIL = "link_fail"               # Fail a link
    LINK_RESTORE = "link_restore"         # Restore a link
    NODE_FAIL = "node_fail"               # Fail a node/agent
    NODE_RESTORE = "node_restore"         # Restore a node/agent

    # Traffic actions
    TRAFFIC_START = "traffic_start"       # Start traffic flow
    TRAFFIC_STOP = "traffic_stop"         # Stop traffic flow
    TRAFFIC_INJECT = "traffic_inject"     # Inject specific traffic

    # Verification actions
    VERIFY_CONNECTIVITY = "verify_connectivity"  # Ping/trace verification
    VERIFY_ROUTE = "verify_route"         # Route exists
    VERIFY_NO_ROUTE = "verify_no_route"   # Route doesn't exist
    VERIFY_NEIGHBOR = "verify_neighbor"   # Neighbor established
    VERIFY_NO_NEIGHBOR = "verify_no_neighbor"  # Neighbor down
    VERIFY_BGP_PATH = "verify_bgp_path"   # BGP path attributes
    VERIFY_CONVERGENCE = "verify_convergence"  # Wait for convergence

    # Control actions
    WAIT = "wait"                         # Wait for duration
    CHECKPOINT = "checkpoint"             # Create checkpoint
    ROLLBACK = "rollback"                 # Rollback to checkpoint
    LOG_MESSAGE = "log_message"           # Log a message
    CUSTOM = "custom"                     # Custom action


class ScenarioStatus(Enum):
    """Scenario execution status."""
    DRAFT = "draft"           # Being edited
    READY = "ready"           # Ready to run
    RUNNING = "running"       # Currently executing
    PAUSED = "paused"         # Paused mid-execution
    COMPLETED = "completed"   # Successfully completed
    FAILED = "failed"         # Failed during execution
    ABORTED = "aborted"       # Manually aborted


@dataclass
class ScenarioStep:
    """A single step in a scenario."""
    step_id: str
    step_type: ScenarioStepType
    name: str
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 60  # seconds
    continue_on_failure: bool = False
    retry_count: int = 0
    retry_delay: int = 5  # seconds
    depends_on: List[str] = field(default_factory=list)  # step IDs

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "step_type": self.step_type.value,
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "timeout": self.timeout,
            "continue_on_failure": self.continue_on_failure,
            "retry_count": self.retry_count,
            "retry_delay": self.retry_delay,
            "depends_on": self.depends_on,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScenarioStep":
        """Create from dictionary."""
        return cls(
            step_id=data["step_id"],
            step_type=ScenarioStepType(data["step_type"]),
            name=data["name"],
            description=data.get("description", ""),
            parameters=data.get("parameters", {}),
            timeout=data.get("timeout", 60),
            continue_on_failure=data.get("continue_on_failure", False),
            retry_count=data.get("retry_count", 0),
            retry_delay=data.get("retry_delay", 5),
            depends_on=data.get("depends_on", []),
        )


@dataclass
class StepResult:
    """Result of executing a scenario step."""
    step_id: str
    success: bool
    message: str
    started_at: datetime
    completed_at: datetime
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    retry_attempts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "success": self.success,
            "message": self.message,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_ms": int((self.completed_at - self.started_at).total_seconds() * 1000),
            "output": self.output,
            "error": self.error,
            "retry_attempts": self.retry_attempts,
        }


@dataclass
class ScenarioResult:
    """Result of executing a complete scenario."""
    scenario_id: str
    status: ScenarioStatus
    started_at: datetime
    completed_at: Optional[datetime]
    step_results: List[StepResult] = field(default_factory=list)
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scenario_id": self.scenario_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": int((self.completed_at - self.started_at).total_seconds() * 1000) if self.completed_at else None,
            "step_results": [r.to_dict() for r in self.step_results],
            "total_steps": self.total_steps,
            "passed_steps": self.passed_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "success_rate": round(self.passed_steps / self.total_steps * 100, 1) if self.total_steps > 0 else 0,
        }


@dataclass
class Scenario:
    """A network test scenario."""
    scenario_id: str
    name: str
    description: str = ""
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    steps: List[ScenarioStep] = field(default_factory=list)
    status: ScenarioStatus = ScenarioStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    author: str = "system"
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "steps": [s.to_dict() for s in self.steps],
            "step_count": len(self.steps),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "author": self.author,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Scenario":
        """Create from dictionary."""
        steps = [ScenarioStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            scenario_id=data["scenario_id"],
            name=data["name"],
            description=data.get("description", ""),
            category=data.get("category", "general"),
            tags=data.get("tags", []),
            steps=steps,
            status=ScenarioStatus(data.get("status", "draft")),
            author=data.get("author", "system"),
            version=data.get("version", "1.0"),
        )


class ScenarioBuilder:
    """
    Network scenario builder and executor.

    Manages the creation, storage, and execution of network test scenarios.
    """

    # Singleton instance
    _instance: Optional["ScenarioBuilder"] = None

    def __new__(cls) -> "ScenarioBuilder":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._scenario_counter = 0
        self._step_counter = 0
        self._scenarios: Dict[str, Scenario] = {}
        self._results: Dict[str, ScenarioResult] = {}
        self._templates: Dict[str, Scenario] = {}
        self._running_scenario: Optional[str] = None
        self._step_handlers: Dict[ScenarioStepType, Callable] = {}
        self._checkpoints: Dict[str, Dict[str, Any]] = {}

        # Register built-in step handlers
        self._register_default_handlers()

        # Create default templates
        self._create_default_templates()

        logger.info("ScenarioBuilder initialized")

    def _generate_scenario_id(self) -> str:
        """Generate unique scenario ID."""
        self._scenario_counter += 1
        return f"scn-{self._scenario_counter:06d}"

    def _generate_step_id(self) -> str:
        """Generate unique step ID."""
        self._step_counter += 1
        return f"step-{self._step_counter:06d}"

    def _register_default_handlers(self):
        """Register default step handlers."""
        self._step_handlers = {
            ScenarioStepType.WAIT: self._handle_wait,
            ScenarioStepType.LOG_MESSAGE: self._handle_log_message,
            ScenarioStepType.CHECKPOINT: self._handle_checkpoint,
            ScenarioStepType.ROLLBACK: self._handle_rollback,
            ScenarioStepType.INTERFACE_UP: self._handle_interface_up,
            ScenarioStepType.INTERFACE_DOWN: self._handle_interface_down,
            ScenarioStepType.LINK_FAIL: self._handle_link_fail,
            ScenarioStepType.LINK_RESTORE: self._handle_link_restore,
            ScenarioStepType.VERIFY_CONNECTIVITY: self._handle_verify_connectivity,
            ScenarioStepType.VERIFY_ROUTE: self._handle_verify_route,
            ScenarioStepType.VERIFY_NEIGHBOR: self._handle_verify_neighbor,
            ScenarioStepType.VERIFY_CONVERGENCE: self._handle_verify_convergence,
            ScenarioStepType.TRAFFIC_START: self._handle_traffic_start,
            ScenarioStepType.TRAFFIC_STOP: self._handle_traffic_stop,
            ScenarioStepType.CONFIG_CHANGE: self._handle_config_change,
        }

    def _create_default_templates(self):
        """Create default scenario templates."""
        # Link failure recovery template
        link_failure = Scenario(
            scenario_id="template-link-failure",
            name="Link Failure Recovery",
            description="Test network recovery after a link failure",
            category="resilience",
            tags=["failure", "recovery", "convergence"],
            author="system",
        )
        link_failure.steps = [
            ScenarioStep(
                step_id="t1-step1",
                step_type=ScenarioStepType.CHECKPOINT,
                name="Create baseline checkpoint",
                parameters={"checkpoint_name": "baseline"},
            ),
            ScenarioStep(
                step_id="t1-step2",
                step_type=ScenarioStepType.VERIFY_CONNECTIVITY,
                name="Verify initial connectivity",
                parameters={"source": "${source}", "destination": "${destination}"},
            ),
            ScenarioStep(
                step_id="t1-step3",
                step_type=ScenarioStepType.LINK_FAIL,
                name="Fail primary link",
                parameters={"agent": "${agent}", "interface": "${interface}"},
            ),
            ScenarioStep(
                step_id="t1-step4",
                step_type=ScenarioStepType.VERIFY_CONVERGENCE,
                name="Wait for convergence",
                parameters={"timeout": 30},
            ),
            ScenarioStep(
                step_id="t1-step5",
                step_type=ScenarioStepType.VERIFY_CONNECTIVITY,
                name="Verify connectivity after failure",
                parameters={"source": "${source}", "destination": "${destination}"},
            ),
            ScenarioStep(
                step_id="t1-step6",
                step_type=ScenarioStepType.LINK_RESTORE,
                name="Restore link",
                parameters={"agent": "${agent}", "interface": "${interface}"},
            ),
            ScenarioStep(
                step_id="t1-step7",
                step_type=ScenarioStepType.VERIFY_CONVERGENCE,
                name="Wait for re-convergence",
                parameters={"timeout": 30},
            ),
        ]
        self._templates["link-failure"] = link_failure

        # BGP peer failover template
        bgp_failover = Scenario(
            scenario_id="template-bgp-failover",
            name="BGP Peer Failover",
            description="Test BGP failover between primary and backup peers",
            category="routing",
            tags=["bgp", "failover", "redundancy"],
            author="system",
        )
        bgp_failover.steps = [
            ScenarioStep(
                step_id="t2-step1",
                step_type=ScenarioStepType.VERIFY_NEIGHBOR,
                name="Verify primary BGP peer",
                parameters={"agent": "${agent}", "neighbor": "${primary_peer}", "protocol": "bgp"},
            ),
            ScenarioStep(
                step_id="t2-step2",
                step_type=ScenarioStepType.VERIFY_ROUTE,
                name="Verify route via primary",
                parameters={"agent": "${agent}", "prefix": "${prefix}", "next_hop": "${primary_next_hop}"},
            ),
            ScenarioStep(
                step_id="t2-step3",
                step_type=ScenarioStepType.INTERFACE_DOWN,
                name="Shut down primary peer interface",
                parameters={"agent": "${agent}", "interface": "${primary_interface}"},
            ),
            ScenarioStep(
                step_id="t2-step4",
                step_type=ScenarioStepType.WAIT,
                name="Wait for BGP timeout",
                parameters={"duration": 10},
            ),
            ScenarioStep(
                step_id="t2-step5",
                step_type=ScenarioStepType.VERIFY_ROUTE,
                name="Verify route via backup",
                parameters={"agent": "${agent}", "prefix": "${prefix}", "next_hop": "${backup_next_hop}"},
            ),
            ScenarioStep(
                step_id="t2-step6",
                step_type=ScenarioStepType.INTERFACE_UP,
                name="Restore primary peer interface",
                parameters={"agent": "${agent}", "interface": "${primary_interface}"},
            ),
        ]
        self._templates["bgp-failover"] = bgp_failover

        # OSPF convergence test template
        ospf_convergence = Scenario(
            scenario_id="template-ospf-convergence",
            name="OSPF Convergence Test",
            description="Measure OSPF convergence time after topology change",
            category="convergence",
            tags=["ospf", "convergence", "performance"],
            author="system",
        )
        ospf_convergence.steps = [
            ScenarioStep(
                step_id="t3-step1",
                step_type=ScenarioStepType.LOG_MESSAGE,
                name="Start convergence test",
                parameters={"message": "Starting OSPF convergence test", "level": "info"},
            ),
            ScenarioStep(
                step_id="t3-step2",
                step_type=ScenarioStepType.VERIFY_NEIGHBOR,
                name="Verify OSPF neighbor",
                parameters={"agent": "${agent}", "neighbor": "${neighbor}", "protocol": "ospf", "state": "Full"},
            ),
            ScenarioStep(
                step_id="t3-step3",
                step_type=ScenarioStepType.CHECKPOINT,
                name="Record pre-failure state",
                parameters={"checkpoint_name": "pre_failure"},
            ),
            ScenarioStep(
                step_id="t3-step4",
                step_type=ScenarioStepType.LINK_FAIL,
                name="Trigger topology change",
                parameters={"agent": "${agent}", "interface": "${interface}"},
            ),
            ScenarioStep(
                step_id="t3-step5",
                step_type=ScenarioStepType.VERIFY_CONVERGENCE,
                name="Measure convergence time",
                parameters={"timeout": 60, "measure": True},
            ),
            ScenarioStep(
                step_id="t3-step6",
                step_type=ScenarioStepType.LINK_RESTORE,
                name="Restore link",
                parameters={"agent": "${agent}", "interface": "${interface}"},
            ),
        ]
        self._templates["ospf-convergence"] = ospf_convergence

    # ==== Scenario Management ====

    def create_scenario(
        self,
        name: str,
        description: str = "",
        category: str = "general",
        tags: Optional[List[str]] = None,
        author: str = "user",
    ) -> Scenario:
        """Create a new scenario."""
        scenario = Scenario(
            scenario_id=self._generate_scenario_id(),
            name=name,
            description=description,
            category=category,
            tags=tags or [],
            author=author,
        )
        self._scenarios[scenario.scenario_id] = scenario
        logger.info(f"Created scenario: {scenario.name} ({scenario.scenario_id})")
        return scenario

    def create_from_template(
        self,
        template_id: str,
        name: str,
        variables: Optional[Dict[str, str]] = None,
    ) -> Optional[Scenario]:
        """Create a scenario from a template with variable substitution."""
        template = self._templates.get(template_id)
        if not template:
            logger.error(f"Template not found: {template_id}")
            return None

        # Clone template
        scenario = Scenario(
            scenario_id=self._generate_scenario_id(),
            name=name,
            description=template.description,
            category=template.category,
            tags=template.tags.copy(),
            author="user",
        )

        # Clone and substitute variables in steps
        variables = variables or {}
        for template_step in template.steps:
            step = ScenarioStep(
                step_id=self._generate_step_id(),
                step_type=template_step.step_type,
                name=self._substitute_variables(template_step.name, variables),
                description=self._substitute_variables(template_step.description, variables),
                parameters=self._substitute_dict_variables(template_step.parameters, variables),
                timeout=template_step.timeout,
                continue_on_failure=template_step.continue_on_failure,
                retry_count=template_step.retry_count,
                retry_delay=template_step.retry_delay,
            )
            scenario.steps.append(step)

        self._scenarios[scenario.scenario_id] = scenario
        logger.info(f"Created scenario from template: {name} ({scenario.scenario_id})")
        return scenario

    def _substitute_variables(self, text: str, variables: Dict[str, str]) -> str:
        """Substitute ${var} placeholders in text."""
        for key, value in variables.items():
            text = text.replace(f"${{{key}}}", str(value))
        return text

    def _substitute_dict_variables(self, params: Dict[str, Any], variables: Dict[str, str]) -> Dict[str, Any]:
        """Substitute variables in a dictionary recursively."""
        result = {}
        for key, value in params.items():
            if isinstance(value, str):
                result[key] = self._substitute_variables(value, variables)
            elif isinstance(value, dict):
                result[key] = self._substitute_dict_variables(value, variables)
            elif isinstance(value, list):
                result[key] = [
                    self._substitute_variables(v, variables) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def add_step(
        self,
        scenario_id: str,
        step_type: ScenarioStepType,
        name: str,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Optional[ScenarioStep]:
        """Add a step to a scenario."""
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            logger.error(f"Scenario not found: {scenario_id}")
            return None

        if scenario.status not in (ScenarioStatus.DRAFT, ScenarioStatus.READY):
            logger.error(f"Cannot modify scenario in status: {scenario.status.value}")
            return None

        step = ScenarioStep(
            step_id=self._generate_step_id(),
            step_type=step_type,
            name=name,
            description=description,
            parameters=parameters or {},
            **kwargs,
        )

        scenario.steps.append(step)
        scenario.updated_at = datetime.now()
        scenario.status = ScenarioStatus.DRAFT

        logger.debug(f"Added step to scenario {scenario_id}: {step.name}")
        return step

    def remove_step(self, scenario_id: str, step_id: str) -> bool:
        """Remove a step from a scenario."""
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            return False

        scenario.steps = [s for s in scenario.steps if s.step_id != step_id]
        scenario.updated_at = datetime.now()
        return True

    def update_scenario(self, scenario_id: str, **updates) -> Optional[Scenario]:
        """Update scenario properties."""
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            return None

        for key, value in updates.items():
            if hasattr(scenario, key) and key not in ("scenario_id", "steps", "created_at"):
                setattr(scenario, key, value)

        scenario.updated_at = datetime.now()
        return scenario

    def delete_scenario(self, scenario_id: str) -> bool:
        """Delete a scenario."""
        if scenario_id in self._scenarios:
            del self._scenarios[scenario_id]
            return True
        return False

    def get_scenario(self, scenario_id: str) -> Optional[Scenario]:
        """Get a scenario by ID."""
        return self._scenarios.get(scenario_id)

    def list_scenarios(
        self,
        category: Optional[str] = None,
        status: Optional[ScenarioStatus] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Scenario]:
        """List scenarios with optional filtering."""
        scenarios = list(self._scenarios.values())

        if category:
            scenarios = [s for s in scenarios if s.category == category]
        if status:
            scenarios = [s for s in scenarios if s.status == status]
        if tags:
            scenarios = [s for s in scenarios if any(t in s.tags for t in tags)]

        return scenarios

    def get_templates(self) -> List[Scenario]:
        """Get available scenario templates."""
        return list(self._templates.values())

    def set_ready(self, scenario_id: str) -> bool:
        """Mark a scenario as ready for execution."""
        scenario = self._scenarios.get(scenario_id)
        if not scenario or not scenario.steps:
            return False

        scenario.status = ScenarioStatus.READY
        return True

    # ==== Scenario Execution ====

    async def run_scenario(
        self,
        scenario_id: str,
        dry_run: bool = False,
    ) -> Optional[ScenarioResult]:
        """
        Execute a scenario.

        Args:
            scenario_id: Scenario to run
            dry_run: If True, simulate without making changes

        Returns:
            ScenarioResult with execution details
        """
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            logger.error(f"Scenario not found: {scenario_id}")
            return None

        if scenario.status == ScenarioStatus.RUNNING:
            logger.error("Scenario is already running")
            return None

        if self._running_scenario:
            logger.error("Another scenario is already running")
            return None

        # Initialize result
        result = ScenarioResult(
            scenario_id=scenario_id,
            status=ScenarioStatus.RUNNING,
            started_at=datetime.now(),
            completed_at=None,
            total_steps=len(scenario.steps),
        )

        self._running_scenario = scenario_id
        scenario.status = ScenarioStatus.RUNNING

        logger.info(f"Starting scenario: {scenario.name} ({scenario_id})")

        try:
            # Execute each step
            for step in scenario.steps:
                step_result = await self._execute_step(step, dry_run=dry_run)
                result.step_results.append(step_result)

                if step_result.success:
                    result.passed_steps += 1
                else:
                    result.failed_steps += 1
                    if not step.continue_on_failure:
                        logger.error(f"Step failed, stopping scenario: {step.name}")
                        result.status = ScenarioStatus.FAILED
                        break

            # Mark remaining steps as skipped if we stopped early
            executed_ids = {r.step_id for r in result.step_results}
            for step in scenario.steps:
                if step.step_id not in executed_ids:
                    result.skipped_steps += 1

            if result.status == ScenarioStatus.RUNNING:
                result.status = ScenarioStatus.COMPLETED

        except Exception as e:
            logger.exception(f"Scenario execution error: {e}")
            result.status = ScenarioStatus.FAILED

        finally:
            result.completed_at = datetime.now()
            self._running_scenario = None
            scenario.status = ScenarioStatus.READY

        # Store result
        self._results[scenario_id] = result
        logger.info(f"Scenario completed: {scenario.name} - {result.status.value}")

        return result

    async def _execute_step(
        self,
        step: ScenarioStep,
        dry_run: bool = False,
    ) -> StepResult:
        """Execute a single scenario step."""
        started_at = datetime.now()
        attempts = 0

        while attempts <= step.retry_count:
            try:
                if dry_run:
                    # Simulate execution
                    await asyncio.sleep(0.1)
                    return StepResult(
                        step_id=step.step_id,
                        success=True,
                        message=f"[DRY RUN] {step.name}",
                        started_at=started_at,
                        completed_at=datetime.now(),
                        output={"dry_run": True},
                        retry_attempts=attempts,
                    )

                # Get handler for step type
                handler = self._step_handlers.get(step.step_type)
                if not handler:
                    return StepResult(
                        step_id=step.step_id,
                        success=False,
                        message=f"No handler for step type: {step.step_type.value}",
                        started_at=started_at,
                        completed_at=datetime.now(),
                        error=f"Unknown step type: {step.step_type.value}",
                        retry_attempts=attempts,
                    )

                # Execute with timeout
                logger.debug(f"Executing step: {step.name}")
                output = await asyncio.wait_for(
                    handler(step.parameters),
                    timeout=step.timeout,
                )

                return StepResult(
                    step_id=step.step_id,
                    success=True,
                    message=f"Completed: {step.name}",
                    started_at=started_at,
                    completed_at=datetime.now(),
                    output=output or {},
                    retry_attempts=attempts,
                )

            except asyncio.TimeoutError:
                error = f"Step timed out after {step.timeout}s"
                logger.warning(f"{step.name}: {error}")
            except Exception as e:
                error = str(e)
                logger.warning(f"{step.name}: {error}")

            attempts += 1
            if attempts <= step.retry_count:
                logger.info(f"Retrying step ({attempts}/{step.retry_count}): {step.name}")
                await asyncio.sleep(step.retry_delay)

        return StepResult(
            step_id=step.step_id,
            success=False,
            message=f"Failed after {attempts} attempts: {step.name}",
            started_at=started_at,
            completed_at=datetime.now(),
            error=error,
            retry_attempts=attempts,
        )

    def abort_scenario(self, scenario_id: str) -> bool:
        """Abort a running scenario."""
        if self._running_scenario != scenario_id:
            return False

        scenario = self._scenarios.get(scenario_id)
        if scenario:
            scenario.status = ScenarioStatus.ABORTED

        self._running_scenario = None
        return True

    def get_result(self, scenario_id: str) -> Optional[ScenarioResult]:
        """Get the result of a scenario execution."""
        return self._results.get(scenario_id)

    def get_all_results(self) -> List[ScenarioResult]:
        """Get all scenario results."""
        return list(self._results.values())

    # ==== Step Handlers ====

    async def _handle_wait(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle wait step."""
        duration = params.get("duration", 5)
        await asyncio.sleep(duration)
        return {"waited_seconds": duration}

    async def _handle_log_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle log message step."""
        message = params.get("message", "")
        level = params.get("level", "info")

        log_func = getattr(logger, level, logger.info)
        log_func(f"[SCENARIO] {message}")

        return {"message": message, "level": level}

    async def _handle_checkpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle checkpoint step."""
        checkpoint_name = params.get("checkpoint_name", "default")

        # Capture current network state
        state = {"timestamp": datetime.now().isoformat()}

        try:
            from agentic.replay import get_network_recorder
            recorder = get_network_recorder()
            snapshot = recorder.capture_snapshot()
            state["snapshot_id"] = snapshot.snapshot_id
        except ImportError:
            pass

        self._checkpoints[checkpoint_name] = state
        return {"checkpoint": checkpoint_name, "state": state}

    async def _handle_rollback(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle rollback step."""
        checkpoint_name = params.get("checkpoint_name", "default")

        if checkpoint_name not in self._checkpoints:
            raise ValueError(f"Checkpoint not found: {checkpoint_name}")

        state = self._checkpoints[checkpoint_name]
        return {"checkpoint": checkpoint_name, "restored_from": state}

    async def _handle_interface_up(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle interface up step."""
        agent = params.get("agent")
        interface = params.get("interface")

        # Simulate interface up
        logger.info(f"Bringing up interface {interface} on {agent}")
        return {"agent": agent, "interface": interface, "state": "up"}

    async def _handle_interface_down(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle interface down step."""
        agent = params.get("agent")
        interface = params.get("interface")

        # Simulate interface down
        logger.info(f"Shutting down interface {interface} on {agent}")
        return {"agent": agent, "interface": interface, "state": "down"}

    async def _handle_link_fail(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle link failure step."""
        agent = params.get("agent")
        interface = params.get("interface")

        # Simulate link failure
        logger.info(f"Simulating link failure: {interface} on {agent}")
        return {"agent": agent, "interface": interface, "failed": True}

    async def _handle_link_restore(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle link restore step."""
        agent = params.get("agent")
        interface = params.get("interface")

        # Simulate link restore
        logger.info(f"Restoring link: {interface} on {agent}")
        return {"agent": agent, "interface": interface, "restored": True}

    async def _handle_verify_connectivity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle connectivity verification step."""
        source = params.get("source")
        destination = params.get("destination")
        protocol = params.get("protocol", "icmp")

        # Simulate ping test
        logger.info(f"Verifying connectivity: {source} -> {destination}")
        return {
            "source": source,
            "destination": destination,
            "protocol": protocol,
            "reachable": True,
            "latency_ms": 1.5,
        }

    async def _handle_verify_route(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle route verification step."""
        agent = params.get("agent")
        prefix = params.get("prefix")
        next_hop = params.get("next_hop")

        # Simulate route check
        logger.info(f"Verifying route on {agent}: {prefix} via {next_hop}")
        return {
            "agent": agent,
            "prefix": prefix,
            "expected_next_hop": next_hop,
            "found": True,
        }

    async def _handle_verify_neighbor(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle neighbor verification step."""
        agent = params.get("agent")
        neighbor = params.get("neighbor")
        protocol = params.get("protocol", "ospf")
        expected_state = params.get("state")

        # Simulate neighbor check
        logger.info(f"Verifying {protocol} neighbor on {agent}: {neighbor}")
        return {
            "agent": agent,
            "neighbor": neighbor,
            "protocol": protocol,
            "state": expected_state or "Full",
            "found": True,
        }

    async def _handle_verify_convergence(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle convergence verification step."""
        timeout = params.get("timeout", 30)
        measure = params.get("measure", False)

        start_time = datetime.now()

        # Simulate waiting for convergence
        await asyncio.sleep(min(5, timeout))

        convergence_time = (datetime.now() - start_time).total_seconds()

        return {
            "converged": True,
            "convergence_time_seconds": convergence_time,
            "measured": measure,
        }

    async def _handle_traffic_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle traffic start step."""
        source = params.get("source")
        destination = params.get("destination")
        rate = params.get("rate", 10)

        logger.info(f"Starting traffic: {source} -> {destination} @ {rate} Mbps")
        return {
            "source": source,
            "destination": destination,
            "rate_mbps": rate,
            "started": True,
        }

    async def _handle_traffic_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle traffic stop step."""
        source = params.get("source")
        destination = params.get("destination")

        logger.info(f"Stopping traffic: {source} -> {destination}")
        return {
            "source": source,
            "destination": destination,
            "stopped": True,
        }

    async def _handle_config_change(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle configuration change step."""
        agent = params.get("agent")
        config = params.get("config")

        logger.info(f"Applying config to {agent}")
        return {
            "agent": agent,
            "applied": True,
        }

    # ==== Statistics ====

    def get_statistics(self) -> Dict[str, Any]:
        """Get scenario builder statistics."""
        status_counts = {}
        category_counts = {}

        for scenario in self._scenarios.values():
            status_counts[scenario.status.value] = status_counts.get(scenario.status.value, 0) + 1
            category_counts[scenario.category] = category_counts.get(scenario.category, 0) + 1

        return {
            "total_scenarios": len(self._scenarios),
            "total_templates": len(self._templates),
            "total_results": len(self._results),
            "running_scenario": self._running_scenario,
            "by_status": status_counts,
            "by_category": category_counts,
        }

    def export_scenario(self, scenario_id: str) -> Optional[str]:
        """Export a scenario as JSON."""
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            return None

        return json.dumps(scenario.to_dict(), indent=2)

    def import_scenario(self, json_data: str) -> Optional[Scenario]:
        """Import a scenario from JSON."""
        try:
            data = json.loads(json_data)
            data["scenario_id"] = self._generate_scenario_id()

            # Regenerate step IDs
            for step_data in data.get("steps", []):
                step_data["step_id"] = self._generate_step_id()

            scenario = Scenario.from_dict(data)
            self._scenarios[scenario.scenario_id] = scenario
            return scenario

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to import scenario: {e}")
            return None


# Singleton accessor
def get_scenario_builder() -> ScenarioBuilder:
    """Get the scenario builder instance."""
    return ScenarioBuilder()


# Convenience functions
def create_scenario(name: str, description: str = "", **kwargs) -> Scenario:
    """Create a new scenario."""
    builder = get_scenario_builder()
    return builder.create_scenario(name, description, **kwargs)


async def run_scenario(scenario_id: str, dry_run: bool = False) -> Optional[ScenarioResult]:
    """Run a scenario."""
    builder = get_scenario_builder()
    return await builder.run_scenario(scenario_id, dry_run=dry_run)


def get_scenario_results(scenario_id: str) -> Optional[Dict[str, Any]]:
    """Get scenario results as dictionary."""
    builder = get_scenario_builder()
    result = builder.get_result(scenario_id)
    return result.to_dict() if result else None
