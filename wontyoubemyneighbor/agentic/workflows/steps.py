"""
Workflow Steps

Provides:
- Step definition
- Step execution
- Step status tracking
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable
from datetime import datetime
from enum import Enum
import asyncio


class StepStatus(Enum):
    """Step execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    WAITING = "waiting"  # Waiting for input/approval


class StepType(Enum):
    """Types of workflow steps"""
    ACTION = "action"           # Execute an action
    CONDITION = "condition"     # Conditional branching
    PARALLEL = "parallel"       # Execute steps in parallel
    LOOP = "loop"              # Loop over items
    DELAY = "delay"            # Wait for duration
    APPROVAL = "approval"       # Human approval required
    NOTIFICATION = "notification"  # Send notification
    SCRIPT = "script"          # Execute script
    API_CALL = "api_call"      # Make API call
    TRANSFORM = "transform"     # Transform data


@dataclass
class StepConfig:
    """Step configuration"""

    timeout_seconds: int = 300
    retry_count: int = 0
    retry_delay_seconds: int = 5
    continue_on_failure: bool = False
    condition_expression: Optional[str] = None
    input_mapping: Dict[str, str] = field(default_factory=dict)
    output_mapping: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "retry_delay_seconds": self.retry_delay_seconds,
            "continue_on_failure": self.continue_on_failure,
            "condition_expression": self.condition_expression,
            "input_mapping": self.input_mapping,
            "output_mapping": self.output_mapping
        }


@dataclass
class StepResult:
    """Result of step execution"""

    step_id: str
    status: StepStatus
    output: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count
        }


@dataclass
class Step:
    """Workflow step definition"""

    id: str
    name: str
    step_type: StepType
    description: str = ""
    config: StepConfig = field(default_factory=StepConfig)
    handler: Optional[str] = None  # Handler name or function
    parameters: Dict[str, Any] = field(default_factory=dict)
    next_steps: List[str] = field(default_factory=list)  # Next step IDs
    on_success: Optional[str] = None  # Step ID on success
    on_failure: Optional[str] = None  # Step ID on failure
    parallel_steps: List[str] = field(default_factory=list)  # For parallel execution
    loop_items: Optional[str] = None  # Variable name containing items to loop
    created_at: datetime = field(default_factory=datetime.now)

    # Runtime state
    status: StepStatus = StepStatus.PENDING
    result: Optional[StepResult] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "step_type": self.step_type.value,
            "description": self.description,
            "config": self.config.to_dict(),
            "handler": self.handler,
            "parameters": self.parameters,
            "next_steps": self.next_steps,
            "on_success": self.on_success,
            "on_failure": self.on_failure,
            "parallel_steps": self.parallel_steps,
            "loop_items": self.loop_items,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "result": self.result.to_dict() if self.result else None
        }


