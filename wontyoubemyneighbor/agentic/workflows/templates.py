"""
Workflow Templates

Provides:
- Workflow template definitions
- Template instantiation
- Built-in templates
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

from .steps import Step, StepType, StepConfig
from .engine import Workflow, WorkflowEngine, get_workflow_engine


@dataclass
class TemplateVariable:
    """Variable definition for templates"""

    name: str
    description: str = ""
    type: str = "string"  # string, number, boolean, list, dict
    required: bool = True
    default: Optional[Any] = None
    validation: Optional[str] = None  # Validation regex or expression

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "validation": self.validation
        }


@dataclass
class WorkflowTemplate:
    """Workflow template definition"""

    id: str
    name: str
    description: str = ""
    category: str = "general"
    version: str = "1.0.0"
    variables: List[TemplateVariable] = field(default_factory=list)
    steps_definition: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    author: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    usage_count: int = 0
    rating: float = 0.0
    is_builtin: bool = False

    def validate_inputs(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate input variables against template requirements"""
        errors = []
        for var in self.variables:
            if var.required and var.name not in inputs:
                if var.default is None:
                    errors.append(f"Required variable '{var.name}' not provided")
            elif var.name in inputs:
                value = inputs[var.name]
                # Type validation
                if var.type == "string" and not isinstance(value, str):
                    errors.append(f"Variable '{var.name}' must be a string")
                elif var.type == "number" and not isinstance(value, (int, float)):
                    errors.append(f"Variable '{var.name}' must be a number")
                elif var.type == "boolean" and not isinstance(value, bool):
                    errors.append(f"Variable '{var.name}' must be a boolean")
                elif var.type == "list" and not isinstance(value, list):
                    errors.append(f"Variable '{var.name}' must be a list")
                elif var.type == "dict" and not isinstance(value, dict):
                    errors.append(f"Variable '{var.name}' must be a dict")
        return errors

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "version": self.version,
            "variables": [v.to_dict() for v in self.variables],
            "steps_definition": self.steps_definition,
            "tags": self.tags,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "usage_count": self.usage_count,
            "rating": self.rating,
            "is_builtin": self.is_builtin
        }


