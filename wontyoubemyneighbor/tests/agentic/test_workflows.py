"""Tests for workflow engine module"""

import pytest
from agentic.workflows import (
    Step, StepStatus, StepType, StepResult, StepConfig, StepManager, get_step_manager,
    Workflow, WorkflowStatus, WorkflowResult, WorkflowEngine, get_workflow_engine,
    WorkflowTemplate, TemplateVariable, WorkflowTemplateManager, get_workflow_template_manager
)


class TestStepManager:
    """Tests for StepManager"""

    def test_create_step(self):
        """Test step creation"""
        manager = StepManager()
        step = manager.create_step(
            name="test-step",
            step_type=StepType.ACTION,
            description="Test step"
        )
        assert step.name == "test-step"
        assert step.step_type == StepType.ACTION

    def test_get_step(self):
        """Test getting step by ID"""
        manager = StepManager()
        step = manager.create_step("test", StepType.DELAY)

        retrieved = manager.get_step(step.id)
        assert retrieved is not None
        assert retrieved.id == step.id

    def test_delete_step(self):
        """Test step deletion"""
        manager = StepManager()
        step = manager.create_step("test", StepType.SCRIPT)

        assert manager.delete_step(step.id)
        assert manager.get_step(step.id) is None


class TestWorkflowEngine:
    """Tests for WorkflowEngine"""

    def test_create_workflow(self):
        """Test workflow creation"""
        engine = WorkflowEngine()
        workflow = engine.create_workflow(
            name="test-workflow",
            description="Test workflow"
        )
        assert workflow.name == "test-workflow"
        assert workflow.status == WorkflowStatus.DRAFT

    def test_get_workflow(self):
        """Test getting workflow by ID"""
        engine = WorkflowEngine()
        workflow = engine.create_workflow("test")

        retrieved = engine.get_workflow(workflow.id)
        assert retrieved is not None
        assert retrieved.id == workflow.id

    def test_delete_workflow(self):
        """Test workflow deletion"""
        engine = WorkflowEngine()
        workflow = engine.create_workflow("test")

        assert engine.delete_workflow(workflow.id)
        assert engine.get_workflow(workflow.id) is None


class TestWorkflowTemplate:
    """Tests for WorkflowTemplate"""

    def test_to_dict(self):
        """Test template serialization"""
        template = WorkflowTemplate(
            id="tmpl-1",
            name="Test Template",
            description="Test template description"
        )

        data = template.to_dict()
        assert data["id"] == "tmpl-1"
        assert data["name"] == "Test Template"


class TestStepType:
    """Tests for StepType enum"""

    def test_step_types_exist(self):
        """Test step types are defined"""
        assert hasattr(StepType, "ACTION")
        assert hasattr(StepType, "CONDITION")
        assert hasattr(StepType, "PARALLEL")
        assert hasattr(StepType, "LOOP")
        assert hasattr(StepType, "DELAY")


class TestWorkflowStatus:
    """Tests for WorkflowStatus enum"""

    def test_statuses_exist(self):
        """Test workflow statuses are defined"""
        assert hasattr(WorkflowStatus, "DRAFT")
        assert hasattr(WorkflowStatus, "PENDING")
        assert hasattr(WorkflowStatus, "RUNNING")
        assert hasattr(WorkflowStatus, "COMPLETED")
        assert hasattr(WorkflowStatus, "FAILED")