class StepManager:
    """Manages workflow steps"""

    def __init__(self):
        self.steps: Dict[str, Step] = {}
        self._handlers: Dict[str, Callable] = {}
        self._register_builtin_handlers()

    def _register_builtin_handlers(self) -> None:
        """Register built-in step handlers"""

        async def delay_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Any:
            """Delay execution"""
            seconds = params.get("seconds", 1)
            await asyncio.sleep(seconds)
            return {"delayed_seconds": seconds}

        async def log_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Any:
            """Log a message"""
            message = params.get("message", "")
            level = params.get("level", "info")
            return {"logged": True, "message": message, "level": level}

        async def transform_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Any:
            """Transform data"""
            input_data = params.get("input", context.get("previous_output"))
            operation = params.get("operation", "passthrough")

            if operation == "passthrough":
                return input_data
            elif operation == "uppercase":
                return str(input_data).upper() if input_data else None
            elif operation == "lowercase":
                return str(input_data).lower() if input_data else None
            elif operation == "extract":
                key = params.get("key")
                if isinstance(input_data, dict) and key:
                    return input_data.get(key)
                return None
            elif operation == "merge":
                merge_with = params.get("merge_with", {})
                if isinstance(input_data, dict):
                    return {**input_data, **merge_with}
                return merge_with
            return input_data

        async def condition_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Any:
            """Evaluate condition"""
            expression = params.get("expression", "true")
            variables = {**context.get("variables", {}), **params}

            # Simple expression evaluation
            try:
                # Safe evaluation of simple conditions
                if expression.lower() == "true":
                    return True
                elif expression.lower() == "false":
                    return False
                elif "==" in expression:
                    parts = expression.split("==")
                    left = parts[0].strip()
                    right = parts[1].strip()
                    left_val = variables.get(left, left)
                    right_val = variables.get(right, right)
                    return str(left_val) == str(right_val)
                elif "!=" in expression:
                    parts = expression.split("!=")
                    left = parts[0].strip()
                    right = parts[1].strip()
                    left_val = variables.get(left, left)
                    right_val = variables.get(right, right)
                    return str(left_val) != str(right_val)
                elif ">" in expression:
                    parts = expression.split(">")
                    left = float(variables.get(parts[0].strip(), parts[0].strip()))
                    right = float(variables.get(parts[1].strip(), parts[1].strip()))
                    return left > right
                elif "<" in expression:
                    parts = expression.split("<")
                    left = float(variables.get(parts[0].strip(), parts[0].strip()))
                    right = float(variables.get(parts[1].strip(), parts[1].strip()))
                    return left < right
                return bool(expression)
            except Exception:
                return False

        async def notification_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Any:
            """Send notification (simulated)"""
            channel = params.get("channel", "default")
            message = params.get("message", "")
            recipients = params.get("recipients", [])
            return {
                "sent": True,
                "channel": channel,
                "message": message,
                "recipients": recipients,
                "timestamp": datetime.now().isoformat()
            }

        async def api_call_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Any:
            """Make API call (simulated)"""
            url = params.get("url", "")
            method = params.get("method", "GET")
            headers = params.get("headers", {})
            body = params.get("body", {})

            # Simulated response
            return {
                "status_code": 200,
                "url": url,
                "method": method,
                "response": {"success": True, "simulated": True},
                "timestamp": datetime.now().isoformat()
            }

        async def script_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Any:
            """Execute script (simulated)"""
            script = params.get("script", "")
            language = params.get("language", "python")

            # Simulated execution
            return {
                "executed": True,
                "language": language,
                "output": "Script execution simulated",
                "exit_code": 0
            }

        async def approval_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Any:
            """Request approval (auto-approve for simulation)"""
            approvers = params.get("approvers", [])
            message = params.get("message", "Approval required")
            timeout = params.get("timeout_hours", 24)

            return {
                "approved": True,  # Auto-approve in simulation
                "approvers": approvers,
                "message": message,
                "approved_by": "system",
                "timestamp": datetime.now().isoformat()
            }

        self._handlers = {
            "delay": delay_handler,
            "log": log_handler,
            "transform": transform_handler,
            "condition": condition_handler,
            "notification": notification_handler,
            "api_call": api_call_handler,
            "script": script_handler,
            "approval": approval_handler
        }

    def register_handler(
        self,
        name: str,
        handler: Callable
    ) -> None:
        """Register a custom step handler"""
        self._handlers[name] = handler

    def get_handler(self, name: str) -> Optional[Callable]:
        """Get handler by name"""
        return self._handlers.get(name)

    def get_available_handlers(self) -> List[str]:
        """Get list of available handlers"""
        return list(self._handlers.keys())

    def create_step(
        self,
        name: str,
        step_type: StepType,
        description: str = "",
        handler: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        config: Optional[StepConfig] = None
    ) -> Step:
        """Create a new step"""
        step_id = f"step_{uuid.uuid4().hex[:8]}"

        step = Step(
            id=step_id,
            name=name,
            step_type=step_type,
            description=description,
            handler=handler,
            parameters=parameters or {},
            config=config or StepConfig()
        )

        self.steps[step_id] = step
        return step

    def get_step(self, step_id: str) -> Optional[Step]:
        """Get step by ID"""
        return self.steps.get(step_id)

    def update_step(
        self,
        step_id: str,
        **kwargs
    ) -> Optional[Step]:
        """Update step properties"""
        step = self.steps.get(step_id)
        if not step:
            return None

        for key, value in kwargs.items():
            if hasattr(step, key):
                setattr(step, key, value)

        return step

    def delete_step(self, step_id: str) -> bool:
        """Delete a step"""
        if step_id in self.steps:
            del self.steps[step_id]
            return True
        return False

    def connect_steps(
        self,
        from_step_id: str,
        to_step_id: str,
        on_success: bool = True
    ) -> bool:
        """Connect steps in workflow"""
        from_step = self.steps.get(from_step_id)
        to_step = self.steps.get(to_step_id)

        if not from_step or not to_step:
            return False

        if on_success:
            from_step.on_success = to_step_id
        else:
            from_step.on_failure = to_step_id

        if to_step_id not in from_step.next_steps:
            from_step.next_steps.append(to_step_id)

        return True

    async def execute_step(
        self,
        step: Step,
        context: Dict[str, Any]
    ) -> StepResult:
        """Execute a single step"""
        started_at = datetime.now()
        step.status = StepStatus.RUNNING

        try:
            handler = self._handlers.get(step.handler)
            if not handler:
                raise ValueError(f"Unknown handler: {step.handler}")

            # Apply input mapping
            mapped_params = dict(step.parameters)
            for target, source in step.config.input_mapping.items():
                if source in context.get("variables", {}):
                    mapped_params[target] = context["variables"][source]

            # Execute with timeout
            try:
                output = await asyncio.wait_for(
                    handler(mapped_params, context),
                    timeout=step.config.timeout_seconds
                )
            except asyncio.TimeoutError:
                raise TimeoutError(f"Step timed out after {step.config.timeout_seconds}s")

            completed_at = datetime.now()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            step.status = StepStatus.COMPLETED
            result = StepResult(
                step_id=step.id,
                status=StepStatus.COMPLETED,
                output=output,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms
            )

        except Exception as e:
            completed_at = datetime.now()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            step.status = StepStatus.FAILED
            result = StepResult(
                step_id=step.id,
                status=StepStatus.FAILED,
                error=str(e),
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms
            )

        step.result = result
        return result

    def reset_step(self, step_id: str) -> bool:
        """Reset step to pending state"""
        step = self.steps.get(step_id)
        if step:
            step.status = StepStatus.PENDING
            step.result = None
            return True
        return False

    def get_steps(
        self,
        step_type: Optional[StepType] = None,
        status: Optional[StepStatus] = None
    ) -> List[Step]:
        """Get steps with filtering"""
        steps = list(self.steps.values())

        if step_type:
            steps = [s for s in steps if s.step_type == step_type]
        if status:
            steps = [s for s in steps if s.status == status]

        return steps

    def get_statistics(self) -> dict:
        """Get step statistics"""
        by_type = {}
        by_status = {}

        for step in self.steps.values():
            by_type[step.step_type.value] = by_type.get(step.step_type.value, 0) + 1
            by_status[step.status.value] = by_status.get(step.status.value, 0) + 1

        return {
            "total_steps": len(self.steps),
            "by_type": by_type,
            "by_status": by_status,
            "available_handlers": len(self._handlers)
        }


# Global step manager instance
_step_manager: Optional[StepManager] = None


def get_step_manager() -> StepManager:
    """Get or create the global step manager"""
    global _step_manager
    if _step_manager is None:
        _step_manager = StepManager()
    return _step_manager