class WorkflowTemplateManager:
    """Manages workflow templates"""

    def __init__(self):
        self.templates: Dict[str, WorkflowTemplate] = {}
        self._workflow_engine = get_workflow_engine()
        self._init_builtin_templates()

    def _init_builtin_templates(self) -> None:
        """Initialize built-in workflow templates"""

        # Network Health Check Template
        self.register(WorkflowTemplate(
            id="tpl_network_health",
            name="Network Health Check",
            description="Run comprehensive network health checks across all devices",
            category="monitoring",
            variables=[
                TemplateVariable(name="target_devices", type="list", description="List of device IPs to check"),
                TemplateVariable(name="check_types", type="list", description="Types of checks to run", default=["ping", "bgp", "ospf"]),
                TemplateVariable(name="timeout", type="number", description="Timeout per check in seconds", default=30)
            ],
            steps_definition=[
                {
                    "name": "Initialize Health Check",
                    "step_type": "action",
                    "handler": "log",
                    "parameters": {"message": "Starting network health check", "level": "info"}
                },
                {
                    "name": "Run Connectivity Tests",
                    "step_type": "loop",
                    "handler": "api_call",
                    "loop_items": "target_devices",
                    "parameters": {"url": "/api/health/ping", "method": "POST"}
                },
                {
                    "name": "Check Protocol Status",
                    "step_type": "parallel",
                    "parallel_steps": ["bgp_check", "ospf_check"]
                },
                {
                    "name": "Generate Report",
                    "step_type": "action",
                    "handler": "transform",
                    "parameters": {"operation": "merge"}
                },
                {
                    "name": "Send Notification",
                    "step_type": "notification",
                    "handler": "notification",
                    "parameters": {"channel": "slack", "message": "Health check complete"}
                }
            ],
            tags=["monitoring", "health", "network"],
            author="ADN Platform",
            is_builtin=True
        ))

        # BGP Session Recovery Template
        self.register(WorkflowTemplate(
            id="tpl_bgp_recovery",
            name="BGP Session Recovery",
            description="Automated BGP session troubleshooting and recovery workflow",
            category="troubleshooting",
            variables=[
                TemplateVariable(name="neighbor_ip", type="string", description="BGP neighbor IP address"),
                TemplateVariable(name="local_asn", type="number", description="Local AS number"),
                TemplateVariable(name="max_retries", type="number", description="Maximum recovery attempts", default=3)
            ],
            steps_definition=[
                {
                    "name": "Check BGP Status",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/bgp/neighbors", "method": "GET"}
                },
                {
                    "name": "Evaluate Session State",
                    "step_type": "condition",
                    "handler": "condition",
                    "parameters": {"expression": "session_state != Established"}
                },
                {
                    "name": "Clear BGP Session",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/bgp/clear", "method": "POST"}
                },
                {
                    "name": "Wait for Recovery",
                    "step_type": "delay",
                    "handler": "delay",
                    "parameters": {"seconds": 30}
                },
                {
                    "name": "Verify Recovery",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/bgp/neighbors", "method": "GET"}
                },
                {
                    "name": "Alert on Failure",
                    "step_type": "notification",
                    "handler": "notification",
                    "parameters": {"channel": "pagerduty", "message": "BGP recovery failed"}
                }
            ],
            tags=["bgp", "troubleshooting", "recovery"],
            author="ADN Platform",
            is_builtin=True
        ))

        # OSPF Convergence Monitoring Template
        self.register(WorkflowTemplate(
            id="tpl_ospf_convergence",
            name="OSPF Convergence Monitoring",
            description="Monitor OSPF convergence during network changes",
            category="monitoring",
            variables=[
                TemplateVariable(name="area_id", type="string", description="OSPF area to monitor", default="0.0.0.0"),
                TemplateVariable(name="expected_lsas", type="number", description="Expected number of LSAs"),
                TemplateVariable(name="max_wait_time", type="number", description="Maximum wait time in seconds", default=120)
            ],
            steps_definition=[
                {
                    "name": "Capture Initial State",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/ospf/lsdb", "method": "GET"}
                },
                {
                    "name": "Wait for Changes",
                    "step_type": "delay",
                    "handler": "delay",
                    "parameters": {"seconds": 5}
                },
                {
                    "name": "Monitor Convergence",
                    "step_type": "loop",
                    "handler": "api_call",
                    "loop_items": "check_intervals",
                    "parameters": {"url": "/api/ospf/spf", "method": "GET"}
                },
                {
                    "name": "Calculate Metrics",
                    "step_type": "transform",
                    "handler": "transform",
                    "parameters": {"operation": "extract", "key": "convergence_time"}
                },
                {
                    "name": "Generate Report",
                    "step_type": "action",
                    "handler": "log",
                    "parameters": {"message": "Convergence monitoring complete", "level": "info"}
                }
            ],
            tags=["ospf", "convergence", "monitoring"],
            author="ADN Platform",
            is_builtin=True
        ))

        # Device Provisioning Template
        self.register(WorkflowTemplate(
            id="tpl_device_provision",
            name="Device Provisioning",
            description="Automated device provisioning workflow with validation",
            category="provisioning",
            variables=[
                TemplateVariable(name="device_name", type="string", description="Name of the device"),
                TemplateVariable(name="device_ip", type="string", description="Management IP address"),
                TemplateVariable(name="device_role", type="string", description="Device role (spine/leaf/border)"),
                TemplateVariable(name="config_template", type="string", description="Configuration template to apply")
            ],
            steps_definition=[
                {
                    "name": "Validate Parameters",
                    "step_type": "action",
                    "handler": "condition",
                    "parameters": {"expression": "device_ip != ''"}
                },
                {
                    "name": "Check Device Connectivity",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/devices/ping", "method": "POST"}
                },
                {
                    "name": "Generate Configuration",
                    "step_type": "action",
                    "handler": "transform",
                    "parameters": {"operation": "merge"}
                },
                {
                    "name": "Request Approval",
                    "step_type": "approval",
                    "handler": "approval",
                    "parameters": {"approvers": ["network-admin"], "message": "Approve device provisioning"}
                },
                {
                    "name": "Apply Configuration",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/devices/config", "method": "POST"}
                },
                {
                    "name": "Verify Configuration",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/devices/verify", "method": "GET"}
                },
                {
                    "name": "Notify Completion",
                    "step_type": "notification",
                    "handler": "notification",
                    "parameters": {"channel": "slack", "message": "Device provisioning complete"}
                }
            ],
            tags=["provisioning", "devices", "automation"],
            author="ADN Platform",
            is_builtin=True
        ))

        # Maintenance Window Template
        self.register(WorkflowTemplate(
            id="tpl_maintenance",
            name="Maintenance Window",
            description="Coordinated maintenance window workflow with pre/post checks",
            category="maintenance",
            variables=[
                TemplateVariable(name="target_devices", type="list", description="Devices in maintenance"),
                TemplateVariable(name="maintenance_type", type="string", description="Type of maintenance"),
                TemplateVariable(name="notification_channels", type="list", description="Channels to notify", default=["slack", "email"]),
                TemplateVariable(name="rollback_on_failure", type="boolean", description="Auto-rollback on failure", default=True)
            ],
            steps_definition=[
                {
                    "name": "Pre-Maintenance Checks",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/health/check", "method": "GET"}
                },
                {
                    "name": "Create Backup",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/backup/create", "method": "POST"}
                },
                {
                    "name": "Send Start Notification",
                    "step_type": "notification",
                    "handler": "notification",
                    "parameters": {"message": "Maintenance window started"}
                },
                {
                    "name": "Execute Maintenance",
                    "step_type": "action",
                    "handler": "script",
                    "parameters": {"script": "maintenance_script", "language": "python"}
                },
                {
                    "name": "Post-Maintenance Checks",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/health/check", "method": "GET"}
                },
                {
                    "name": "Send Completion Notification",
                    "step_type": "notification",
                    "handler": "notification",
                    "parameters": {"message": "Maintenance window completed"}
                }
            ],
            tags=["maintenance", "backup", "automation"],
            author="ADN Platform",
            is_builtin=True
        ))

        # Incident Response Template
        self.register(WorkflowTemplate(
            id="tpl_incident_response",
            name="Incident Response",
            description="Automated incident response workflow with escalation",
            category="incident",
            variables=[
                TemplateVariable(name="incident_type", type="string", description="Type of incident"),
                TemplateVariable(name="severity", type="string", description="Incident severity (low/medium/high/critical)"),
                TemplateVariable(name="affected_services", type="list", description="List of affected services"),
                TemplateVariable(name="escalation_contacts", type="list", description="Escalation contact list")
            ],
            steps_definition=[
                {
                    "name": "Log Incident",
                    "step_type": "action",
                    "handler": "log",
                    "parameters": {"message": "Incident logged", "level": "warning"}
                },
                {
                    "name": "Assess Impact",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/impact/assess", "method": "POST"}
                },
                {
                    "name": "Check Severity",
                    "step_type": "condition",
                    "handler": "condition",
                    "parameters": {"expression": "severity == critical"}
                },
                {
                    "name": "Page On-Call",
                    "step_type": "notification",
                    "handler": "notification",
                    "parameters": {"channel": "pagerduty", "message": "Critical incident"}
                },
                {
                    "name": "Execute Runbook",
                    "step_type": "action",
                    "handler": "script",
                    "parameters": {"script": "incident_runbook", "language": "python"}
                },
                {
                    "name": "Update Status Page",
                    "step_type": "action",
                    "handler": "api_call",
                    "parameters": {"url": "/api/status/update", "method": "POST"}
                },
                {
                    "name": "Close Incident",
                    "step_type": "action",
                    "handler": "log",
                    "parameters": {"message": "Incident closed", "level": "info"}
                }
            ],
            tags=["incident", "response", "escalation"],
            author="ADN Platform",
            is_builtin=True
        ))

    def register(self, template: WorkflowTemplate) -> WorkflowTemplate:
        """Register a workflow template"""
        self.templates[template.id] = template
        return template

    def get(self, template_id: str) -> Optional[WorkflowTemplate]:
        """Get template by ID"""
        return self.templates.get(template_id)

    def delete(self, template_id: str) -> bool:
        """Delete a template"""
        template = self.templates.get(template_id)
        if template and not template.is_builtin:
            del self.templates[template_id]
            return True
        return False

    def search(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        builtin_only: bool = False
    ) -> List[WorkflowTemplate]:
        """Search templates"""
        results = list(self.templates.values())

        if query:
            query = query.lower()
            results = [
                t for t in results
                if query in t.name.lower() or query in t.description.lower()
            ]

        if category:
            results = [t for t in results if t.category == category]

        if tag:
            results = [t for t in results if tag in t.tags]

        if builtin_only:
            results = [t for t in results if t.is_builtin]

        return results

    def get_categories(self) -> List[str]:
        """Get all template categories"""
        categories = set()
        for template in self.templates.values():
            categories.add(template.category)
        return sorted(categories)

    def get_tags(self) -> List[str]:
        """Get all template tags"""
        tags = set()
        for template in self.templates.values():
            tags.update(template.tags)
        return sorted(tags)

    def instantiate(
        self,
        template_id: str,
        workflow_name: str,
        inputs: Dict[str, Any],
        created_by: str = ""
    ) -> Optional[Workflow]:
        """Create a workflow instance from a template"""
        template = self.templates.get(template_id)
        if not template:
            return None

        # Validate inputs
        errors = template.validate_inputs(inputs)
        if errors:
            return None

        # Apply defaults
        final_inputs = {}
        for var in template.variables:
            if var.name in inputs:
                final_inputs[var.name] = inputs[var.name]
            elif var.default is not None:
                final_inputs[var.name] = var.default

        # Create workflow
        workflow = self._workflow_engine.create_workflow(
            name=workflow_name,
            description=f"Created from template: {template.name}",
            version=template.version,
            tags=list(template.tags),
            created_by=created_by
        )

        # Set variables
        for name, value in final_inputs.items():
            workflow.set_variable(name, value)

        # Create steps
        step_id_mapping = {}
        prev_step_id = None

        for step_def in template.steps_definition:
            step = Step(
                id=f"step_{uuid.uuid4().hex[:8]}",
                name=step_def.get("name", "Unnamed Step"),
                step_type=StepType(step_def.get("step_type", "action")),
                description=step_def.get("description", ""),
                handler=step_def.get("handler"),
                parameters=step_def.get("parameters", {}),
                config=StepConfig(
                    timeout_seconds=step_def.get("timeout", 300),
                    retry_count=step_def.get("retry_count", 0),
                    continue_on_failure=step_def.get("continue_on_failure", False),
                    condition_expression=step_def.get("condition")
                )
            )

            if step_def.get("loop_items"):
                step.loop_items = step_def["loop_items"]
            if step_def.get("parallel_steps"):
                step.parallel_steps = step_def["parallel_steps"]

            workflow.add_step(step)
            step_id_mapping[step_def.get("name")] = step.id

            # Connect to previous step
            if prev_step_id:
                workflow.steps[prev_step_id].on_success = step.id
                workflow.steps[prev_step_id].next_steps.append(step.id)

            prev_step_id = step.id

        # Update usage count
        template.usage_count += 1

        return workflow

    def rate_template(self, template_id: str, rating: float) -> bool:
        """Rate a template"""
        template = self.templates.get(template_id)
        if not template or rating < 1 or rating > 5:
            return False

        # Simple average calculation
        if template.rating == 0:
            template.rating = rating
        else:
            template.rating = (template.rating + rating) / 2

        return True

    def get_popular(self, limit: int = 10) -> List[WorkflowTemplate]:
        """Get popular templates by usage"""
        sorted_templates = sorted(
            self.templates.values(),
            key=lambda t: t.usage_count,
            reverse=True
        )
        return sorted_templates[:limit]

    def get_statistics(self) -> dict:
        """Get template statistics"""
        by_category = {}
        total_usage = 0

        for template in self.templates.values():
            by_category[template.category] = by_category.get(template.category, 0) + 1
            total_usage += template.usage_count

        return {
            "total_templates": len(self.templates),
            "builtin_templates": len([t for t in self.templates.values() if t.is_builtin]),
            "by_category": by_category,
            "total_usage": total_usage,
            "categories": list(self.get_categories()),
            "tags": list(self.get_tags())
        }


# Global template manager instance
_template_manager: Optional[WorkflowTemplateManager] = None


def get_workflow_template_manager() -> WorkflowTemplateManager:
    """Get or create the global workflow template manager"""
    global _template_manager
    if _template_manager is None:
        _template_manager = WorkflowTemplateManager()
    return _template_manager
