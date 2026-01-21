"""
Workflow Engine

Provides:
- Workflow definition
- Workflow execution
- State management
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum
import asyncio

from .steps import Step, StepStatus, StepType, StepResult, StepManager, get_step_manager


class WorkflowStatus(Enum):
    """Workflow execution status"""
    DRAFT = "draft"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    WAITING = "waiting"  # Waiting for approval/input


@dataclass
class WorkflowResult:
    """Result of workflow execution"""

    workflow_id: str
    status: WorkflowStatus
    outputs: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    steps_completed: int = 0
    steps_failed: int = 0
    steps_skipped: int = 0

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "outputs": self.outputs,
            "errors": self.errors,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "steps_skipped": self.steps_skipped
        }


@dataclass
class Workflow:
    """Workflow definition"""

    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    steps: Dict[str, Step] = field(default_factory=dict)
    start_step_id: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: str = ""

    # Runtime state
    status: WorkflowStatus = WorkflowStatus.DRAFT
    current_step_id: Optional[str] = None
    result: Optional[WorkflowResult] = None
    execution_history: List[StepResult] = field(default_factory=list)

    def add_step(self, step: Step) -> None:
        """Add a step to the workflow"""
        self.steps[step.id] = step
        if not self.start_step_id:
            self.start_step_id = step.id

    def remove_step(self, step_id: str) -> bool:
        """Remove a step from the workflow"""
        if step_id in self.steps:
            del self.steps[step_id]
            # Update references
            for step in self.steps.values():
                if step.on_success == step_id:
                    step.on_success = None
                if step.on_failure == step_id:
                    step.on_failure = None
                step.next_steps = [s for s in step.next_steps if s != step_id]
            if self.start_step_id == step_id:
                self.start_step_id = None
            return True
        return False

    def get_step(self, step_id: str) -> Optional[Step]:
        """Get a step by ID"""
        return self.steps.get(step_id)

    def set_variable(self, name: str, value: Any) -> None:
        """Set a workflow variable"""
        self.variables[name] = value

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a workflow variable"""
        return self.variables.get(name, default)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "start_step_id": self.start_step_id,
            "variables": self.variables,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "status": self.status.value,
            "current_step_id": self.current_step_id,
            "result": self.result.to_dict() if self.result else None,
            "execution_history": [r.to_dict() for r in self.execution_history]
        }


