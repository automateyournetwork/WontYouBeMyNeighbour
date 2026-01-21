"""
Template Renderer

Provides:
- Template definitions
- Template rendering
- Template management
"""

import uuid
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class TemplateCategory(Enum):
    """Template categories"""
    CONFIGURATION = "configuration"  # Device configuration
    INTERFACE = "interface"  # Interface configuration
    ROUTING = "routing"  # Routing protocol config
    SECURITY = "security"  # Security policies
    QOS = "qos"  # Quality of Service
    VLAN = "vlan"  # VLAN configuration
    ACL = "acl"  # Access Control Lists
    NAT = "nat"  # NAT configuration
    VPN = "vpn"  # VPN configuration
    MONITORING = "monitoring"  # Monitoring scripts
    NOTIFICATION = "notification"  # Notification messages
    REPORT = "report"  # Report templates
    CUSTOM = "custom"  # Custom templates


class TemplateFormat(Enum):
    """Template output formats"""
    TEXT = "text"
    CLI = "cli"  # CLI commands
    JSON = "json"
    XML = "xml"
    YAML = "yaml"
    NETCONF = "netconf"
    RESTCONF = "restconf"
    HTML = "html"
    MARKDOWN = "markdown"


@dataclass
class TemplateConfig:
    """Template configuration"""

    output_format: TemplateFormat = TemplateFormat.TEXT
    variable_start: str = "{{"
    variable_end: str = "}}"
    block_start: str = "{%"
    block_end: str = "%}"
    comment_start: str = "{#"
    comment_end: str = "#}"
    trim_blocks: bool = True
    lstrip_blocks: bool = True
    escape_output: bool = False
    strict_mode: bool = False  # Error on undefined variables
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "output_format": self.output_format.value,
            "variable_start": self.variable_start,
            "variable_end": self.variable_end,
            "block_start": self.block_start,
            "block_end": self.block_end,
            "comment_start": self.comment_start,
            "comment_end": self.comment_end,
            "trim_blocks": self.trim_blocks,
            "lstrip_blocks": self.lstrip_blocks,
            "escape_output": self.escape_output,
            "strict_mode": self.strict_mode,
            "extra": self.extra
        }


@dataclass
class Template:
    """Template definition"""

    id: str
    name: str
    content: str
    category: TemplateCategory
    description: str = ""
    config: TemplateConfig = field(default_factory=TemplateConfig)
    variable_ids: List[str] = field(default_factory=list)  # Required variables
    parent_id: Optional[str] = None  # For template inheritance
    enabled: bool = True
    version: str = "1.0.0"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Statistics
    render_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_render_time_ms: float = 0.0
    last_rendered_at: Optional[datetime] = None

    def extract_variables(self) -> List[str]:
        """Extract variable names from template content"""
        pattern = re.escape(self.config.variable_start) + r'\s*(\w+)' + re.escape(self.config.variable_end)
        matches = re.findall(pattern, self.content)
        return list(set(matches))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "content": self.content,
            "category": self.category.value,
            "description": self.description,
            "config": self.config.to_dict(),
            "variable_ids": self.variable_ids,
            "parent_id": self.parent_id,
            "enabled": self.enabled,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": self.tags,
            "metadata": self.metadata,
            "render_count": self.render_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_render_time_ms": self.avg_render_time_ms,
            "last_rendered_at": self.last_rendered_at.isoformat() if self.last_rendered_at else None,
            "extracted_variables": self.extract_variables()
        }


class TemplateManager:
    """Manages templates"""

    def __init__(self):
        self.templates: Dict[str, Template] = {}
        self._init_builtin_templates()

    def _init_builtin_templates(self) -> None:
        """Initialize built-in templates"""

        # Cisco-style interface configuration
        self.create_template(
            name="Cisco Interface",
            content="""interface {{ interface_name }}
 description {{ description }}
 ip address {{ ip_address }} {{ subnet_mask }}
 no shutdown
!""",
            category=TemplateCategory.INTERFACE,
            description="Cisco IOS interface configuration",
            tags=["cisco", "ios", "interface"]
        )

        # OSPF configuration
        self.create_template(
            name="OSPF Router",
            content="""router ospf {{ process_id }}
 router-id {{ router_id }}
 network {{ network }} {{ wildcard }} area {{ area }}
!""",
            category=TemplateCategory.ROUTING,
            description="OSPF router configuration",
            tags=["ospf", "routing"]
        )

        # BGP configuration
        self.create_template(
            name="BGP Neighbor",
            content="""router bgp {{ local_asn }}
 neighbor {{ neighbor_ip }} remote-as {{ remote_asn }}
 neighbor {{ neighbor_ip }} description {{ description }}
 neighbor {{ neighbor_ip }} update-source {{ update_source }}
!""",
            category=TemplateCategory.ROUTING,
            description="BGP neighbor configuration",
            tags=["bgp", "routing"]
        )

        # VLAN configuration
        self.create_template(
            name="VLAN",
            content="""vlan {{ vlan_id }}
 name {{ vlan_name }}
!""",
            category=TemplateCategory.VLAN,
            description="VLAN configuration",
            tags=["vlan", "layer2"]
        )

        # Access List
        self.create_template(
            name="Standard ACL",
            content="""ip access-list standard {{ acl_name }}
 permit {{ source_network }} {{ source_wildcard }}
 deny any log
!""",
            category=TemplateCategory.ACL,
            description="Standard IP access list",
            tags=["acl", "security"]
        )

        # Extended ACL
        self.create_template(
            name="Extended ACL",
            content="""ip access-list extended {{ acl_name }}
 permit {{ protocol }} {{ source }} {{ source_wildcard }} {{ destination }} {{ destination_wildcard }} {{ options }}
 deny ip any any log
!""",
            category=TemplateCategory.ACL,
            description="Extended IP access list",
            tags=["acl", "security"]
        )

        # NTP configuration
        self.create_template(
            name="NTP Server",
            content="""ntp server {{ ntp_server }} prefer
ntp source {{ source_interface }}
!""",
            category=TemplateCategory.CONFIGURATION,
            description="NTP server configuration",
            tags=["ntp", "management"]
        )

        # SNMP configuration
        self.create_template(
            name="SNMP v3",
            content="""snmp-server group {{ group_name }} v3 priv
snmp-server user {{ user_name }} {{ group_name }} v3 auth sha {{ auth_password }} priv aes 256 {{ priv_password }}
snmp-server host {{ host }} version 3 priv {{ user_name }}
!""",
            category=TemplateCategory.MONITORING,
            description="SNMPv3 configuration",
            tags=["snmp", "monitoring", "security"]
        )

        # Email notification
        self.create_template(
            name="Alert Email",
            content="""Subject: [{{ severity }}] {{ alert_name }}

Alert: {{ alert_name }}
Severity: {{ severity }}
Time: {{ timestamp }}
Source: {{ source }}

Description:
{{ description }}

Details:
{{ details }}

--
Sent by ADN Platform""",
            category=TemplateCategory.NOTIFICATION,
            description="Alert email notification",
            config=TemplateConfig(output_format=TemplateFormat.TEXT),
            tags=["notification", "email", "alert"]
        )

        # JSON report
        self.create_template(
            name="JSON Status Report",
            content="""{
  "report": {
    "name": "{{ report_name }}",
    "generated_at": "{{ timestamp }}",
    "period": {
      "start": "{{ start_time }}",
      "end": "{{ end_time }}"
    },
    "summary": {
      "total_devices": {{ total_devices }},
      "healthy_devices": {{ healthy_devices }},
      "alerts_count": {{ alerts_count }}
    }
  }
}""",
            category=TemplateCategory.REPORT,
            description="JSON status report",
            config=TemplateConfig(output_format=TemplateFormat.JSON),
            tags=["report", "json"]
        )

    def create_template(
        self,
        name: str,
        content: str,
        category: TemplateCategory,
        description: str = "",
        config: Optional[TemplateConfig] = None,
        variable_ids: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
        version: str = "1.0.0",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Template:
        """Create a new template"""
        template_id = f"tpl_{uuid.uuid4().hex[:8]}"

        template = Template(
            id=template_id,
            name=name,
            content=content,
            category=category,
            description=description,
            config=config or TemplateConfig(),
            variable_ids=variable_ids or [],
            parent_id=parent_id,
            version=version,
            tags=tags or [],
            metadata=metadata or {}
        )

        self.templates[template_id] = template
        return template

    def get_template(self, template_id: str) -> Optional[Template]:
        """Get template by ID"""
        return self.templates.get(template_id)

    def get_template_by_name(self, name: str) -> Optional[Template]:
        """Get template by name"""
        for template in self.templates.values():
            if template.name == name:
                return template
        return None

    def update_template(
        self,
        template_id: str,
        **kwargs
    ) -> Optional[Template]:
        """Update template properties"""
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

    def enable_template(self, template_id: str) -> bool:
        """Enable a template"""
        template = self.templates.get(template_id)
        if template:
            template.enabled = True
            return True
        return False

    def disable_template(self, template_id: str) -> bool:
        """Disable a template"""
        template = self.templates.get(template_id)
        if template:
            template.enabled = False
            return True
        return False

    def clone_template(
        self,
        template_id: str,
        new_name: str
    ) -> Optional[Template]:
        """Clone a template"""
        template = self.templates.get(template_id)
        if not template:
            return None

        return self.create_template(
            name=new_name,
            content=template.content,
            category=template.category,
            description=f"Clone of {template.name}",
            config=template.config,
            variable_ids=template.variable_ids.copy(),
            parent_id=template_id,
            tags=template.tags.copy(),
            metadata=template.metadata.copy()
        )

    def get_templates(
        self,
        category: Optional[TemplateCategory] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[Template]:
        """Get templates with filtering"""
        templates = list(self.templates.values())

        if category:
            templates = [t for t in templates if t.category == category]
        if enabled_only:
            templates = [t for t in templates if t.enabled]
        if tag:
            templates = [t for t in templates if tag in t.tags]

        return templates

    def get_statistics(self) -> dict:
        """Get template statistics"""
        total_renders = 0
        total_successes = 0
        total_failures = 0
        by_category = {}

        for template in self.templates.values():
            total_renders += template.render_count
            total_successes += template.success_count
            total_failures += template.failure_count
            by_category[template.category.value] = by_category.get(template.category.value, 0) + 1

        return {
            "total_templates": len(self.templates),
            "enabled_templates": len([t for t in self.templates.values() if t.enabled]),
            "total_renders": total_renders,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "success_rate": total_successes / total_renders if total_renders > 0 else 1.0,
            "by_category": by_category
        }


# Global template manager instance
_template_manager: Optional[TemplateManager] = None


def get_template_manager() -> TemplateManager:
    """Get or create the global template manager"""
    global _template_manager
    if _template_manager is None:
        _template_manager = TemplateManager()
    return _template_manager
