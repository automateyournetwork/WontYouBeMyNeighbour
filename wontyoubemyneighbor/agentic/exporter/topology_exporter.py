"""
Network Topology Exporter

Exports network topology to various formats for use with other tools
like Graphviz, GNS3, Containerlab, and more.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import logging
import yaml

logger = logging.getLogger(__name__)


class ExportFormat(Enum):
    """Supported export formats."""
    DOT = "dot"                   # Graphviz DOT format
    JSON = "json"                 # JSON format
    YAML = "yaml"                 # YAML format
    GNS3 = "gns3"                 # GNS3 project format
    CONTAINERLAB = "containerlab" # Containerlab topology
    NETBOX = "netbox"             # NetBox import format
    D2 = "d2"                     # D2 diagram format
    MERMAID = "mermaid"           # Mermaid diagram format
    CYJS = "cyjs"                 # Cytoscape.js JSON
    CSV = "csv"                   # CSV format (nodes and links)


@dataclass
class ExportOptions:
    """Options for topology export."""
    include_configs: bool = True
    include_interfaces: bool = True
    include_routing: bool = True
    include_metadata: bool = True
    filter_agents: Optional[List[str]] = None
    filter_protocols: Optional[List[str]] = None
    layout: str = "hierarchical"  # hierarchical, circular, grid
    node_shape: str = "box"
    link_style: str = "solid"
    include_labels: bool = True
    compress: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "include_configs": self.include_configs,
            "include_interfaces": self.include_interfaces,
            "include_routing": self.include_routing,
            "include_metadata": self.include_metadata,
            "filter_agents": self.filter_agents,
            "filter_protocols": self.filter_protocols,
            "layout": self.layout,
            "node_shape": self.node_shape,
            "link_style": self.link_style,
            "include_labels": self.include_labels,
            "compress": self.compress
        }


@dataclass
class ExportResult:
    """Result of an export operation."""
    format: ExportFormat
    content: str
    filename: str
    exported_at: datetime
    node_count: int
    link_count: int
    options: ExportOptions
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format.value,
            "content": self.content,
            "filename": self.filename,
            "exported_at": self.exported_at.isoformat(),
            "node_count": self.node_count,
            "link_count": self.link_count,
            "options": self.options.to_dict(),
            "metadata": self.metadata,
            "content_length": len(self.content)
        }


class TopologyExporter:
    """Network topology exporter."""

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

        self._exports: List[ExportResult] = []
        self._max_history = 50

        logger.info("TopologyExporter initialized")

    def export(
        self,
        format: ExportFormat,
        options: ExportOptions = None
    ) -> ExportResult:
        """Export topology to specified format."""
        if options is None:
            options = ExportOptions()

        # Get topology data
        nodes, links = self._get_topology(options)

        # Generate content based on format
        exporters = {
            ExportFormat.DOT: self._export_dot,
            ExportFormat.JSON: self._export_json,
            ExportFormat.YAML: self._export_yaml,
            ExportFormat.GNS3: self._export_gns3,
            ExportFormat.CONTAINERLAB: self._export_containerlab,
            ExportFormat.NETBOX: self._export_netbox,
            ExportFormat.D2: self._export_d2,
            ExportFormat.MERMAID: self._export_mermaid,
            ExportFormat.CYJS: self._export_cyjs,
            ExportFormat.CSV: self._export_csv,
        }

        exporter_func = exporters.get(format)
        if not exporter_func:
            raise ValueError(f"Unsupported format: {format}")

        content = exporter_func(nodes, links, options)

        # Determine filename
        ext_map = {
            ExportFormat.DOT: "dot",
            ExportFormat.JSON: "json",
            ExportFormat.YAML: "yaml",
            ExportFormat.GNS3: "gns3",
            ExportFormat.CONTAINERLAB: "clab.yml",
            ExportFormat.NETBOX: "json",
            ExportFormat.D2: "d2",
            ExportFormat.MERMAID: "md",
            ExportFormat.CYJS: "cyjs.json",
            ExportFormat.CSV: "csv",
        }
        ext = ext_map.get(format, "txt")
        filename = f"topology_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"

        result = ExportResult(
            format=format,
            content=content,
            filename=filename,
            exported_at=datetime.now(),
            node_count=len(nodes),
            link_count=len(links),
            options=options,
            metadata={
                "generator": "ASI Topology Exporter",
                "version": "1.0.0"
            }
        )

        # Store in history
        self._exports.append(result)
        if len(self._exports) > self._max_history:
            self._exports = self._exports[-self._max_history:]

        logger.info(f"Exported topology to {format.value}: {len(nodes)} nodes, {len(links)} links")
        return result

    def _get_topology(self, options: ExportOptions) -> tuple:
        """Get topology data from the network."""
        try:
            from agentic.network import get_all_agents, get_topology
            agents = get_all_agents()
            topology = get_topology()

            # Convert agents to node format
            nodes = []
            for agent in agents:
                agent_dict = agent.to_dict() if hasattr(agent, 'to_dict') else agent
                agent_name = agent_dict.get("name", agent_dict.get("agent_id", "unknown"))

                # Apply filters
                if options.filter_agents and agent_name not in options.filter_agents:
                    continue
                if options.filter_protocols:
                    agent_protocols = agent_dict.get("protocols", [])
                    if not any(p.lower() in [fp.lower() for fp in options.filter_protocols] for p in agent_protocols):
                        continue

                node = {
                    "id": agent_name,
                    "name": agent_name,
                    "type": agent_dict.get("type", agent_dict.get("agent_type", "router")),
                    "loopback": agent_dict.get("loopback", agent_dict.get("loopback_ip")),
                    "protocols": agent_dict.get("protocols", []),
                    "status": agent_dict.get("status", "unknown"),
                }

                if options.include_interfaces:
                    node["interfaces"] = agent_dict.get("interfaces", [])

                if options.include_configs:
                    node["config"] = {
                        "ospf_area": agent_dict.get("ospf_area"),
                        "bgp_asn": agent_dict.get("bgp_asn"),
                        "hostname": agent_dict.get("hostname", agent_name)
                    }

                if options.include_metadata:
                    node["metadata"] = {
                        "vendor": agent_dict.get("vendor", "FRRouting"),
                        "version": agent_dict.get("version"),
                        "description": agent_dict.get("description")
                    }

                nodes.append(node)

            # Get links from topology
            links = []
            topo_links = topology.get("links", []) if topology else []
            node_ids = {n["id"] for n in nodes}

            for link in topo_links:
                source = link.get("source")
                target = link.get("target")

                # Only include links between included nodes
                if source in node_ids and target in node_ids:
                    links.append({
                        "source": source,
                        "target": target,
                        "source_interface": link.get("source_interface", "eth0"),
                        "target_interface": link.get("target_interface", "eth0"),
                        "type": link.get("type", "ethernet"),
                        "bandwidth": link.get("bandwidth"),
                        "label": link.get("label", f"{source}-{target}")
                    })

            return nodes, links

        except Exception as e:
            logger.warning(f"Could not fetch topology: {e}")
            return [], []

    def _export_dot(self, nodes: List[Dict], links: List[Dict], options: ExportOptions) -> str:
        """Export to Graphviz DOT format."""
        lines = [
            "digraph NetworkTopology {",
            "    // Graph settings",
            "    rankdir=TB;",
            "    splines=true;",
            "    overlap=false;",
            "    node [fontname=\"Helvetica\", fontsize=10];",
            "    edge [fontname=\"Helvetica\", fontsize=8];",
            ""
        ]

        # Layout settings
        if options.layout == "hierarchical":
            lines.append("    // Hierarchical layout")
        elif options.layout == "circular":
            lines.append("    layout=circo;")
        elif options.layout == "grid":
            lines.append("    layout=fdp;")

        lines.append("")
        lines.append("    // Nodes")

        # Node shapes based on type
        shape_map = {
            "router": "box",
            "switch": "diamond",
            "firewall": "hexagon",
            "server": "ellipse",
            "default": options.node_shape
        }

        # Color based on status
        color_map = {
            "running": "green",
            "stopped": "red",
            "unknown": "gray"
        }

        for node in nodes:
            shape = shape_map.get(node["type"], shape_map["default"])
            color = color_map.get(node.get("status", "unknown"), "gray")
            label = node["name"]

            if options.include_labels and node.get("loopback"):
                label = f"{node['name']}\\n{node['loopback']}"

            protocols = ", ".join(node.get("protocols", [])[:3])
            if protocols and options.include_labels:
                label += f"\\n[{protocols}]"

            lines.append(f'    "{node["id"]}" [shape={shape}, label="{label}", color={color}, style=filled, fillcolor="{color}30"];')

        lines.append("")
        lines.append("    // Links")

        for link in links:
            label = ""
            if options.include_labels:
                label = f'{link.get("source_interface", "")} - {link.get("target_interface", "")}'

            style = "solid" if options.link_style == "solid" else "dashed"
            lines.append(f'    "{link["source"]}" -> "{link["target"]}" [label="{label}", style={style}, dir=none];')

        lines.append("}")
        return "\n".join(lines)

    def _export_json(self, nodes: List[Dict], links: List[Dict], options: ExportOptions) -> str:
        """Export to JSON format."""
        data = {
            "topology": {
                "name": "ASI Network Topology",
                "exported_at": datetime.now().isoformat(),
                "nodes": nodes,
                "links": links
            },
            "metadata": {
                "generator": "ASI Topology Exporter",
                "version": "1.0.0",
                "node_count": len(nodes),
                "link_count": len(links)
            }
        }
        return json.dumps(data, indent=2)

    def _export_yaml(self, nodes: List[Dict], links: List[Dict], options: ExportOptions) -> str:
        """Export to YAML format."""
        data = {
            "topology": {
                "name": "ASI Network Topology",
                "exported_at": datetime.now().isoformat(),
                "nodes": nodes,
                "links": links
            },
            "metadata": {
                "generator": "ASI Topology Exporter",
                "version": "1.0.0"
            }
        }
        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def _export_gns3(self, nodes: List[Dict], links: List[Dict], options: ExportOptions) -> str:
        """Export to GNS3 project format."""
        # GNS3 project structure
        project = {
            "auto_close": True,
            "auto_open": False,
            "auto_start": False,
            "drawing_grid_size": 25,
            "grid_size": 75,
            "name": "ASI_Network",
            "project_id": "asi-export-" + datetime.now().strftime("%Y%m%d%H%M%S"),
            "revision": 9,
            "scene_height": 1000,
            "scene_width": 2000,
            "show_grid": False,
            "show_interface_labels": options.include_labels,
            "show_layers": False,
            "snap_to_grid": False,
            "supplier": None,
            "topology": {
                "computes": [],
                "drawings": [],
                "links": [],
                "nodes": []
            },
            "type": "topology",
            "variables": None,
            "version": "2.2.0",
            "zoom": 100
        }

        # Add nodes
        x_offset = 100
        y_offset = 100
        for i, node in enumerate(nodes):
            gns3_node = {
                "compute_id": "local",
                "console": None,
                "console_auto_start": False,
                "console_type": "telnet",
                "custom_adapters": [],
                "first_port_name": None,
                "height": 59,
                "label": {
                    "rotation": 0,
                    "style": "font-family: TypeWriter;font-size: 10.0;font-weight: bold;fill: #000000;fill-opacity: 1.0;",
                    "text": node["name"],
                    "x": 3,
                    "y": -25
                },
                "name": node["name"],
                "node_id": f"node-{i}",
                "node_type": "vpcs" if node["type"] == "server" else "dynamips",
                "port_name_format": "Ethernet{0}",
                "port_segment_size": 0,
                "properties": {},
                "symbol": f":/symbols/router.svg",
                "width": 66,
                "x": x_offset + (i % 5) * 200,
                "y": y_offset + (i // 5) * 150,
                "z": 1
            }
            project["topology"]["nodes"].append(gns3_node)

        # Add links
        for i, link in enumerate(links):
            source_idx = next((j for j, n in enumerate(nodes) if n["id"] == link["source"]), None)
            target_idx = next((j for j, n in enumerate(nodes) if n["id"] == link["target"]), None)

            if source_idx is not None and target_idx is not None:
                gns3_link = {
                    "filters": {},
                    "link_id": f"link-{i}",
                    "nodes": [
                        {"adapter_number": 0, "label": {"rotation": 0, "style": "", "text": link.get("source_interface", "e0"), "x": 0, "y": 0}, "node_id": f"node-{source_idx}", "port_number": 0},
                        {"adapter_number": 0, "label": {"rotation": 0, "style": "", "text": link.get("target_interface", "e0"), "x": 0, "y": 0}, "node_id": f"node-{target_idx}", "port_number": 0}
                    ],
                    "suspend": False
                }
                project["topology"]["links"].append(gns3_link)

        return json.dumps(project, indent=2)

    def _export_containerlab(self, nodes: List[Dict], links: List[Dict], options: ExportOptions) -> str:
        """Export to Containerlab topology format."""
        topo = {
            "name": "asi-network",
            "topology": {
                "kinds": {
                    "linux": {
                        "image": "frrouting/frr:latest"
                    }
                },
                "nodes": {},
                "links": []
            }
        }

        # Add nodes
        for node in nodes:
            node_config = {
                "kind": "linux",
            }

            # Add management IP if available
            if node.get("loopback"):
                node_config["mgmt-ipv4"] = node["loopback"]

            # Add environment variables for protocols
            env = {}
            if "ospf" in [p.lower() for p in node.get("protocols", [])]:
                env["OSPF_ENABLED"] = "true"
            if "bgp" in [p.lower() for p in node.get("protocols", [])]:
                env["BGP_ENABLED"] = "true"
            if env:
                node_config["env"] = env

            topo["topology"]["nodes"][node["name"]] = node_config

        # Add links
        for link in links:
            link_def = [
                f"{link['source']}:{link.get('source_interface', 'eth1')}",
                f"{link['target']}:{link.get('target_interface', 'eth1')}"
            ]
            topo["topology"]["links"].append(link_def)

        return yaml.dump(topo, default_flow_style=False, sort_keys=False)

    def _export_netbox(self, nodes: List[Dict], links: List[Dict], options: ExportOptions) -> str:
        """Export to NetBox import format."""
        netbox_data = {
            "devices": [],
            "interfaces": [],
            "cables": []
        }

        for node in nodes:
            device = {
                "name": node["name"],
                "device_type": node["type"],
                "site": "ASI-Network",
                "status": "active" if node.get("status") == "running" else "offline",
                "custom_fields": {
                    "protocols": ", ".join(node.get("protocols", [])),
                    "loopback": node.get("loopback")
                }
            }
            netbox_data["devices"].append(device)

            # Add interfaces
            for iface in node.get("interfaces", []):
                if isinstance(iface, dict):
                    interface = {
                        "device": node["name"],
                        "name": iface.get("name", "eth0"),
                        "type": "1000base-t",
                        "enabled": iface.get("state") == "up"
                    }
                    netbox_data["interfaces"].append(interface)

        # Add cables (links)
        for link in links:
            cable = {
                "termination_a_type": "dcim.interface",
                "termination_a_device": link["source"],
                "termination_a_name": link.get("source_interface", "eth0"),
                "termination_b_type": "dcim.interface",
                "termination_b_device": link["target"],
                "termination_b_name": link.get("target_interface", "eth0"),
                "status": "connected"
            }
            netbox_data["cables"].append(cable)

        return json.dumps(netbox_data, indent=2)

    def _export_d2(self, nodes: List[Dict], links: List[Dict], options: ExportOptions) -> str:
        """Export to D2 diagram format."""
        lines = [
            "# ASI Network Topology",
            "# Generated by ASI Topology Exporter",
            "",
            "direction: down",
            ""
        ]

        # Define styles
        lines.append("# Styles")
        lines.append("classes: {")
        lines.append("  router: {")
        lines.append("    shape: rectangle")
        lines.append("    style.fill: \"#e1f5fe\"")
        lines.append("  }")
        lines.append("  switch: {")
        lines.append("    shape: diamond")
        lines.append("    style.fill: \"#e8f5e9\"")
        lines.append("  }")
        lines.append("}")
        lines.append("")

        # Add nodes
        lines.append("# Nodes")
        for node in nodes:
            label = node["name"]
            if options.include_labels and node.get("loopback"):
                label = f'{node["name"]}\\n{node["loopback"]}'

            node_class = node["type"] if node["type"] in ["router", "switch"] else "router"
            lines.append(f'{node["id"]}: "{label}" {{ class: {node_class} }}')

        lines.append("")
        lines.append("# Links")

        # Add links
        for link in links:
            label = ""
            if options.include_labels:
                label = f': {link.get("source_interface", "")} <-> {link.get("target_interface", "")}'
            lines.append(f'{link["source"]} -- {link["target"]}{label}')

        return "\n".join(lines)

    def _export_mermaid(self, nodes: List[Dict], links: List[Dict], options: ExportOptions) -> str:
        """Export to Mermaid diagram format."""
        lines = [
            "```mermaid",
            "graph TD"
        ]

        # Define node styles
        lines.append("")
        lines.append("    %% Nodes")

        for node in nodes:
            label = node["name"]
            if options.include_labels and node.get("loopback"):
                label = f'{node["name"]}<br/>{node["loopback"]}'

            # Different shapes based on type
            if node["type"] == "router":
                lines.append(f'    {node["id"]}["{label}"]')
            elif node["type"] == "switch":
                lines.append(f'    {node["id"]}{{"{label}"}}')
            else:
                lines.append(f'    {node["id"]}("{label}")')

        lines.append("")
        lines.append("    %% Links")

        for link in links:
            label = ""
            if options.include_labels:
                label = f'|{link.get("source_interface", "")}-{link.get("target_interface", "")}|'
            lines.append(f'    {link["source"]} <--{label}--> {link["target"]}')

        lines.append("")
        lines.append("    %% Styles")
        lines.append("    classDef router fill:#e1f5fe,stroke:#0288d1")
        lines.append("    classDef switch fill:#e8f5e9,stroke:#388e3c")

        # Apply styles
        routers = [n["id"] for n in nodes if n["type"] == "router"]
        switches = [n["id"] for n in nodes if n["type"] == "switch"]

        if routers:
            lines.append(f'    class {",".join(routers)} router')
        if switches:
            lines.append(f'    class {",".join(switches)} switch')

        lines.append("```")
        return "\n".join(lines)

    def _export_cyjs(self, nodes: List[Dict], links: List[Dict], options: ExportOptions) -> str:
        """Export to Cytoscape.js JSON format."""
        elements = {
            "nodes": [],
            "edges": []
        }

        for node in nodes:
            cy_node = {
                "data": {
                    "id": node["id"],
                    "label": node["name"],
                    "type": node["type"],
                    "loopback": node.get("loopback"),
                    "protocols": node.get("protocols", []),
                    "status": node.get("status")
                }
            }
            elements["nodes"].append(cy_node)

        for i, link in enumerate(links):
            cy_edge = {
                "data": {
                    "id": f"edge-{i}",
                    "source": link["source"],
                    "target": link["target"],
                    "source_interface": link.get("source_interface"),
                    "target_interface": link.get("target_interface"),
                    "label": link.get("label")
                }
            }
            elements["edges"].append(cy_edge)

        return json.dumps(elements, indent=2)

    def _export_csv(self, nodes: List[Dict], links: List[Dict], options: ExportOptions) -> str:
        """Export to CSV format (nodes and links sections)."""
        lines = [
            "# NODES",
            "id,name,type,loopback,protocols,status"
        ]

        for node in nodes:
            protocols = ";".join(node.get("protocols", []))
            lines.append(f'{node["id"]},{node["name"]},{node["type"]},{node.get("loopback", "")},{protocols},{node.get("status", "")}')

        lines.append("")
        lines.append("# LINKS")
        lines.append("source,target,source_interface,target_interface,type")

        for link in links:
            lines.append(f'{link["source"]},{link["target"]},{link.get("source_interface", "")},{link.get("target_interface", "")},{link.get("type", "")}')

        return "\n".join(lines)

    def import_topology(self, content: str, format: ExportFormat) -> Dict[str, Any]:
        """Import topology from a string."""
        importers = {
            ExportFormat.JSON: self._import_json,
            ExportFormat.YAML: self._import_yaml,
            ExportFormat.CSV: self._import_csv,
        }

        importer = importers.get(format)
        if not importer:
            raise ValueError(f"Import not supported for format: {format}")

        return importer(content)

    def _import_json(self, content: str) -> Dict[str, Any]:
        """Import from JSON format."""
        data = json.loads(content)
        return data.get("topology", data)

    def _import_yaml(self, content: str) -> Dict[str, Any]:
        """Import from YAML format."""
        data = yaml.safe_load(content)
        return data.get("topology", data)

    def _import_csv(self, content: str) -> Dict[str, Any]:
        """Import from CSV format."""
        lines = content.strip().split("\n")
        nodes = []
        links = []

        section = None
        headers = []

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                if "NODES" in line:
                    section = "nodes"
                elif "LINKS" in line:
                    section = "links"
                continue

            if section == "nodes":
                if not headers:
                    headers = line.split(",")
                else:
                    values = line.split(",")
                    node = dict(zip(headers, values))
                    if node.get("protocols"):
                        node["protocols"] = node["protocols"].split(";")
                    nodes.append(node)
            elif section == "links":
                if not headers or "source" not in headers:
                    headers = line.split(",")
                else:
                    values = line.split(",")
                    link = dict(zip(headers, values))
                    links.append(link)

        return {"nodes": nodes, "links": links}

    def get_export_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent export history."""
        exports = self._exports[-limit:]
        # Return without content to reduce size
        return [{
            "format": e.format.value,
            "filename": e.filename,
            "exported_at": e.exported_at.isoformat(),
            "node_count": e.node_count,
            "link_count": e.link_count
        } for e in reversed(exports)]

    def get_statistics(self) -> Dict[str, Any]:
        """Get exporter statistics."""
        format_counts = {}
        for e in self._exports:
            fmt = e.format.value
            format_counts[fmt] = format_counts.get(fmt, 0) + 1

        return {
            "total_exports": len(self._exports),
            "by_format": format_counts,
            "supported_formats": [f.value for f in ExportFormat],
            "import_formats": ["json", "yaml", "csv"]
        }
