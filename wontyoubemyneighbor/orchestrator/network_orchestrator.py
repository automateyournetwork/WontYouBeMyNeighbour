"""
Network Orchestrator for Multi-Agent Networks

Manages complete network deployments:
- Docker network creation
- Multi-agent launch coordination
- Network-wide status monitoring
- Graceful shutdown and cleanup
"""

import asyncio
import ipaddress
import logging
import re
import traceback
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from toon.models import TOONNetwork, TOONAgent
from persistence.manager import PersistenceManager, capture_agent_state
from .docker_manager import DockerManager, NetworkInfo, DockerNotAvailableError
from .agent_launcher import AgentLauncher, AgentContainer


@dataclass
class NetworkDeployment:
    """Network deployment status"""
    network_id: str
    network_name: str
    status: str = "pending"  # pending, deploying, running, stopping, stopped, error
    docker_network: Optional[str] = None
    subnet: Optional[str] = None
    subnet6: Optional[str] = None  # Docker IPv6 subnet if dual-stack enabled
    agents: Dict[str, AgentContainer] = field(default_factory=dict)
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None


class NetworkOrchestrator:
    """
    Orchestrates multi-agent network deployments
    """

    def __init__(
        self,
        docker_manager: Optional[DockerManager] = None,
        persistence_manager: Optional[PersistenceManager] = None
    ):
        """
        Initialize network orchestrator

        Args:
            docker_manager: Docker manager instance
            persistence_manager: Persistence manager for state storage
        """
        self.docker = docker_manager or DockerManager()
        self.persistence = persistence_manager or PersistenceManager()
        self.launcher = AgentLauncher(self.docker)
        self.logger = logging.getLogger("NetworkOrchestrator")
        self._deployments: Dict[str, NetworkDeployment] = {}

    def _calculate_agent_ips(
        self,
        agents: List[TOONAgent],
        subnet: Optional[str]
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        """
        Pre-calculate IP addresses for agents from the subnet

        Args:
            agents: List of agents to assign IPs to
            subnet: Docker network subnet (e.g., "172.20.0.0/24")

        Returns:
            Tuple of (agent_id -> IP mapping, router_id -> IP mapping)
        """
        agent_to_ip = {}
        router_id_to_ip = {}

        if not subnet:
            return agent_to_ip, router_id_to_ip

        try:
            network = ipaddress.ip_network(subnet, strict=False)
            # Get usable hosts (skip network address and broadcast)
            hosts = list(network.hosts())

            # Skip the first IP (usually the gateway)
            available_hosts = hosts[1:] if len(hosts) > 1 else hosts

            for i, agent in enumerate(agents):
                if i < len(available_hosts):
                    ip = str(available_hosts[i])
                    agent_to_ip[agent.id] = ip
                    agent_to_ip[agent.n] = ip  # Also map by name
                    router_id_to_ip[agent.r] = ip  # Map by router-id

                    self.logger.info(
                        f"Pre-assigned IP {ip} to agent {agent.id} "
                        f"(name={agent.n}, router-id={agent.r})"
                    )

        except Exception as e:
            self.logger.warning(f"Failed to pre-calculate IPs from subnet {subnet}: {e}")

        return agent_to_ip, router_id_to_ip

    async def launch(
        self,
        network: TOONNetwork,
        image: Optional[str] = None,
        api_keys: Optional[Dict[str, str]] = None,
        parallel: bool = True,
        network_foundation: Optional[Dict[str, Any]] = None
    ) -> NetworkDeployment:
        """
        Launch a complete network deployment

        Args:
            network: TOON network configuration
            image: Docker image for agents
            api_keys: LLM API keys
            parallel: Launch agents in parallel
            network_foundation: Network foundation settings (3-layer architecture)
                - underlay_protocol: 'ipv4', 'ipv6', or 'dual'
                - overlay: ASI agent mesh settings (IPv6)
                - docker_ipv6: Docker IPv6 settings

        Returns:
            NetworkDeployment status
        """
        deployment = NetworkDeployment(
            network_id=network.id,
            network_name=network.n,
            status="pending"
        )
        self._deployments[network.id] = deployment

        if not self.docker.available:
            deployment.status = "error"
            deployment.error_message = self.docker.error_message
            return deployment

        try:
            deployment.status = "deploying"
            deployment.started_at = datetime.now().isoformat()

            # Step 1: Create Docker network (Layer 1 of 3-layer architecture)
            self.logger.info(f"Creating Docker network for {network.n}...")
            docker_net_name = network.docker.n if network.docker else network.id
            subnet = network.docker.subnet if network.docker else None
            gateway = network.docker.gw if network.docker else None

            # Extract IPv6 dual-stack settings from network foundation
            subnet6 = None
            gateway6 = None
            enable_ipv6 = False

            if network_foundation:
                docker_ipv6 = network_foundation.get("docker_ipv6", {})
                if docker_ipv6.get("enabled", False):
                    enable_ipv6 = True
                    subnet6 = docker_ipv6.get("subnet")
                    gateway6 = docker_ipv6.get("gateway")
                    self.logger.info(f"Docker IPv6 dual-stack enabled: {subnet6}")

            network_info = self.docker.create_network(
                name=docker_net_name,
                subnet=subnet,
                gateway=gateway,
                subnet6=subnet6,
                gateway6=gateway6,
                enable_ipv6=enable_ipv6,
                labels={
                    "asi.network_id": network.id,
                    "asi.network_name": network.n,
                    "asi.ipv6_enabled": str(enable_ipv6).lower()
                }
            )

            deployment.docker_network = docker_net_name
            deployment.subnet = network_info.subnet
            deployment.subnet6 = subnet6  # Store IPv6 subnet if dual-stack enabled

            # Step 2: Pre-calculate agent IPs for BGP peer resolution
            agent_to_ip, router_id_to_ip = self._calculate_agent_ips(
                network.agents,
                network_info.subnet
            )
            # Merge both mappings for comprehensive lookup
            ip_mapping = {**agent_to_ip, **router_id_to_ip}

            self.logger.info(f"IP mapping for BGP peer resolution: {ip_mapping}")

            # Step 3: Launch agents
            self.logger.info(f"Launching {len(network.agents)} agents...")
            for i, agent in enumerate(network.agents):
                self.logger.info(f"  Agent {i+1}/{len(network.agents)}: {agent.id} ({agent.n})")

            if parallel:
                # Launch all agents in parallel
                tasks = [
                    self.launcher.launch(
                        agent=agent,
                        network_name=docker_net_name,
                        image=image,
                        api_keys=api_keys,
                        ip_mapping=ip_mapping,
                        assigned_ip=agent_to_ip.get(agent.id),
                        agent_index=i + 1,  # 1-based index for IPv6 overlay addressing
                        network_foundation=network_foundation
                    )
                    for i, agent in enumerate(network.agents)
                ]
                agent_results = await asyncio.gather(*tasks, return_exceptions=True)

                self.logger.info(f"Processing {len(agent_results)} launch results...")
                for i, (agent, result) in enumerate(zip(network.agents, agent_results)):
                    if isinstance(result, Exception):
                        # Log full traceback for debugging, but store clean message
                        self.logger.error(
                            f"Failed to launch agent {agent.n}: {result}\n"
                            f"{''.join(traceback.format_exception(type(result), result, result.__traceback__))}"
                        )
                        # Use agent name for human-readable container names
                        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '-', agent.n).lower().strip('-')
                        deployment.agents[agent.id] = AgentContainer(
                            agent_id=agent.id,
                            container_name=f"{docker_net_name}-{clean_name}",
                            status="error",
                            error_message=str(result)
                        )
                    else:
                        deployment.agents[agent.id] = result
                        self.logger.info(f"  Agent {i+1}: {agent.id} -> {result.status} (port: {result.webui_port})")
            else:
                # Launch agents sequentially
                for i, agent in enumerate(network.agents):
                    try:
                        result = await self.launcher.launch(
                            agent=agent,
                            network_name=docker_net_name,
                            image=image,
                            api_keys=api_keys,
                            ip_mapping=ip_mapping,
                            assigned_ip=agent_to_ip.get(agent.id),
                            agent_index=i + 1,  # 1-based index for IPv6 overlay addressing
                            network_foundation=network_foundation
                        )
                        deployment.agents[agent.id] = result
                    except Exception as e:
                        # Use agent name for human-readable container names
                        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '-', agent.n).lower().strip('-')
                        deployment.agents[agent.id] = AgentContainer(
                            agent_id=agent.id,
                            container_name=f"{docker_net_name}-{clean_name}",
                            status="error",
                            error_message=str(e)
                        )

            # Check if all agents launched successfully
            running_count = sum(
                1 for a in deployment.agents.values()
                if a.status == "running"
            )

            if running_count == len(network.agents):
                deployment.status = "running"
                self.logger.info(f"Network {network.n} fully deployed ({running_count} agents)")
            elif running_count > 0:
                deployment.status = "running"  # Partial success
                self.logger.warning(
                    f"Network {network.n} partially deployed "
                    f"({running_count}/{len(network.agents)} agents)"
                )
            else:
                deployment.status = "error"
                deployment.error_message = "No agents launched successfully"

        except Exception as e:
            deployment.status = "error"
            deployment.error_message = str(e)
            self.logger.error(f"Failed to launch network {network.id}: {e}")

            # Cleanup any successfully launched containers on failure
            cleanup_errors = []
            for agent_id, agent_container in deployment.agents.items():
                if agent_container.status == "running":
                    try:
                        await self.launcher.stop(agent_id, remove=True)
                        self.logger.info(f"Cleaned up agent {agent_id} after deployment failure")
                    except Exception as cleanup_error:
                        cleanup_errors.append(f"{agent_id}: {cleanup_error}")
                        self.logger.warning(f"Failed to cleanup agent {agent_id}: {cleanup_error}")

            if cleanup_errors:
                deployment.error_message += f"; Cleanup errors: {', '.join(cleanup_errors)}"

            # Remove the Docker network if it was created
            if docker_net_name:
                try:
                    self.docker.delete_network(docker_net_name, force=True)
                    self.logger.info(f"Cleaned up Docker network {docker_net_name} after deployment failure")
                except Exception as net_error:
                    self.logger.warning(f"Failed to cleanup network {docker_net_name}: {net_error}")

        return deployment

    async def stop(
        self,
        network_id: str,
        remove_containers: bool = True,
        remove_network: bool = True,
        save_state: bool = True
    ) -> bool:
        """
        Stop a network deployment

        Args:
            network_id: Network identifier
            remove_containers: Remove containers after stopping
            remove_network: Remove Docker network
            save_state: Save agent states before stopping

        Returns:
            True if stopped successfully
        """
        if network_id not in self._deployments:
            return False

        deployment = self._deployments[network_id]
        deployment.status = "stopping"

        try:
            # Save state if requested
            if save_state:
                await self._save_network_state(network_id)

            # Stop all agents
            for agent_id in list(deployment.agents.keys()):
                await self.launcher.stop(agent_id, remove=remove_containers)
                deployment.agents[agent_id].status = "stopped"

            # Remove Docker network
            if remove_network and deployment.docker_network:
                self.docker.delete_network(deployment.docker_network, force=True)

            deployment.status = "stopped"
            deployment.stopped_at = datetime.now().isoformat()
            self.logger.info(f"Network {network_id} stopped")

            return True

        except Exception as e:
            self.logger.error(f"Error stopping network {network_id}: {e}")
            return False

    async def _save_network_state(self, network_id: str):
        """Save current state of all agents in network"""
        deployment = self._deployments.get(network_id)
        if not deployment:
            return

        # Load network from persistence
        network = self.persistence.load_network(network_id)
        if not network:
            return

        # Update each agent's state
        for agent in network.agents:
            if agent.id in deployment.agents:
                agent_container = deployment.agents[agent.id]
                if agent_container.status == "running":
                    # TODO: Fetch actual state from running container via API
                    # For now, just update with container info
                    agent.state = capture_agent_state(
                        agent,
                        ospf_data={},  # Would fetch from container
                        bgp_data={}
                    ).state
                    agent.meta["last_container_ip"] = agent_container.ip_address

        # Save updated network
        self.persistence.save_network(network)

    def get_status(self, network_id: str) -> Optional[NetworkDeployment]:
        """
        Get network deployment status

        Args:
            network_id: Network identifier

        Returns:
            NetworkDeployment or None
        """
        if network_id not in self._deployments:
            return None

        deployment = self._deployments[network_id]

        # Refresh agent statuses
        for agent_id in deployment.agents:
            status = self.launcher.get_status(agent_id)
            if status:
                deployment.agents[agent_id] = status

        # Update deployment status based on agent statuses
        running_count = sum(
            1 for a in deployment.agents.values()
            if a.status == "running"
        )

        if running_count == 0 and deployment.status == "running":
            deployment.status = "stopped"
        elif running_count > 0 and running_count < len(deployment.agents):
            if deployment.status not in ["deploying", "stopping"]:
                deployment.status = "degraded"

        return deployment

    def get_agent_logs(self, network_id: str, agent_id: str, tail: int = 100) -> Optional[str]:
        """
        Get logs for a specific agent in a network

        Args:
            network_id: Network identifier
            agent_id: Agent identifier
            tail: Number of lines

        Returns:
            Log string or None
        """
        if network_id not in self._deployments:
            return None

        return self.launcher.get_logs(agent_id, tail)

    def list_deployments(self) -> List[NetworkDeployment]:
        """
        List all network deployments

        Returns:
            List of NetworkDeployment
        """
        # Refresh all deployments
        for network_id in list(self._deployments.keys()):
            self.get_status(network_id)

        return list(self._deployments.values())

    async def restart_agent(self, network_id: str, agent_id: str) -> bool:
        """
        Restart a specific agent in a network

        Args:
            network_id: Network identifier
            agent_id: Agent identifier

        Returns:
            True if restarted successfully
        """
        if network_id not in self._deployments:
            return False

        deployment = self._deployments[network_id]
        if agent_id not in deployment.agents:
            return False

        # Get agent config
        network = self.persistence.load_network(network_id)
        if not network:
            return False

        agent = network.get_agent(agent_id)
        if not agent:
            return False

        # Stop and relaunch
        await self.launcher.stop(agent_id, remove=True)

        result = await self.launcher.launch(
            agent=agent,
            network_name=deployment.docker_network,
            api_keys=None  # TODO: Store and retrieve API keys
        )

        deployment.agents[agent_id] = result
        return result.status == "running"

    async def health_check(self, network_id: str) -> Dict[str, Any]:
        """
        Perform health check on network

        Args:
            network_id: Network identifier

        Returns:
            Health check results
        """
        deployment = self.get_status(network_id)
        if not deployment:
            return {"status": "not_found"}

        results = {
            "network_id": network_id,
            "status": deployment.status,
            "agents": {},
            "healthy": True,
            "timestamp": datetime.now().isoformat()
        }

        for agent_id, agent in deployment.agents.items():
            agent_health = {
                "status": agent.status,
                "container_id": agent.container_id,
                "ip_address": agent.ip_address,
                "healthy": agent.status == "running"
            }
            results["agents"][agent_id] = agent_health

            if not agent_health["healthy"]:
                results["healthy"] = False

        return results


# Module-level convenience functions

_default_orchestrator: Optional[NetworkOrchestrator] = None


def get_orchestrator() -> NetworkOrchestrator:
    """Get or create default network orchestrator"""
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = NetworkOrchestrator()
    return _default_orchestrator


async def launch_network(
    network: TOONNetwork,
    image: Optional[str] = None,
    api_keys: Optional[Dict[str, str]] = None
) -> NetworkDeployment:
    """Launch network using default orchestrator"""
    return await get_orchestrator().launch(network, image, api_keys)


async def stop_network(network_id: str, save_state: bool = True) -> bool:
    """Stop network using default orchestrator"""
    return await get_orchestrator().stop(network_id, save_state=save_state)


def get_network_status(network_id: str) -> Optional[NetworkDeployment]:
    """Get network status using default orchestrator"""
    return get_orchestrator().get_status(network_id)