class WorkflowEngine:
    """Executes and manages workflows"""

    def __init__(self):
        self.workflows: Dict[str, Workflow] = {}
        self._step_manager = get_step_manager()
        self._running_workflows: Dict[str, asyncio.Task] = {}

    def create_workflow(
        self,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        tags: Optional[List[str]] = None,
        created_by: str = ""
    ) -> Workflow:
        """Create a new workflow"""
        workflow_id = f"wf_{uuid.uuid4().hex[:8]}"

        workflow = Workflow(
            id=workflow_id,
            name=name,
            description=description,
            version=version,
            tags=tags or [],
            created_by=created_by
        )

        self.workflows[workflow_id] = workflow
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Get workflow by ID"""
        return self.workflows.get(workflow_id)

    def update_workflow(
        self,
        workflow_id: str,
        **kwargs
    ) -> Optional[Workflow]:
        """Update workflow properties"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return None

        for key, value in kwargs.items():
            if hasattr(workflow, key):
                setattr(workflow, key, value)

        workflow.updated_at = datetime.now()
        return workflow

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow"""
        if workflow_id in self.workflows:
            # Cancel if running
            if workflow_id in self._running_workflows:
                self._running_workflows[workflow_id].cancel()
                del self._running_workflows[workflow_id]
            del self.workflows[workflow_id]
            return True
        return False

    def add_step_to_workflow(
        self,
        workflow_id: str,
        step: Step
    ) -> bool:
        """Add a step to a workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False

        workflow.add_step(step)
        workflow.updated_at = datetime.now()
        return True

    def connect_workflow_steps(
        self,
        workflow_id: str,
        from_step_id: str,
        to_step_id: str,
        on_success: bool = True
    ) -> bool:
        """Connect steps within a workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False

        from_step = workflow.get_step(from_step_id)
        to_step = workflow.get_step(to_step_id)

        if not from_step or not to_step:
            return False

        if on_success:
            from_step.on_success = to_step_id
        else:
            from_step.on_failure = to_step_id

        if to_step_id not in from_step.next_steps:
            from_step.next_steps.append(to_step_id)

        workflow.updated_at = datetime.now()
        return True

    async def execute_workflow(
        self,
        workflow_id: str,
        inputs: Optional[Dict[str, Any]] = None
    ) -> WorkflowResult:
        """Execute a workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return WorkflowResult(
                workflow_id=workflow_id,
                status=WorkflowStatus.FAILED,
                errors=["Workflow not found"]
            )

        if not workflow.start_step_id:
            return WorkflowResult(
                workflow_id=workflow_id,
                status=WorkflowStatus.FAILED,
                errors=["No start step defined"]
            )

        # Initialize
        started_at = datetime.now()
        workflow.status = WorkflowStatus.RUNNING
        workflow.variables = {**workflow.variables, **(inputs or {})}
        workflow.inputs = inputs or {}
        workflow.execution_history = []

        # Reset all steps
        for step in workflow.steps.values():
            step.status = StepStatus.PENDING
            step.result = None

        steps_completed = 0
        steps_failed = 0
        steps_skipped = 0
        errors = []
        outputs = {}

        # Execute steps
        current_step_id = workflow.start_step_id
        context = {
            "workflow_id": workflow_id,
            "variables": workflow.variables,
            "inputs": inputs or {},
            "previous_output": None
        }

        while current_step_id:
            step = workflow.get_step(current_step_id)
            if not step:
                errors.append(f"Step not found: {current_step_id}")
                break

            workflow.current_step_id = current_step_id

            # Check condition
            if step.config.condition_expression:
                condition_result = await self._evaluate_condition(
                    step.config.condition_expression,
                    context
                )
                if not condition_result:
                    step.status = StepStatus.SKIPPED
                    steps_skipped += 1
                    # Move to next step
                    current_step_id = step.on_success
                    continue

            # Handle different step types
            if step.step_type == StepType.PARALLEL:
                # Execute parallel steps
                results = await self._execute_parallel_steps(
                    workflow, step.parallel_steps, context
                )
                for r in results:
                    workflow.execution_history.append(r)
                    if r.status == StepStatus.COMPLETED:
                        steps_completed += 1
                    else:
                        steps_failed += 1
                        if r.error:
                            errors.append(r.error)

                # Determine next step
                all_success = all(r.status == StepStatus.COMPLETED for r in results)
                if all_success:
                    current_step_id = step.on_success
                else:
                    current_step_id = step.on_failure
                continue

            elif step.step_type == StepType.LOOP:
                # Execute loop
                items = context["variables"].get(step.loop_items, [])
                for idx, item in enumerate(items):
                    loop_context = {
                        **context,
                        "loop_index": idx,
                        "loop_item": item
                    }
                    result = await self._step_manager.execute_step(step, loop_context)
                    workflow.execution_history.append(result)
                    if result.status == StepStatus.COMPLETED:
                        steps_completed += 1
                    else:
                        steps_failed += 1
                        if result.error:
                            errors.append(result.error)
                        if not step.config.continue_on_failure:
                            break

                current_step_id = step.on_success if steps_failed == 0 else step.on_failure
                continue

            # Execute normal step
            result = await self._step_manager.execute_step(step, context)
            workflow.execution_history.append(result)

            if result.status == StepStatus.COMPLETED:
                steps_completed += 1
                context["previous_output"] = result.output

                # Apply output mapping
                if result.output and step.config.output_mapping:
                    for var_name, output_key in step.config.output_mapping.items():
                        if isinstance(result.output, dict):
                            context["variables"][var_name] = result.output.get(output_key)
                        else:
                            context["variables"][var_name] = result.output

                # Store as workflow output if last step
                if not step.on_success and not step.next_steps:
                    outputs = result.output if isinstance(result.output, dict) else {"result": result.output}

                current_step_id = step.on_success or (step.next_steps[0] if step.next_steps else None)

            else:
                steps_failed += 1
                if result.error:
                    errors.append(f"Step '{step.name}': {result.error}")

                if step.config.continue_on_failure:
                    current_step_id = step.on_success or (step.next_steps[0] if step.next_steps else None)
                else:
                    current_step_id = step.on_failure

        # Complete workflow
        completed_at = datetime.now()
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        final_status = WorkflowStatus.COMPLETED if steps_failed == 0 else WorkflowStatus.FAILED
        workflow.status = final_status
        workflow.current_step_id = None
        workflow.outputs = outputs
        workflow.variables = context["variables"]

        result = WorkflowResult(
            workflow_id=workflow_id,
            status=final_status,
            outputs=outputs,
            errors=errors,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            steps_completed=steps_completed,
            steps_failed=steps_failed,
            steps_skipped=steps_skipped
        )

        workflow.result = result
        return result

    async def _execute_parallel_steps(
        self,
        workflow: Workflow,
        step_ids: List[str],
        context: Dict[str, Any]
    ) -> List[StepResult]:
        """Execute steps in parallel"""
        tasks = []
        for step_id in step_ids:
            step = workflow.get_step(step_id)
            if step:
                tasks.append(self._step_manager.execute_step(step, context))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(StepResult(
                    step_id=step_ids[i] if i < len(step_ids) else "unknown",
                    status=StepStatus.FAILED,
                    error=str(result)
                ))
            else:
                final_results.append(result)

        return final_results

    async def _evaluate_condition(
        self,
        expression: str,
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate a condition expression"""
        handler = self._step_manager.get_handler("condition")
        if handler:
            result = await handler(
                {"expression": expression},
                context
            )
            return bool(result)
        return True

    def start_workflow_async(
        self,
        workflow_id: str,
        inputs: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Start workflow execution asynchronously"""
        if workflow_id in self._running_workflows:
            return False

        async def run():
            return await self.execute_workflow(workflow_id, inputs)

        task = asyncio.create_task(run())
        self._running_workflows[workflow_id] = task
        return True

    def pause_workflow(self, workflow_id: str) -> bool:
        """Pause a running workflow"""
        workflow = self.workflows.get(workflow_id)
        if workflow and workflow.status == WorkflowStatus.RUNNING:
            workflow.status = WorkflowStatus.PAUSED
            return True
        return False

    def resume_workflow(self, workflow_id: str) -> bool:
        """Resume a paused workflow"""
        workflow = self.workflows.get(workflow_id)
        if workflow and workflow.status == WorkflowStatus.PAUSED:
            workflow.status = WorkflowStatus.RUNNING
            return True
        return False

    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False

        if workflow_id in self._running_workflows:
            self._running_workflows[workflow_id].cancel()
            del self._running_workflows[workflow_id]

        workflow.status = WorkflowStatus.CANCELLED
        return True

    def clone_workflow(self, workflow_id: str, new_name: str) -> Optional[Workflow]:
        """Clone a workflow"""
        original = self.workflows.get(workflow_id)
        if not original:
            return None

        cloned = self.create_workflow(
            name=new_name,
            description=original.description,
            version=original.version,
            tags=list(original.tags),
            created_by=original.created_by
        )

        # Clone steps
        step_id_mapping = {}
        for step_id, step in original.steps.items():
            new_step = Step(
                id=f"step_{uuid.uuid4().hex[:8]}",
                name=step.name,
                step_type=step.step_type,
                description=step.description,
                config=step.config,
                handler=step.handler,
                parameters=dict(step.parameters)
            )
            cloned.add_step(new_step)
            step_id_mapping[step_id] = new_step.id

        # Update step references
        for old_id, new_id in step_id_mapping.items():
            old_step = original.get_step(old_id)
            new_step = cloned.get_step(new_id)
            if old_step and new_step:
                if old_step.on_success:
                    new_step.on_success = step_id_mapping.get(old_step.on_success)
                if old_step.on_failure:
                    new_step.on_failure = step_id_mapping.get(old_step.on_failure)
                new_step.next_steps = [
                    step_id_mapping.get(s, s) for s in old_step.next_steps
                ]

        # Update start step
        if original.start_step_id:
            cloned.start_step_id = step_id_mapping.get(original.start_step_id)

        return cloned

    def get_workflows(
        self,
        status: Optional[WorkflowStatus] = None,
        tag: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> List[Workflow]:
        """Get workflows with filtering"""
        workflows = list(self.workflows.values())

        if status:
            workflows = [w for w in workflows if w.status == status]
        if tag:
            workflows = [w for w in workflows if tag in w.tags]
        if created_by:
            workflows = [w for w in workflows if w.created_by == created_by]

        return workflows

    def get_running_workflows(self) -> List[Workflow]:
        """Get currently running workflows"""
        return [
            w for w in self.workflows.values()
            if w.status == WorkflowStatus.RUNNING
        ]

    def get_workflow_history(self, workflow_id: str) -> List[StepResult]:
        """Get execution history for a workflow"""
        workflow = self.workflows.get(workflow_id)
        if workflow:
            return workflow.execution_history
        return []

    def get_statistics(self) -> dict:
        """Get workflow engine statistics"""
        by_status = {}
        total_steps = 0

        for workflow in self.workflows.values():
            by_status[workflow.status.value] = by_status.get(workflow.status.value, 0) + 1
            total_steps += len(workflow.steps)

        return {
            "total_workflows": len(self.workflows),
            "running_workflows": len(self._running_workflows),
            "by_status": by_status,
            "total_steps": total_steps,
            "step_manager": self._step_manager.get_statistics()
        }


# Global workflow engine instance
_workflow_engine: Optional[WorkflowEngine] = None


def get_workflow_engine() -> WorkflowEngine:
    """Get or create the global workflow engine"""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine
