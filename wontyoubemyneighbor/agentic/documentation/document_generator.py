"""
Network Documentation Generator

Generates comprehensive network documentation including topology diagrams,
IP addressing plans, protocol summaries, and interface descriptions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import json
import logging

logger = logging.getLogger(__name__)


class DocumentFormat(Enum):
    """Supported document output formats."""
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    TEXT = "text"
    PDF = "pdf"  # Requires external library


class DocumentSection(Enum):
    """Document section types."""
    TITLE = "title"
    EXECUTIVE_SUMMARY = "executive_summary"
    TABLE_OF_CONTENTS = "table_of_contents"
    TOPOLOGY_OVERVIEW = "topology_overview"
    TOPOLOGY_DIAGRAM = "topology_diagram"
    AGENT_INVENTORY = "agent_inventory"
    IP_ADDRESSING = "ip_addressing"
    INTERFACE_DESCRIPTIONS = "interface_descriptions"
    PROTOCOL_SUMMARY = "protocol_summary"
    OSPF_CONFIGURATION = "ospf_configuration"
    BGP_CONFIGURATION = "bgp_configuration"
    ISIS_CONFIGURATION = "isis_configuration"
    MPLS_CONFIGURATION = "mpls_configuration"
    VXLAN_CONFIGURATION = "vxlan_configuration"
    ACL_POLICIES = "acl_policies"
    NEIGHBOR_RELATIONSHIPS = "neighbor_relationships"
    ROUTE_TABLES = "route_tables"
    HEALTH_STATUS = "health_status"
    CHANGE_LOG = "change_log"
    APPENDIX = "appendix"


@dataclass
class DocumentTemplate:
    """Template definition for document generation."""
    template_id: str
    name: str
    description: str
    sections: List[DocumentSection]
    include_diagrams: bool = True
    include_configs: bool = True
    include_tables: bool = True
    custom_css: Optional[str] = None
    custom_header: Optional[str] = None
    custom_footer: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "sections": [s.value for s in self.sections],
            "include_diagrams": self.include_diagrams,
            "include_configs": self.include_configs,
            "include_tables": self.include_tables,
            "has_custom_css": self.custom_css is not None,
            "has_custom_header": self.custom_header is not None,
            "has_custom_footer": self.custom_footer is not None
        }


@dataclass
class SectionContent:
    """Content for a single document section."""
    section_type: DocumentSection
    title: str
    content: str
    tables: List[Dict[str, Any]] = field(default_factory=list)
    diagrams: List[str] = field(default_factory=list)
    subsections: List['SectionContent'] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_type": self.section_type.value,
            "title": self.title,
            "content": self.content,
            "tables": self.tables,
            "diagrams": self.diagrams,
            "subsections": [s.to_dict() for s in self.subsections]
        }


@dataclass
class NetworkDocument:
    """A generated network document."""
    document_id: str
    network_name: str
    title: str
    template_id: str
    generated_at: datetime
    sections: List[SectionContent]
    metadata: Dict[str, Any] = field(default_factory=dict)
    export_formats: List[DocumentFormat] = field(default_factory=list)
    exported_files: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "network_name": self.network_name,
            "title": self.title,
            "template_id": self.template_id,
            "generated_at": self.generated_at.isoformat(),
            "sections": [s.to_dict() for s in self.sections],
            "metadata": self.metadata,
            "export_formats": [f.value for f in self.export_formats],
            "exported_files": self.exported_files,
            "section_count": len(self.sections)
        }


class DocumentGenerator:
    """Network documentation generator singleton."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._documents: Dict[str, NetworkDocument] = {}
        self._templates: Dict[str, DocumentTemplate] = {}
        self._init_templates()

        logger.info("DocumentGenerator initialized")

    def _init_templates(self):
        """Initialize built-in document templates."""
        # Full Network Documentation
        self._templates["full"] = DocumentTemplate(
            template_id="full",
            name="Full Network Documentation",
            description="Comprehensive network documentation with all sections",
            sections=[
                DocumentSection.TITLE,
                DocumentSection.EXECUTIVE_SUMMARY,
                DocumentSection.TABLE_OF_CONTENTS,
                DocumentSection.TOPOLOGY_OVERVIEW,
                DocumentSection.TOPOLOGY_DIAGRAM,
                DocumentSection.AGENT_INVENTORY,
                DocumentSection.IP_ADDRESSING,
                DocumentSection.INTERFACE_DESCRIPTIONS,
                DocumentSection.PROTOCOL_SUMMARY,
                DocumentSection.OSPF_CONFIGURATION,
                DocumentSection.BGP_CONFIGURATION,
                DocumentSection.NEIGHBOR_RELATIONSHIPS,
                DocumentSection.ROUTE_TABLES,
                DocumentSection.ACL_POLICIES,
                DocumentSection.HEALTH_STATUS,
                DocumentSection.APPENDIX
            ],
            include_diagrams=True,
            include_configs=True,
            include_tables=True
        )

        # Quick Overview
        self._templates["overview"] = DocumentTemplate(
            template_id="overview",
            name="Quick Overview",
            description="Brief network overview with key information",
            sections=[
                DocumentSection.TITLE,
                DocumentSection.EXECUTIVE_SUMMARY,
                DocumentSection.TOPOLOGY_OVERVIEW,
                DocumentSection.AGENT_INVENTORY,
                DocumentSection.IP_ADDRESSING,
                DocumentSection.HEALTH_STATUS
            ],
            include_diagrams=True,
            include_configs=False,
            include_tables=True
        )

        # IP Addressing Plan
        self._templates["ip_plan"] = DocumentTemplate(
            template_id="ip_plan",
            name="IP Addressing Plan",
            description="Detailed IP addressing documentation",
            sections=[
                DocumentSection.TITLE,
                DocumentSection.TABLE_OF_CONTENTS,
                DocumentSection.TOPOLOGY_OVERVIEW,
                DocumentSection.IP_ADDRESSING,
                DocumentSection.INTERFACE_DESCRIPTIONS,
                DocumentSection.ROUTE_TABLES
            ],
            include_diagrams=True,
            include_configs=False,
            include_tables=True
        )

        # Protocol Configuration Guide
        self._templates["protocol_guide"] = DocumentTemplate(
            template_id="protocol_guide",
            name="Protocol Configuration Guide",
            description="Detailed protocol configurations and relationships",
            sections=[
                DocumentSection.TITLE,
                DocumentSection.TABLE_OF_CONTENTS,
                DocumentSection.PROTOCOL_SUMMARY,
                DocumentSection.OSPF_CONFIGURATION,
                DocumentSection.BGP_CONFIGURATION,
                DocumentSection.ISIS_CONFIGURATION,
                DocumentSection.MPLS_CONFIGURATION,
                DocumentSection.NEIGHBOR_RELATIONSHIPS
            ],
            include_diagrams=True,
            include_configs=True,
            include_tables=True
        )

        # Security Documentation
        self._templates["security"] = DocumentTemplate(
            template_id="security",
            name="Security Documentation",
            description="Network security policies and ACL configurations",
            sections=[
                DocumentSection.TITLE,
                DocumentSection.EXECUTIVE_SUMMARY,
                DocumentSection.TOPOLOGY_OVERVIEW,
                DocumentSection.ACL_POLICIES,
                DocumentSection.INTERFACE_DESCRIPTIONS
            ],
            include_diagrams=True,
            include_configs=True,
            include_tables=True
        )

        # Change Report
        self._templates["change_report"] = DocumentTemplate(
            template_id="change_report",
            name="Change Report",
            description="Document network changes and their impact",
            sections=[
                DocumentSection.TITLE,
                DocumentSection.EXECUTIVE_SUMMARY,
                DocumentSection.CHANGE_LOG,
                DocumentSection.TOPOLOGY_OVERVIEW,
                DocumentSection.HEALTH_STATUS
            ],
            include_diagrams=True,
            include_configs=False,
            include_tables=True
        )

    def get_templates(self) -> List[DocumentTemplate]:
        """Get all available document templates."""
        return list(self._templates.values())

    def get_template(self, template_id: str) -> Optional[DocumentTemplate]:
        """Get a specific template by ID."""
        return self._templates.get(template_id)

    def generate(
        self,
        network_name: str = None,
        sections: List[DocumentSection] = None,
        template: str = None
    ) -> NetworkDocument:
        """Generate network documentation."""
        import uuid

        # Get template or use default
        if template and template in self._templates:
            doc_template = self._templates[template]
        else:
            doc_template = self._templates["full"]

        # Override sections if provided
        if sections:
            doc_sections = sections
        else:
            doc_sections = doc_template.sections

        # Generate document ID
        doc_id = str(uuid.uuid4())[:8]

        # Network name
        if not network_name:
            network_name = "ASI Network"

        # Generate sections
        generated_sections = []
        for section_type in doc_sections:
            content = self._generate_section(section_type, network_name, doc_template)
            if content:
                generated_sections.append(content)

        # Create document
        document = NetworkDocument(
            document_id=doc_id,
            network_name=network_name,
            title=f"{network_name} - Network Documentation",
            template_id=doc_template.template_id,
            generated_at=datetime.now(),
            sections=generated_sections,
            metadata={
                "generator": "ASI Document Generator",
                "version": "1.0.0",
                "template_name": doc_template.name
            },
            export_formats=[DocumentFormat.MARKDOWN, DocumentFormat.HTML, DocumentFormat.JSON]
        )

        self._documents[doc_id] = document
        logger.info(f"Generated document {doc_id} with {len(generated_sections)} sections")

        return document

    def _generate_section(
        self,
        section_type: DocumentSection,
        network_name: str,
        template: DocumentTemplate
    ) -> Optional[SectionContent]:
        """Generate content for a specific section."""
        try:
            # Try to get actual network data
            agents = self._get_agents()
            topology = self._get_topology()
        except Exception as e:
            logger.warning(f"Could not fetch network data: {e}")
            agents = []
            topology = {"nodes": [], "links": []}

        generators = {
            DocumentSection.TITLE: self._gen_title,
            DocumentSection.EXECUTIVE_SUMMARY: self._gen_executive_summary,
            DocumentSection.TABLE_OF_CONTENTS: self._gen_toc,
            DocumentSection.TOPOLOGY_OVERVIEW: self._gen_topology_overview,
            DocumentSection.TOPOLOGY_DIAGRAM: self._gen_topology_diagram,
            DocumentSection.AGENT_INVENTORY: self._gen_agent_inventory,
            DocumentSection.IP_ADDRESSING: self._gen_ip_addressing,
            DocumentSection.INTERFACE_DESCRIPTIONS: self._gen_interface_descriptions,
            DocumentSection.PROTOCOL_SUMMARY: self._gen_protocol_summary,
            DocumentSection.OSPF_CONFIGURATION: self._gen_ospf_config,
            DocumentSection.BGP_CONFIGURATION: self._gen_bgp_config,
            DocumentSection.ISIS_CONFIGURATION: self._gen_isis_config,
            DocumentSection.MPLS_CONFIGURATION: self._gen_mpls_config,
            DocumentSection.VXLAN_CONFIGURATION: self._gen_vxlan_config,
            DocumentSection.ACL_POLICIES: self._gen_acl_policies,
            DocumentSection.NEIGHBOR_RELATIONSHIPS: self._gen_neighbor_relationships,
            DocumentSection.ROUTE_TABLES: self._gen_route_tables,
            DocumentSection.HEALTH_STATUS: self._gen_health_status,
            DocumentSection.CHANGE_LOG: self._gen_change_log,
            DocumentSection.APPENDIX: self._gen_appendix
        }

        generator = generators.get(section_type)
        if generator:
            return generator(network_name, agents, topology, template)
        return None

    def _get_agents(self) -> List[Dict[str, Any]]:
        """Get agent data from the network."""
        try:
            from agentic.network import get_all_agents
            agents = get_all_agents()
            return [a.to_dict() if hasattr(a, 'to_dict') else a for a in agents]
        except Exception:
            return []

    def _get_topology(self) -> Dict[str, Any]:
        """Get topology data from the network."""
        try:
            from agentic.network import get_topology
            return get_topology()
        except Exception:
            return {"nodes": [], "links": []}

    def _gen_title(self, network_name, agents, topology, template) -> SectionContent:
        """Generate title section."""
        now = datetime.now()
        content = f"""
# {network_name} - Network Documentation

**Generated:** {now.strftime('%Y-%m-%d %H:%M:%S')}

**Template:** {template.name}

---
"""
        return SectionContent(
            section_type=DocumentSection.TITLE,
            title="",
            content=content
        )

    def _gen_executive_summary(self, network_name, agents, topology, template) -> SectionContent:
        """Generate executive summary."""
        node_count = len(topology.get("nodes", [])) if topology else len(agents)
        link_count = len(topology.get("links", [])) if topology else 0

        # Count protocols
        protocols = set()
        for agent in agents:
            if isinstance(agent, dict):
                agent_protocols = agent.get("protocols", [])
                if isinstance(agent_protocols, list):
                    protocols.update(agent_protocols)

        content = f"""
## Executive Summary

This document provides comprehensive documentation for the **{network_name}** network infrastructure.

### Key Statistics

| Metric | Value |
|--------|-------|
| Total Devices | {node_count} |
| Network Links | {link_count} |
| Protocols in Use | {', '.join(protocols) if protocols else 'N/A'} |
| Documentation Date | {datetime.now().strftime('%Y-%m-%d')} |

### Network Overview

The {network_name} network consists of {node_count} devices interconnected via {link_count} links.
The network implements {len(protocols)} routing protocol(s) to provide connectivity and redundancy.
"""
        return SectionContent(
            section_type=DocumentSection.EXECUTIVE_SUMMARY,
            title="Executive Summary",
            content=content,
            tables=[{
                "name": "Key Statistics",
                "headers": ["Metric", "Value"],
                "rows": [
                    ["Total Devices", str(node_count)],
                    ["Network Links", str(link_count)],
                    ["Protocols", ', '.join(protocols) if protocols else 'N/A']
                ]
            }]
        )

    def _gen_toc(self, network_name, agents, topology, template) -> SectionContent:
        """Generate table of contents."""
        toc_items = []
        for i, section in enumerate(template.sections, 1):
            if section != DocumentSection.TABLE_OF_CONTENTS:
                toc_items.append(f"{i}. {section.value.replace('_', ' ').title()}")

        content = "## Table of Contents\n\n" + "\n".join(toc_items)
        return SectionContent(
            section_type=DocumentSection.TABLE_OF_CONTENTS,
            title="Table of Contents",
            content=content
        )

    def _gen_topology_overview(self, network_name, agents, topology, template) -> SectionContent:
        """Generate topology overview."""
        nodes = topology.get("nodes", [])
        links = topology.get("links", [])

        # Group nodes by type
        node_types = {}
        for node in nodes:
            ntype = node.get("type", "unknown")
            if ntype not in node_types:
                node_types[ntype] = []
            node_types[ntype].append(node.get("name", node.get("id", "Unknown")))

        type_summary = "\n".join([
            f"- **{t.title()}s**: {', '.join(names)}"
            for t, names in node_types.items()
        ])

        content = f"""
## Topology Overview

### Network Devices

The network contains {len(nodes)} devices:

{type_summary if type_summary else '- No devices found'}

### Network Links

The network has {len(links)} interconnections between devices.
"""

        # Build links table
        link_rows = []
        for link in links[:20]:  # Limit to 20 links
            source = link.get("source", "Unknown")
            target = link.get("target", "Unknown")
            link_type = link.get("type", "P2P")
            link_rows.append([source, target, link_type])

        return SectionContent(
            section_type=DocumentSection.TOPOLOGY_OVERVIEW,
            title="Topology Overview",
            content=content,
            tables=[{
                "name": "Network Links",
                "headers": ["Source", "Target", "Type"],
                "rows": link_rows
            }] if link_rows else []
        )

    def _gen_topology_diagram(self, network_name, agents, topology, template) -> SectionContent:
        """Generate topology diagram section."""
        # Generate ASCII diagram
        nodes = topology.get("nodes", [])
        links = topology.get("links", [])

        if not nodes:
            diagram = "No topology data available."
        else:
            # Simple ASCII representation
            diagram_lines = ["```"]
            diagram_lines.append(f"    {network_name} Topology")
            diagram_lines.append("    " + "=" * len(network_name + " Topology"))
            diagram_lines.append("")

            for node in nodes[:10]:  # Limit to 10 nodes
                name = node.get("name", node.get("id", "?"))
                ntype = node.get("type", "device")
                diagram_lines.append(f"    [{name}] ({ntype})")

            if links:
                diagram_lines.append("")
                diagram_lines.append("    Connections:")
                for link in links[:10]:  # Limit to 10 links
                    src = link.get("source", "?")
                    dst = link.get("target", "?")
                    diagram_lines.append(f"      {src} <---> {dst}")

            diagram_lines.append("```")
            diagram = "\n".join(diagram_lines)

        content = f"""
## Topology Diagram

{diagram}

*Note: For a detailed interactive topology view, use the 3D Topology Viewer in the dashboard.*
"""
        return SectionContent(
            section_type=DocumentSection.TOPOLOGY_DIAGRAM,
            title="Topology Diagram",
            content=content,
            diagrams=[diagram]
        )

    def _gen_agent_inventory(self, network_name, agents, topology, template) -> SectionContent:
        """Generate agent inventory."""
        rows = []
        for agent in agents:
            if isinstance(agent, dict):
                name = agent.get("name", agent.get("agent_id", "Unknown"))
                agent_type = agent.get("type", agent.get("agent_type", "router"))
                status = agent.get("status", "unknown")
                loopback = agent.get("loopback", agent.get("loopback_ip", "N/A"))
                protocols = ", ".join(agent.get("protocols", [])) if agent.get("protocols") else "N/A"
                rows.append([name, agent_type, status, loopback, protocols])

        content = f"""
## Agent Inventory

This section lists all network agents/devices in the {network_name} network.

| Name | Type | Status | Loopback IP | Protocols |
|------|------|--------|-------------|-----------|
"""
        for row in rows:
            content += f"| {' | '.join(row)} |\n"

        if not rows:
            content += "| No agents found | - | - | - | - |\n"

        return SectionContent(
            section_type=DocumentSection.AGENT_INVENTORY,
            title="Agent Inventory",
            content=content,
            tables=[{
                "name": "Agent Inventory",
                "headers": ["Name", "Type", "Status", "Loopback IP", "Protocols"],
                "rows": rows
            }]
        )

    def _gen_ip_addressing(self, network_name, agents, topology, template) -> SectionContent:
        """Generate IP addressing plan."""
        # Collect all IP addresses
        ipv4_addresses = []
        ipv6_addresses = []
        subnets = set()

        for agent in agents:
            if isinstance(agent, dict):
                name = agent.get("name", "Unknown")

                # Loopback addresses
                loopback = agent.get("loopback", agent.get("loopback_ip"))
                if loopback:
                    ipv4_addresses.append([name, "loopback0", loopback, "Loopback"])

                loopback_v6 = agent.get("loopback_ipv6")
                if loopback_v6:
                    ipv6_addresses.append([name, "loopback0", loopback_v6, "Loopback"])

                # Interface addresses
                interfaces = agent.get("interfaces", [])
                for iface in interfaces:
                    if isinstance(iface, dict):
                        iface_name = iface.get("name", "Unknown")
                        ipv4 = iface.get("ipv4", iface.get("ip_address"))
                        ipv6 = iface.get("ipv6", iface.get("ipv6_address"))
                        desc = iface.get("description", "Interface")

                        if ipv4:
                            ipv4_addresses.append([name, iface_name, ipv4, desc])
                            # Extract subnet
                            if "/" in str(ipv4):
                                subnet = ipv4.rsplit(".", 1)[0] + ".0/" + ipv4.split("/")[1]
                                subnets.add(subnet)
                        if ipv6:
                            ipv6_addresses.append([name, iface_name, ipv6, desc])

        content = f"""
## IP Addressing Plan

### IPv4 Addresses

| Device | Interface | IPv4 Address | Description |
|--------|-----------|--------------|-------------|
"""
        for row in ipv4_addresses[:50]:  # Limit to 50
            content += f"| {' | '.join(str(c) for c in row)} |\n"
        if not ipv4_addresses:
            content += "| No IPv4 addresses found | - | - | - |\n"

        content += f"""

### IPv6 Addresses

| Device | Interface | IPv6 Address | Description |
|--------|-----------|--------------|-------------|
"""
        for row in ipv6_addresses[:50]:
            content += f"| {' | '.join(str(c) for c in row)} |\n"
        if not ipv6_addresses:
            content += "| No IPv6 addresses found | - | - | - |\n"

        content += f"""

### Subnet Summary

The network uses the following subnets:
"""
        for subnet in sorted(subnets)[:20]:
            content += f"- {subnet}\n"
        if not subnets:
            content += "- No subnets identified\n"

        return SectionContent(
            section_type=DocumentSection.IP_ADDRESSING,
            title="IP Addressing Plan",
            content=content,
            tables=[
                {
                    "name": "IPv4 Addresses",
                    "headers": ["Device", "Interface", "IPv4 Address", "Description"],
                    "rows": ipv4_addresses
                },
                {
                    "name": "IPv6 Addresses",
                    "headers": ["Device", "Interface", "IPv6 Address", "Description"],
                    "rows": ipv6_addresses
                }
            ]
        )

    def _gen_interface_descriptions(self, network_name, agents, topology, template) -> SectionContent:
        """Generate interface descriptions."""
        rows = []
        for agent in agents:
            if isinstance(agent, dict):
                name = agent.get("name", "Unknown")
                interfaces = agent.get("interfaces", [])
                for iface in interfaces:
                    if isinstance(iface, dict):
                        iface_name = iface.get("name", "Unknown")
                        state = iface.get("state", iface.get("admin_state", "unknown"))
                        speed = iface.get("speed", "auto")
                        mtu = iface.get("mtu", "1500")
                        desc = iface.get("description", "-")
                        rows.append([name, iface_name, state, str(speed), str(mtu), desc])

        content = f"""
## Interface Descriptions

| Device | Interface | State | Speed | MTU | Description |
|--------|-----------|-------|-------|-----|-------------|
"""
        for row in rows[:100]:  # Limit to 100
            content += f"| {' | '.join(row)} |\n"
        if not rows:
            content += "| No interfaces found | - | - | - | - | - |\n"

        return SectionContent(
            section_type=DocumentSection.INTERFACE_DESCRIPTIONS,
            title="Interface Descriptions",
            content=content,
            tables=[{
                "name": "Interface Descriptions",
                "headers": ["Device", "Interface", "State", "Speed", "MTU", "Description"],
                "rows": rows
            }]
        )

    def _gen_protocol_summary(self, network_name, agents, topology, template) -> SectionContent:
        """Generate protocol summary."""
        protocol_stats = {}
        for agent in agents:
            if isinstance(agent, dict):
                protocols = agent.get("protocols", [])
                for proto in protocols:
                    if proto not in protocol_stats:
                        protocol_stats[proto] = {"count": 0, "agents": []}
                    protocol_stats[proto]["count"] += 1
                    protocol_stats[proto]["agents"].append(agent.get("name", "Unknown"))

        content = f"""
## Protocol Summary

### Protocols in Use

"""
        for proto, stats in protocol_stats.items():
            content += f"""
#### {proto.upper()}

- **Devices Running**: {stats['count']}
- **Device List**: {', '.join(stats['agents'][:10])}{'...' if len(stats['agents']) > 10 else ''}
"""

        if not protocol_stats:
            content += "No protocols configured.\n"

        rows = [[proto, str(stats["count"]), ", ".join(stats["agents"][:5])]
                for proto, stats in protocol_stats.items()]

        return SectionContent(
            section_type=DocumentSection.PROTOCOL_SUMMARY,
            title="Protocol Summary",
            content=content,
            tables=[{
                "name": "Protocol Summary",
                "headers": ["Protocol", "Device Count", "Devices"],
                "rows": rows
            }]
        )

    def _gen_ospf_config(self, network_name, agents, topology, template) -> SectionContent:
        """Generate OSPF configuration section."""
        ospf_agents = []
        for agent in agents:
            if isinstance(agent, dict):
                protocols = agent.get("protocols", [])
                if "ospf" in [p.lower() for p in protocols]:
                    ospf_agents.append(agent)

        content = f"""
## OSPF Configuration

### OSPF Overview

{len(ospf_agents)} device(s) are running OSPF in this network.

### OSPF Router IDs and Areas

| Router | Router ID | Area | Networks |
|--------|-----------|------|----------|
"""
        for agent in ospf_agents:
            name = agent.get("name", "Unknown")
            router_id = agent.get("ospf_router_id", agent.get("loopback", "N/A"))
            area = agent.get("ospf_area", "0")
            networks = agent.get("ospf_networks", [])
            net_str = ", ".join(networks[:3]) if networks else "N/A"
            content += f"| {name} | {router_id} | {area} | {net_str} |\n"

        if not ospf_agents:
            content += "| No OSPF routers | - | - | - |\n"

        return SectionContent(
            section_type=DocumentSection.OSPF_CONFIGURATION,
            title="OSPF Configuration",
            content=content
        )

    def _gen_bgp_config(self, network_name, agents, topology, template) -> SectionContent:
        """Generate BGP configuration section."""
        bgp_agents = []
        for agent in agents:
            if isinstance(agent, dict):
                protocols = agent.get("protocols", [])
                if "bgp" in [p.lower() for p in protocols]:
                    bgp_agents.append(agent)

        content = f"""
## BGP Configuration

### BGP Overview

{len(bgp_agents)} device(s) are running BGP in this network.

### BGP AS Numbers and Peers

| Router | AS Number | Router ID | Peers |
|--------|-----------|-----------|-------|
"""
        for agent in bgp_agents:
            name = agent.get("name", "Unknown")
            asn = agent.get("bgp_asn", agent.get("as_number", "N/A"))
            router_id = agent.get("bgp_router_id", agent.get("loopback", "N/A"))
            peers = agent.get("bgp_peers", [])
            peer_str = str(len(peers)) if isinstance(peers, list) else str(peers)
            content += f"| {name} | {asn} | {router_id} | {peer_str} |\n"

        if not bgp_agents:
            content += "| No BGP routers | - | - | - |\n"

        return SectionContent(
            section_type=DocumentSection.BGP_CONFIGURATION,
            title="BGP Configuration",
            content=content
        )

    def _gen_isis_config(self, network_name, agents, topology, template) -> SectionContent:
        """Generate IS-IS configuration section."""
        isis_agents = []
        for agent in agents:
            if isinstance(agent, dict):
                protocols = agent.get("protocols", [])
                if "isis" in [p.lower() for p in protocols]:
                    isis_agents.append(agent)

        content = f"""
## IS-IS Configuration

### IS-IS Overview

{len(isis_agents)} device(s) are running IS-IS in this network.

### IS-IS System IDs and Levels

| Router | System ID | NET | Level |
|--------|-----------|-----|-------|
"""
        for agent in isis_agents:
            name = agent.get("name", "Unknown")
            system_id = agent.get("isis_system_id", "N/A")
            net = agent.get("isis_net", "N/A")
            level = agent.get("isis_level", "L1L2")
            content += f"| {name} | {system_id} | {net} | {level} |\n"

        if not isis_agents:
            content += "| No IS-IS routers | - | - | - |\n"

        return SectionContent(
            section_type=DocumentSection.ISIS_CONFIGURATION,
            title="IS-IS Configuration",
            content=content
        )

    def _gen_mpls_config(self, network_name, agents, topology, template) -> SectionContent:
        """Generate MPLS configuration section."""
        mpls_agents = []
        for agent in agents:
            if isinstance(agent, dict):
                protocols = agent.get("protocols", [])
                if "mpls" in [p.lower() for p in protocols] or "ldp" in [p.lower() for p in protocols]:
                    mpls_agents.append(agent)

        content = f"""
## MPLS Configuration

### MPLS Overview

{len(mpls_agents)} device(s) are running MPLS in this network.

### MPLS Label Distribution

| Router | LDP Router ID | Label Range | Enabled Interfaces |
|--------|---------------|-------------|-------------------|
"""
        for agent in mpls_agents:
            name = agent.get("name", "Unknown")
            ldp_rid = agent.get("ldp_router_id", agent.get("loopback", "N/A"))
            label_range = agent.get("mpls_label_range", "16-1048575")
            interfaces = agent.get("mpls_interfaces", [])
            iface_str = ", ".join(interfaces[:3]) if interfaces else "All"
            content += f"| {name} | {ldp_rid} | {label_range} | {iface_str} |\n"

        if not mpls_agents:
            content += "| No MPLS routers | - | - | - |\n"

        return SectionContent(
            section_type=DocumentSection.MPLS_CONFIGURATION,
            title="MPLS Configuration",
            content=content
        )

    def _gen_vxlan_config(self, network_name, agents, topology, template) -> SectionContent:
        """Generate VXLAN configuration section."""
        vxlan_agents = []
        for agent in agents:
            if isinstance(agent, dict):
                protocols = agent.get("protocols", [])
                if "vxlan" in [p.lower() for p in protocols] or "evpn" in [p.lower() for p in protocols]:
                    vxlan_agents.append(agent)

        content = f"""
## VXLAN Configuration

### VXLAN Overview

{len(vxlan_agents)} device(s) are running VXLAN/EVPN in this network.

### VXLAN VTEPs

| Router | VTEP IP | VNIs | Underlay Protocol |
|--------|---------|------|-------------------|
"""
        for agent in vxlan_agents:
            name = agent.get("name", "Unknown")
            vtep_ip = agent.get("vtep_ip", agent.get("loopback", "N/A"))
            vnis = agent.get("vxlan_vnis", [])
            vni_str = ", ".join(str(v) for v in vnis[:5]) if vnis else "N/A"
            underlay = agent.get("vxlan_underlay", "BGP-EVPN")
            content += f"| {name} | {vtep_ip} | {vni_str} | {underlay} |\n"

        if not vxlan_agents:
            content += "| No VXLAN VTEPs | - | - | - |\n"

        return SectionContent(
            section_type=DocumentSection.VXLAN_CONFIGURATION,
            title="VXLAN Configuration",
            content=content
        )

    def _gen_acl_policies(self, network_name, agents, topology, template) -> SectionContent:
        """Generate ACL policies section."""
        content = f"""
## ACL Policies

### Access Control Lists

This section documents the ACL configurations across the network.

*Note: Detailed ACL rules can be viewed in the Firewall tab of each agent's dashboard.*

### ACL Summary by Device

| Device | ACL Count | Applied Interfaces | Rules Total |
|--------|-----------|-------------------|-------------|
"""
        # Try to get firewall data
        try:
            from agentic.security import get_firewall_manager
            for agent in agents:
                if isinstance(agent, dict):
                    name = agent.get("name", "Unknown")
                    # Placeholder - would query actual firewall manager
                    content += f"| {name} | 0 | - | 0 |\n"
        except Exception:
            for agent in agents[:10]:
                if isinstance(agent, dict):
                    name = agent.get("name", "Unknown")
                    content += f"| {name} | N/A | N/A | N/A |\n"

        if not agents:
            content += "| No devices | - | - | - |\n"

        return SectionContent(
            section_type=DocumentSection.ACL_POLICIES,
            title="ACL Policies",
            content=content
        )

    def _gen_neighbor_relationships(self, network_name, agents, topology, template) -> SectionContent:
        """Generate neighbor relationships section."""
        content = f"""
## Neighbor Relationships

### Protocol Adjacencies

This section documents the protocol neighbor relationships in the network.

"""
        # OSPF Neighbors
        content += """
### OSPF Neighbors

| Router | Neighbor | State | Interface | Area |
|--------|----------|-------|-----------|------|
"""
        ospf_found = False
        for agent in agents:
            if isinstance(agent, dict):
                neighbors = agent.get("ospf_neighbors", [])
                for neighbor in neighbors[:10]:
                    if isinstance(neighbor, dict):
                        ospf_found = True
                        content += f"| {agent.get('name', '?')} | {neighbor.get('neighbor_id', '?')} | {neighbor.get('state', '?')} | {neighbor.get('interface', '?')} | {neighbor.get('area', '0')} |\n"
        if not ospf_found:
            content += "| No OSPF neighbors found | - | - | - | - |\n"

        # BGP Neighbors
        content += """

### BGP Peers

| Router | Peer Address | Remote AS | State | Up/Down |
|--------|--------------|-----------|-------|---------|
"""
        bgp_found = False
        for agent in agents:
            if isinstance(agent, dict):
                peers = agent.get("bgp_peers", agent.get("bgp_neighbors", []))
                for peer in peers[:10]:
                    if isinstance(peer, dict):
                        bgp_found = True
                        content += f"| {agent.get('name', '?')} | {peer.get('peer_address', '?')} | {peer.get('remote_as', '?')} | {peer.get('state', '?')} | {peer.get('uptime', '?')} |\n"
        if not bgp_found:
            content += "| No BGP peers found | - | - | - | - |\n"

        return SectionContent(
            section_type=DocumentSection.NEIGHBOR_RELATIONSHIPS,
            title="Neighbor Relationships",
            content=content
        )

    def _gen_route_tables(self, network_name, agents, topology, template) -> SectionContent:
        """Generate route tables section."""
        content = f"""
## Route Tables

### Routing Information Base Summary

| Device | IPv4 Routes | IPv6 Routes | OSPF | BGP | Connected | Static |
|--------|-------------|-------------|------|-----|-----------|--------|
"""
        for agent in agents[:20]:
            if isinstance(agent, dict):
                name = agent.get("name", "Unknown")
                routes = agent.get("routes", {})
                if isinstance(routes, dict):
                    ipv4 = routes.get("ipv4_count", routes.get("total", 0))
                    ipv6 = routes.get("ipv6_count", 0)
                    ospf = routes.get("ospf", 0)
                    bgp = routes.get("bgp", 0)
                    connected = routes.get("connected", 0)
                    static = routes.get("static", 0)
                else:
                    ipv4 = ipv6 = ospf = bgp = connected = static = "N/A"
                content += f"| {name} | {ipv4} | {ipv6} | {ospf} | {bgp} | {connected} | {static} |\n"

        if not agents:
            content += "| No devices | - | - | - | - | - | - |\n"

        content += """

*Note: For detailed route tables, use the Routes tab in each agent's dashboard.*
"""
        return SectionContent(
            section_type=DocumentSection.ROUTE_TABLES,
            title="Route Tables",
            content=content
        )

    def _gen_health_status(self, network_name, agents, topology, template) -> SectionContent:
        """Generate health status section."""
        # Try to get health data
        try:
            from agentic.health import get_health_scorer
            scorer = get_health_scorer()
            health = scorer.get_network_health()
            score = health.overall_score if hasattr(health, 'overall_score') else 0
            severity = health.severity.value if hasattr(health, 'severity') else "unknown"
        except Exception:
            score = "N/A"
            severity = "N/A"

        content = f"""
## Health Status

### Network Health Overview

| Metric | Value |
|--------|-------|
| Overall Health Score | {score} |
| Health Severity | {severity} |
| Total Devices | {len(agents)} |
| Devices Online | {sum(1 for a in agents if isinstance(a, dict) and a.get('status') == 'running')} |

### Agent Health Status

| Device | Status | Health Score | Issues |
|--------|--------|--------------|--------|
"""
        for agent in agents[:20]:
            if isinstance(agent, dict):
                name = agent.get("name", "Unknown")
                status = agent.get("status", "unknown")
                agent_score = agent.get("health_score", "N/A")
                issues = agent.get("issues", 0)
                content += f"| {name} | {status} | {agent_score} | {issues} |\n"

        if not agents:
            content += "| No devices | - | - | - |\n"

        return SectionContent(
            section_type=DocumentSection.HEALTH_STATUS,
            title="Health Status",
            content=content
        )

    def _gen_change_log(self, network_name, agents, topology, template) -> SectionContent:
        """Generate change log section."""
        content = f"""
## Change Log

### Recent Changes

| Timestamp | Type | Device | Description |
|-----------|------|--------|-------------|
| {datetime.now().strftime('%Y-%m-%d %H:%M')} | Documentation | - | Documentation generated |

*Note: For detailed change history, use the Time Travel feature in the dashboard.*
"""
        return SectionContent(
            section_type=DocumentSection.CHANGE_LOG,
            title="Change Log",
            content=content
        )

    def _gen_appendix(self, network_name, agents, topology, template) -> SectionContent:
        """Generate appendix section."""
        content = f"""
## Appendix

### Document Information

- **Network Name**: {network_name}
- **Generated By**: ASI Document Generator v1.0.0
- **Generated At**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **Template Used**: {template.name}

### Abbreviations

| Abbreviation | Meaning |
|--------------|---------|
| ASI | Agent-Simulated Infrastructure |
| BGP | Border Gateway Protocol |
| OSPF | Open Shortest Path First |
| IS-IS | Intermediate System to Intermediate System |
| MPLS | Multi-Protocol Label Switching |
| VXLAN | Virtual Extensible LAN |
| EVPN | Ethernet VPN |
| LDP | Label Distribution Protocol |
| ACL | Access Control List |
| LLDP | Link Layer Discovery Protocol |
| LACP | Link Aggregation Control Protocol |

### References

- OSPF: RFC 2328 (OSPFv2), RFC 5340 (OSPFv3)
- BGP: RFC 4271 (BGP-4)
- IS-IS: RFC 1142, RFC 5308 (IPv6)
- MPLS: RFC 3031
- VXLAN: RFC 7348
- EVPN: RFC 7432

---

*End of Document*
"""
        return SectionContent(
            section_type=DocumentSection.APPENDIX,
            title="Appendix",
            content=content
        )

    def export(
        self,
        document: NetworkDocument,
        format: DocumentFormat,
        output_path: str = None
    ) -> str:
        """Export document to specified format."""
        exporters = {
            DocumentFormat.MARKDOWN: self._export_markdown,
            DocumentFormat.HTML: self._export_html,
            DocumentFormat.JSON: self._export_json,
            DocumentFormat.TEXT: self._export_text
        }

        exporter = exporters.get(format)
        if not exporter:
            raise ValueError(f"Unsupported format: {format}")

        content = exporter(document)

        # Save to file if path provided
        if output_path:
            with open(output_path, 'w') as f:
                f.write(content)
            document.exported_files[format.value] = output_path
            logger.info(f"Exported document to {output_path}")

        return content

    def _export_markdown(self, document: NetworkDocument) -> str:
        """Export document to Markdown format."""
        md = ""
        for section in document.sections:
            md += section.content + "\n\n"
        return md

    def _export_html(self, document: NetworkDocument) -> str:
        """Export document to HTML format."""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{document.title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
            color: #333;
            background: #f8f9fa;
        }}
        h1, h2, h3 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 0.5rem;
        }}
        h1 {{
            text-align: center;
            border-bottom: 3px solid #2c3e50;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
            background: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th, td {{
            padding: 0.75rem;
            text-align: left;
            border: 1px solid #dee2e6;
        }}
        th {{
            background: #3498db;
            color: white;
            font-weight: 600;
        }}
        tr:nth-child(even) {{
            background: #f8f9fa;
        }}
        tr:hover {{
            background: #e9ecef;
        }}
        code, pre {{
            background: #2c3e50;
            color: #ecf0f1;
            padding: 0.2rem 0.5rem;
            border-radius: 3px;
            font-family: 'Monaco', 'Menlo', monospace;
        }}
        pre {{
            padding: 1rem;
            overflow-x: auto;
        }}
        .metadata {{
            color: #7f8c8d;
            font-size: 0.9rem;
            text-align: center;
            margin-bottom: 2rem;
        }}
        hr {{
            border: none;
            border-top: 1px solid #bdc3c7;
            margin: 2rem 0;
        }}
    </style>
</head>
<body>
    <div class="metadata">
        Generated: {document.generated_at.strftime('%Y-%m-%d %H:%M:%S')} |
        Template: {document.metadata.get('template_name', 'Default')}
    </div>
"""
        # Convert markdown to basic HTML
        for section in document.sections:
            content = section.content
            # Basic markdown to HTML conversion
            lines = content.split('\n')
            for line in lines:
                if line.startswith('# '):
                    html += f"<h1>{line[2:]}</h1>\n"
                elif line.startswith('## '):
                    html += f"<h2>{line[3:]}</h2>\n"
                elif line.startswith('### '):
                    html += f"<h3>{line[4:]}</h3>\n"
                elif line.startswith('#### '):
                    html += f"<h4>{line[5:]}</h4>\n"
                elif line.startswith('| '):
                    # Table row
                    if '---|' in line:
                        continue  # Skip separator
                    cells = [c.strip() for c in line.split('|')[1:-1]]
                    if cells and all('**' not in c for c in cells):
                        html += "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>\n"
                    else:
                        html += "<thead><tr>" + "".join(f"<th>{c.replace('**', '')}</th>" for c in cells) + "</tr></thead><tbody>\n"
                elif line.startswith('- '):
                    html += f"<li>{line[2:]}</li>\n"
                elif line.startswith('```'):
                    if 'pre_open' not in locals() or not pre_open:
                        html += "<pre><code>"
                        pre_open = True
                    else:
                        html += "</code></pre>\n"
                        pre_open = False
                elif line.strip():
                    html += f"<p>{line}</p>\n"

        html += """
</body>
</html>
"""
        return html

    def _export_json(self, document: NetworkDocument) -> str:
        """Export document to JSON format."""
        return json.dumps(document.to_dict(), indent=2, default=str)

    def _export_text(self, document: NetworkDocument) -> str:
        """Export document to plain text format."""
        text = ""
        for section in document.sections:
            content = section.content
            # Strip markdown formatting
            content = content.replace('#', '')
            content = content.replace('**', '')
            content = content.replace('*', '')
            content = content.replace('`', '')
            text += content + "\n\n"
        return text

    def get_document(self, document_id: str) -> Optional[NetworkDocument]:
        """Get a previously generated document by ID."""
        return self._documents.get(document_id)

    def list_documents(self) -> List[NetworkDocument]:
        """List all generated documents."""
        return list(self._documents.values())

    def delete_document(self, document_id: str) -> bool:
        """Delete a document."""
        if document_id in self._documents:
            del self._documents[document_id]
            return True
        return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get generator statistics."""
        return {
            "documents_generated": len(self._documents),
            "templates_available": len(self._templates),
            "templates": [t.name for t in self._templates.values()],
            "export_formats": [f.value for f in DocumentFormat],
            "section_types": [s.value for s in DocumentSection]
        }
