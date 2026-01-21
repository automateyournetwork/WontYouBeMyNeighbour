"""
Notification Templates

Provides:
- Template definition
- Variable substitution
- Template management
- Built-in templates
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from enum import Enum


class TemplateType(Enum):
    """Template types"""
    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"
    WEBHOOK = "webhook"
    GENERIC = "generic"


@dataclass
class TemplateVariable:
    """Template variable definition"""

    name: str
    description: str = ""
    required: bool = True
    default_value: Optional[str] = None
    example: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "default_value": self.default_value,
            "example": self.example
        }


@dataclass
class NotificationTemplate:
    """Notification template"""

    id: str
    name: str
    template_type: TemplateType
    subject_template: str
    body_template: str
    description: str = ""
    variables: List[TemplateVariable] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    use_count: int = 0

    # Optional additional templates for rich content
    html_template: Optional[str] = None
    slack_blocks_template: Optional[str] = None

    @property
    def variable_names(self) -> Set[str]:
        """Get all variable names used in templates"""
        pattern = r'\{\{(\w+)\}\}'
        names = set()
        names.update(re.findall(pattern, self.subject_template))
        names.update(re.findall(pattern, self.body_template))
        if self.html_template:
            names.update(re.findall(pattern, self.html_template))
        return names

    def render(
        self,
        variables: Dict[str, Any],
        include_html: bool = False
    ) -> Dict[str, str]:
        """Render template with variables"""
        result = {}

        # Build variable dict with defaults
        var_dict = {}
        for var in self.variables:
            if var.name in variables:
                var_dict[var.name] = str(variables[var.name])
            elif var.default_value is not None:
                var_dict[var.name] = var.default_value
            elif var.required:
                raise ValueError(f"Missing required variable: {var.name}")

        # Add any extra variables
        for k, v in variables.items():
            if k not in var_dict:
                var_dict[k] = str(v)

        # Render templates
        result["subject"] = self._substitute(self.subject_template, var_dict)
        result["body"] = self._substitute(self.body_template, var_dict)

        if include_html and self.html_template:
            result["html"] = self._substitute(self.html_template, var_dict)

        return result

    def validate(self, variables: Dict[str, Any]) -> List[str]:
        """Validate variables against template requirements"""
        errors = []

        for var in self.variables:
            if var.required and var.name not in variables and var.default_value is None:
                errors.append(f"Missing required variable: {var.name}")

        return errors

    def _substitute(self, template: str, variables: Dict[str, str]) -> str:
        """Substitute variables in template"""
        result = template
        for name, value in variables.items():
            result = result.replace(f"{{{{{name}}}}}", value)
        return result

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "template_type": self.template_type.value,
            "subject_template": self.subject_template,
            "body_template": self.body_template,
            "description": self.description,
            "variables": [v.to_dict() for v in self.variables],
            "tags": self.tags,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "use_count": self.use_count,
            "has_html": self.html_template is not None
        }


class TemplateManager:
    """Manages notification templates"""

    def __init__(self):
        self.templates: Dict[str, NotificationTemplate] = {}
        self._init_builtin_templates()

    def _init_builtin_templates(self) -> None:
        """Initialize built-in templates"""

        # Alert notification template
        self.create_template(
            name="alert_notification",
            template_type=TemplateType.GENERIC,
            subject_template="[{{severity}}] {{alert_name}}",
            body_template="Alert: {{alert_name}}\nSeverity: {{severity}}\nMetric: {{metric_name}}\nValue: {{metric_value}}\nThreshold: {{threshold}}\nTime: {{timestamp}}",
            description="Alert notification template",
            variables=[
                TemplateVariable("alert_name", "Name of the alert", True),
                TemplateVariable("severity", "Alert severity", True),
                TemplateVariable("metric_name", "Metric name", True),
                TemplateVariable("metric_value", "Current metric value", True),
                TemplateVariable("threshold", "Alert threshold", True),
                TemplateVariable("timestamp", "Alert timestamp", True)
            ],
            tags=["alert", "monitoring"]
        )

        # Welcome email template
        self.create_template(
            name="welcome_email",
            template_type=TemplateType.EMAIL,
            subject_template="Welcome to {{platform_name}}!",
            body_template="Hello {{user_name}},\n\nWelcome to {{platform_name}}!\n\nYour account has been created successfully.\n\nBest regards,\nThe {{platform_name}} Team",
            description="Welcome email for new users",
            variables=[
                TemplateVariable("user_name", "User's name", True),
                TemplateVariable("platform_name", "Platform name", True, "ADN Platform")
            ],
            tags=["email", "onboarding"]
        )

        # Password reset template
        self.create_template(
            name="password_reset",
            template_type=TemplateType.EMAIL,
            subject_template="Password Reset Request - {{platform_name}}",
            body_template="Hello {{user_name}},\n\nA password reset was requested for your account.\n\nReset link: {{reset_link}}\n\nThis link expires in {{expiry_hours}} hours.\n\nIf you didn't request this, please ignore this email.",
            description="Password reset email",
            variables=[
                TemplateVariable("user_name", "User's name", True),
                TemplateVariable("platform_name", "Platform name", True, "ADN Platform"),
                TemplateVariable("reset_link", "Password reset URL", True),
                TemplateVariable("expiry_hours", "Link expiry time", True, "24")
            ],
            tags=["email", "security"]
        )

        # Network event template
        self.create_template(
            name="network_event",
            template_type=TemplateType.GENERIC,
            subject_template="Network Event: {{event_type}} on {{device_name}}",
            body_template="Event: {{event_type}}\nDevice: {{device_name}}\nInterface: {{interface}}\nDetails: {{details}}\nTime: {{timestamp}}",
            description="Network event notification",
            variables=[
                TemplateVariable("event_type", "Type of event", True),
                TemplateVariable("device_name", "Device name", True),
                TemplateVariable("interface", "Interface name", False, "N/A"),
                TemplateVariable("details", "Event details", True),
                TemplateVariable("timestamp", "Event timestamp", True)
            ],
            tags=["network", "event"]
        )

        # Protocol state change template
        self.create_template(
            name="protocol_state_change",
            template_type=TemplateType.GENERIC,
            subject_template="{{protocol}} State Change: {{old_state}} -> {{new_state}}",
            body_template="Protocol: {{protocol}}\nNode: {{node_name}}\nNeighbor: {{neighbor}}\nOld State: {{old_state}}\nNew State: {{new_state}}\nTime: {{timestamp}}",
            description="Protocol state change notification",
            variables=[
                TemplateVariable("protocol", "Protocol name", True),
                TemplateVariable("node_name", "Node name", True),
                TemplateVariable("neighbor", "Neighbor identifier", True),
                TemplateVariable("old_state", "Previous state", True),
                TemplateVariable("new_state", "New state", True),
                TemplateVariable("timestamp", "Event timestamp", True)
            ],
            tags=["protocol", "state"]
        )

        # Slack alert template
        self.create_template(
            name="slack_alert",
            template_type=TemplateType.SLACK,
            subject_template=":warning: {{alert_name}}",
            body_template="*{{alert_name}}*\n> Severity: `{{severity}}`\n> Metric: `{{metric_name}}` = {{metric_value}}\n> Threshold: {{threshold}}",
            description="Slack-formatted alert",
            variables=[
                TemplateVariable("alert_name", "Name of the alert", True),
                TemplateVariable("severity", "Alert severity", True),
                TemplateVariable("metric_name", "Metric name", True),
                TemplateVariable("metric_value", "Current metric value", True),
                TemplateVariable("threshold", "Alert threshold", True)
            ],
            tags=["slack", "alert"]
        )

    def create_template(
        self,
        name: str,
        template_type: TemplateType,
        subject_template: str,
        body_template: str,
        description: str = "",
        variables: Optional[List[TemplateVariable]] = None,
        tags: Optional[List[str]] = None,
        html_template: Optional[str] = None
    ) -> NotificationTemplate:
        """Create a notification template"""
        template_id = f"template_{uuid.uuid4().hex[:8]}"

        template = NotificationTemplate(
            id=template_id,
            name=name,
            template_type=template_type,
            subject_template=subject_template,
            body_template=body_template,
            description=description,
            variables=variables or [],
            tags=tags or [],
            html_template=html_template
        )

        self.templates[template_id] = template
        return template

    def get_template(self, template_id: str) -> Optional[NotificationTemplate]:
        """Get template by ID"""
        return self.templates.get(template_id)

    def get_template_by_name(self, name: str) -> Optional[NotificationTemplate]:
        """Get template by name"""
        for template in self.templates.values():
            if template.name == name:
                return template
        return None

    def update_template(
        self,
        template_id: str,
        **kwargs
    ) -> Optional[NotificationTemplate]:
        """Update a template"""
        template = self.templates.get(template_id)
        if not template:
            return None

        for key, value in kwargs.items():
            if hasattr(template, key):
                setattr(template, key, value)

        template.updated_at = datetime.now()
        return template

    def delete_template(self, template_id: str) -> bool:
        """Delete a template"""
        if template_id in self.templates:
            del self.templates[template_id]
            return True
        return False

    def render_template(
        self,
        template_id: str,
        variables: Dict[str, Any],
        include_html: bool = False
    ) -> Optional[Dict[str, str]]:
        """Render a template with variables"""
        template = self.templates.get(template_id)
        if not template or not template.enabled:
            return None

        template.use_count += 1
        return template.render(variables, include_html)

    def render_by_name(
        self,
        name: str,
        variables: Dict[str, Any],
        include_html: bool = False
    ) -> Optional[Dict[str, str]]:
        """Render template by name"""
        template = self.get_template_by_name(name)
        if not template or not template.enabled:
            return None

        template.use_count += 1
        return template.render(variables, include_html)

    def validate_template(
        self,
        template_id: str,
        variables: Dict[str, Any]
    ) -> List[str]:
        """Validate variables for a template"""
        template = self.templates.get(template_id)
        if not template:
            return ["Template not found"]
        return template.validate(variables)

    def get_templates(
        self,
        template_type: Optional[TemplateType] = None,
        tag: Optional[str] = None,
        enabled_only: bool = False
    ) -> List[NotificationTemplate]:
        """Get templates with optional filtering"""
        templates = list(self.templates.values())

        if template_type:
            templates = [t for t in templates if t.template_type == template_type]
        if tag:
            templates = [t for t in templates if tag in t.tags]
        if enabled_only:
            templates = [t for t in templates if t.enabled]

        return templates

    def get_templates_by_tag(self, tag: str) -> List[NotificationTemplate]:
        """Get templates by tag"""
        return [t for t in self.templates.values() if tag in t.tags]

    def clone_template(
        self,
        template_id: str,
        new_name: str
    ) -> Optional[NotificationTemplate]:
        """Clone a template"""
        template = self.templates.get(template_id)
        if not template:
            return None

        return self.create_template(
            name=new_name,
            template_type=template.template_type,
            subject_template=template.subject_template,
            body_template=template.body_template,
            description=f"Cloned from {template.name}",
            variables=template.variables.copy(),
            tags=template.tags.copy(),
            html_template=template.html_template
        )

    def get_statistics(self) -> dict:
        """Get template statistics"""
        by_type = {}
        total_uses = 0

        for template in self.templates.values():
            type_name = template.template_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1
            total_uses += template.use_count

        return {
            "total_templates": len(self.templates),
            "enabled_templates": len([t for t in self.templates.values() if t.enabled]),
            "by_type": by_type,
            "total_uses": total_uses,
            "all_tags": list(set(tag for t in self.templates.values() for tag in t.tags))
        }


# Global template manager instance
_template_manager: Optional[TemplateManager] = None


def get_template_manager() -> TemplateManager:
    """Get or create the global template manager"""
    global _template_manager
    if _template_manager is None:
        _template_manager = TemplateManager()
    return _template_manager
