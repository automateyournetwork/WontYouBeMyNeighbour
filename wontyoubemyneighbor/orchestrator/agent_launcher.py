"""
Agent Launcher for Multi-Agent Orchestration

Handles launching individual agents as Docker containers:
- Container configuration from TOON agent specs
- Environment variable setup
- Command generation
- Health monitoring
"""

import asyncio
import ipaddress
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

from toon.models import TOONAgent, TOONProtocolConfig, TOONMCPConfig
from .docker_manager import DockerManager, ContainerInfo, DockerNotAvailableError


@dataclass
class AgentContainer:
    """Agent container status and metadata"""
    agent_id: str
    container_name: str
    container_id: Optional[str] = None
    status: str = "pending"  # pending, starting, running, stopped, error
    network: Optional[str] = None
    ip_address: Optional[str] = None
    webui_port: Optional[int] = None
    api_port: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class AgentLauncher:
    """
    Launches and manages individual agent containers
    """

    DEFAULT_IMAGE = "wontyoubemyneighbor:latest"
    BASE_WEBUI_PORT = 8888
    BASE_API_PORT = 8080

    def __init__(self, docker_manager: Optional[DockerManager] = None):
        """
        Initialize agent launcher

        Args:
            docker_manager: Docker manager instance (creates new if None)
        """
        self.docker = docker_manager or DockerManager()
        self.logger = logging.getLogger("AgentLauncher")
        self._agents: Dict[str, AgentContainer] = {}
        self._port_counter = 0

    def _get_next_ports(self) -> tuple:
        """Get next available port pair for webui and api"""
        webui_port = self.BASE_WEBUI_PORT + self._port_counter
        api_port = self.BASE_API_PORT + self._port_counter
        self._port_counter += 1
        return webui_port, api_port

    def _generate_container_name(self, network_name: str, agent_name: str) -> str:
        """Generate container name from network and agent name"""
        # Clean names for Docker (allow alphanumeric, dash, underscore)
        clean_network = re.sub(r'[^a-zA-Z0-9_-]', '-', network_name).lower().strip('-')
        clean_agent = re.sub(r'[^a-zA-Z0-9_-]', '-', agent_name).lower().strip('-')
        return f"{clean_network}-{clean_agent}"

    def _build_command(
        self,
        agent: TOONAgent,
        ip_mapping: Optional[Dict[str, str]] = None
    ) -> List[str]:
        """
        Build command line arguments for agent container

        Args:
            agent: TOON agent configuration
            ip_mapping: Mapping of agent IDs/names/router-IDs to container IPs

        Returns:
            List of command arguments
        """
        cmd = ["python3", "wontyoubemyneighbor.py"]

        # Router ID (required)
        cmd.extend(["--router-id", agent.r])

        # Process each protocol
        for proto in agent.protos:
            if proto.p == "ospf":
                cmd.extend(["--area", proto.a or "0.0.0.0"])
                # Interface will be eth0 in container
                cmd.extend(["--interface", "eth0"])
                if proto.opts.get("network_type"):
                    cmd.extend(["--network-type", proto.opts["network_type"]])
                if proto.opts.get("unicast_peer"):
                    cmd.extend(["--unicast-peer", proto.opts["unicast_peer"]])

            elif proto.p == "ospfv3":
                cmd.extend(["--ospfv3-interface", "eth0"])
                cmd.extend(["--ospfv3-area", proto.a or "0.0.0.0"])

            elif proto.p in ["ibgp", "ebgp"]:
                cmd.extend(["--bgp-local-as", str(proto.asn or 65001)])

                # Add peers
                for peer in proto.peers:
                    peer_ip = peer["ip"]
                    # Resolve peer IP from mapping if possible
                    if ip_mapping:
                        resolved_ip = self._resolve_peer_ip(peer_ip, ip_mapping)
                        if resolved_ip:
                            peer_ip = resolved_ip

                    cmd.extend(["--bgp-peer", peer_ip])
                    cmd.extend(["--bgp-peer-as", str(peer.get("asn", proto.asn))])
                    if peer.get("passive"):
                        cmd.extend(["--bgp-passive", peer_ip])

                # Add networks to advertise
                for net in proto.nets:
                    cmd.extend(["--bgp-network", net])

            elif proto.p == "isis":
                # IS-IS configuration
                if proto.opts.get("system_id"):
                    cmd.extend(["--isis-system-id", proto.opts["system_id"]])
                if proto.opts.get("area"):
                    cmd.extend(["--isis-area", proto.opts["area"]])
                elif proto.a:
                    cmd.extend(["--isis-area", proto.a])
                if proto.opts.get("level"):
                    cmd.extend(["--isis-level", str(proto.opts["level"])])
                if proto.opts.get("metric"):
                    cmd.extend(["--isis-metric", str(proto.opts["metric"])])
                cmd.extend(["--isis-interface", "eth0"])
                # Add networks to advertise
                for net in proto.nets:
                    cmd.extend(["--isis-network", net])

            elif proto.p in ["mpls", "ldp"]:
                # MPLS/LDP configuration
                if proto.opts.get("router_id") or agent.r:
                    cmd.extend(["--mpls-router-id", proto.opts.get("router_id", agent.r)])
                cmd.extend(["--ldp-interface", "eth0"])
                # Add LDP neighbors
                for neighbor in proto.opts.get("neighbors", []):
                    neighbor_ip = neighbor
                    if ip_mapping:
                        resolved_ip = self._resolve_peer_ip(neighbor_ip, ip_mapping)
                        if resolved_ip:
                            neighbor_ip = resolved_ip
                    cmd.extend(["--ldp-neighbor", neighbor_ip])
                # Label range
                if proto.opts.get("label_range_start"):
                    cmd.extend(["--mpls-label-range-start", str(proto.opts["label_range_start"])])
                if proto.opts.get("label_range_end"):
                    cmd.extend(["--mpls-label-range-end", str(proto.opts["label_range_end"])])

            elif proto.p == "vxlan":
                # VXLAN configuration
                if proto.opts.get("vtep_ip"):
                    cmd.extend(["--vtep-ip", proto.opts["vtep_ip"]])
                for vni in proto.opts.get("vnis", []):
                    cmd.extend(["--vxlan-vni", str(vni)])
                for remote_vtep in proto.opts.get("remote_vteps", []):
                    vtep_ip = remote_vtep
                    if ip_mapping:
                        resolved_ip = self._resolve_peer_ip(vtep_ip, ip_mapping)
                        if resolved_ip:
                            vtep_ip = resolved_ip
                    cmd.extend(["--vxlan-remote-vtep", vtep_ip])
                if proto.opts.get("port"):
                    cmd.extend(["--vxlan-port", str(proto.opts["port"])])

            elif proto.p == "evpn":
                # EVPN configuration
                if proto.opts.get("rd"):
                    cmd.extend(["--evpn-rd", proto.opts["rd"]])
                for rt in proto.opts.get("rts", []):
                    cmd.extend(["--evpn-rt", rt])
                # EVPN typically needs VXLAN VNIs too
                for vni in proto.opts.get("vnis", []):
                    cmd.extend(["--vxlan-vni", str(vni)])

            elif proto.p == "dhcp":
                # DHCP server configuration
                cmd.append("--dhcp-server")
                if proto.opts.get("pool_start") and proto.opts.get("pool_end"):
                    pool_name = proto.opts.get("pool_name", "default")
                    subnet = proto.opts.get("subnet", "10.0.0.0/24")
                    cmd.extend(["--dhcp-pool", f"{pool_name},{proto.opts['pool_start']},{proto.opts['pool_end']},{subnet}"])
                if proto.opts.get("gateway"):
                    cmd.extend(["--dhcp-gateway", proto.opts["gateway"]])
                for dns in proto.opts.get("dns_servers", []):
                    cmd.extend(["--dhcp-dns", dns])
                if proto.opts.get("lease_time"):
                    cmd.extend(["--dhcp-lease-time", str(proto.opts["lease_time"])])

            elif proto.p == "dns":
                # DNS server configuration
                cmd.append("--dns-server")
                if proto.opts.get("zone"):
                    cmd.extend(["--dns-zone", proto.opts["zone"]])
                for record in proto.opts.get("records", []):
                    # Format: name,type,value
                    cmd.extend(["--dns-record", record])
                for forwarder in proto.opts.get("forwarders", []):
                    cmd.extend(["--dns-forwarder", forwarder])
                if proto.opts.get("port"):
                    cmd.extend(["--dns-port", str(proto.opts["port"])])

        # Enable web UI
        cmd.extend(["--webui"])

        return cmd

    def _resolve_peer_ip(
        self,
        configured_ip: str,
        ip_mapping: Dict[str, str]
    ) -> Optional[str]:
        """
        Resolve a configured peer IP to actual container IP

        Resolves IPs that are in the same Docker network subnet as our containers.
        External peers (truly different subnets like 8.8.8.8) are not resolved.

        Resolution strategy:
        1. Direct lookup by exact IP match (router-id or name in mapping)
        2. Match by last octet if configured IP appears to be in private ranges
           (172.x, 192.168.x, 10.x) that might be simulated multi-interface configs

        Args:
            configured_ip: The IP from configuration
            ip_mapping: Dict mapping agent_id, agent_name, router_id to container IPs

        Returns:
            Resolved container IP or None if no match
        """
        # Direct lookup by exact IP match
        if configured_ip in ip_mapping:
            return ip_mapping[configured_ip]

        # Check if configured_ip is an external/public IP (not private)
        try:
            ip_obj = ipaddress.ip_address(configured_ip)
            if not ip_obj.is_private:
                # Public IP - this is truly external, don't resolve
                self.logger.debug(f"Not resolving {configured_ip} - public IP (external peer)")
                return None
        except ValueError:
            pass

        # For private IPs, try to match by router-ID last octet
        # This handles cases where config has 172.20.1.99 but we need to find
        # the container IP for router-id 10.255.255.99 (matching last octet .99)
        try:
            configured_last_octet = configured_ip.split('.')[-1]
            for key, container_ip in ip_mapping.items():
                # Check if key is an IP-like router-id with matching last octet
                if '.' in key and key.count('.') == 3:
                    key_last_octet = key.split('.')[-1]
                    if key_last_octet == configured_last_octet:
                        self.logger.info(
                            f"Resolved BGP peer {configured_ip} -> {container_ip} "
                            f"(matched via router-id {key} last octet .{configured_last_octet})"
                        )
                        return container_ip
        except Exception:
            pass

        self.logger.debug(f"Could not resolve peer IP {configured_ip}")
        return None

    def _build_environment(self, agent: TOONAgent, api_keys: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Build environment variables for agent container

        Args:
            agent: TOON agent configuration
            api_keys: LLM API keys

        Returns:
            Dict of environment variables
        """
        import json

        env = {
            "RUBBERBAND_AGENT_ID": agent.id,
            "RUBBERBAND_AGENT_NAME": agent.n,
            "RUBBERBAND_ROUTER_ID": agent.r,
            # Pass full agent config as JSON for interface/protocol display
            "RUBBERBAND_AGENT_CONFIG": json.dumps(agent.to_dict())
        }

        # Add API keys if provided
        if api_keys:
            if api_keys.get("openai"):
                env["OPENAI_API_KEY"] = api_keys["openai"]
            if api_keys.get("anthropic") or api_keys.get("claude"):
                env["ANTHROPIC_API_KEY"] = api_keys.get("anthropic") or api_keys.get("claude")
            if api_keys.get("google") or api_keys.get("gemini"):
                env["GOOGLE_API_KEY"] = api_keys.get("google") or api_keys.get("gemini")

        # Add MCP configurations
        for mcp in agent.mcps:
            if mcp.e:  # Only if enabled
                env[f"MCP_{mcp.t.upper()}_ENABLED"] = "true"
                env[f"MCP_{mcp.t.upper()}_URL"] = mcp.url
                for key, value in mcp.c.items():
                    env[f"MCP_{mcp.t.upper()}_{key.upper()}"] = str(value)

        return env

    async def launch(
        self,
        agent: TOONAgent,
        network_name: str,
        image: Optional[str] = None,
        api_keys: Optional[Dict[str, str]] = None,
        expose_ports: bool = True,
        ip_mapping: Optional[Dict[str, str]] = None,
        assigned_ip: Optional[str] = None
    ) -> AgentContainer:
        """
        Launch an agent as a Docker container

        Args:
            agent: TOON agent configuration
            network_name: Docker network to connect to
            image: Docker image (default: wontyoubemyneighbor:latest)
            api_keys: LLM API keys
            expose_ports: Expose WebUI and API ports
            ip_mapping: Mapping of agent IDs/router-IDs to container IPs for BGP peer resolution
            assigned_ip: Specific IP to assign to this container

        Returns:
            AgentContainer with status
        """
        # Use agent name (agent.n) for human-readable container names
        container_name = self._generate_container_name(network_name, agent.n)

        # Create agent container tracking
        agent_container = AgentContainer(
            agent_id=agent.id,
            container_name=container_name,
            network=network_name,
            status="pending",
            config=agent.to_dict()
        )
        self._agents[agent.id] = agent_container

        if not self.docker.available:
            agent_container.status = "error"
            agent_container.error_message = self.docker.error_message
            return agent_container

        try:
            agent_container.status = "starting"

            # Get ports if exposing
            ports = None
            if expose_ports:
                webui_port, api_port = self._get_next_ports()
                ports = {8888: webui_port, 8080: api_port}
                agent_container.webui_port = webui_port
                agent_container.api_port = api_port

            # Build command and environment
            command = self._build_command(agent, ip_mapping)
            environment = self._build_environment(agent, api_keys)

            # Add container name to environment for dashboard display
            environment["CONTAINER_NAME"] = container_name

            # Create container
            container_info = self.docker.create_container(
                name=container_name,
                image=image or self.DEFAULT_IMAGE,
                network=network_name,
                command=command,
                environment=environment,
                ports=ports,
                labels={
                    "rubberband.agent_id": agent.id,
                    "rubberband.agent_name": agent.n,
                    "rubberband.network": network_name
                },
                privileged=True,  # Required for raw sockets
                cap_add=["NET_ADMIN", "NET_RAW"],
                ip_address=assigned_ip
            )

            agent_container.container_id = container_info.id
            agent_container.ip_address = container_info.ip_address
            agent_container.status = "running"
            agent_container.started_at = datetime.now().isoformat()

            self.logger.info(
                f"Launched agent {agent.id} as {container_name} "
                f"(IP: {container_info.ip_address})"
            )

        except Exception as e:
            agent_container.status = "error"
            agent_container.error_message = str(e)
            self.logger.error(f"Failed to launch agent {agent.id}: {e}")

        return agent_container

    async def stop(self, agent_id: str, remove: bool = False) -> bool:
        """
        Stop an agent container

        Args:
            agent_id: Agent identifier
            remove: Remove container after stopping

        Returns:
            True if stopped successfully
        """
        if agent_id not in self._agents:
            return False

        agent_container = self._agents[agent_id]

        try:
            if self.docker.stop_container(agent_container.container_name):
                agent_container.status = "stopped"

                if remove:
                    self.docker.remove_container(agent_container.container_name)
                    del self._agents[agent_id]

                return True
        except Exception as e:
            self.logger.error(f"Failed to stop agent {agent_id}: {e}")

        return False

    def get_status(self, agent_id: str) -> Optional[AgentContainer]:
        """
        Get agent container status

        Args:
            agent_id: Agent identifier

        Returns:
            AgentContainer or None
        """
        if agent_id not in self._agents:
            return None

        agent_container = self._agents[agent_id]

        # Refresh status from Docker
        container_info = self.docker.get_container(agent_container.container_name)
        if container_info:
            agent_container.status = container_info.status
            agent_container.ip_address = container_info.ip_address
        else:
            agent_container.status = "not_found"

        return agent_container

    def get_logs(self, agent_id: str, tail: int = 100) -> Optional[str]:
        """
        Get agent container logs

        Args:
            agent_id: Agent identifier
            tail: Number of lines

        Returns:
            Log string or None
        """
        if agent_id not in self._agents:
            return None

        agent_container = self._agents[agent_id]
        return self.docker.get_container_logs(agent_container.container_name, tail)

    def list_agents(self) -> List[AgentContainer]:
        """
        List all managed agent containers

        Returns:
            List of AgentContainer
        """
        # Refresh status for all agents
        for agent_id in list(self._agents.keys()):
            self.get_status(agent_id)

        return list(self._agents.values())


# Module-level convenience functions

_default_launcher: Optional[AgentLauncher] = None


def get_launcher() -> AgentLauncher:
    """Get or create default agent launcher"""
    global _default_launcher
    if _default_launcher is None:
        _default_launcher = AgentLauncher()
    return _default_launcher


async def launch_agent(
    agent: TOONAgent,
    network_name: str,
    image: Optional[str] = None,
    api_keys: Optional[Dict[str, str]] = None,
    ip_mapping: Optional[Dict[str, str]] = None,
    assigned_ip: Optional[str] = None
) -> AgentContainer:
    """Launch agent using default launcher"""
    return await get_launcher().launch(
        agent, network_name, image, api_keys, ip_mapping=ip_mapping, assigned_ip=assigned_ip
    )


async def stop_agent(agent_id: str, remove: bool = False) -> bool:
    """Stop agent using default launcher"""
    return await get_launcher().stop(agent_id, remove)


def get_agent_status(agent_id: str) -> Optional[AgentContainer]:
    """Get agent status using default launcher"""
    return get_launcher().get_status(agent_id)


def get_agent_logs(agent_id: str, tail: int = 100) -> Optional[str]:
    """Get agent logs using default launcher"""
    return get_launcher().get_logs(agent_id, tail)
