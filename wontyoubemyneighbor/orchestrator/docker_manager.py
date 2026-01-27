"""
Docker Manager for Multi-Agent Orchestration

Provides low-level Docker operations for:
- Container lifecycle management
- Network creation and configuration
- Image management
- Volume management
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

try:
    import docker
    from docker.errors import DockerException, NotFound, APIError
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None


class DockerNotAvailableError(Exception):
    """Raised when Docker is not available or not running"""
    pass


@dataclass
class ContainerInfo:
    """Container status information"""
    id: str
    name: str
    status: str  # running, exited, paused, etc.
    image: str
    created: str
    network: Optional[str] = None
    ip_address: Optional[str] = None
    ip_address_v6: Optional[str] = None  # IPv6 address for dual-stack support
    ports: Dict[str, Any] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    health: Optional[str] = None


@dataclass
class NetworkInfo:
    """Docker network information"""
    id: str
    name: str
    driver: str
    subnet: Optional[str] = None
    gateway: Optional[str] = None
    # IPv6 dual-stack support (3-layer architecture)
    subnet6: Optional[str] = None  # IPv6 subnet (e.g., "fd00:d0c:1::/64")
    gateway6: Optional[str] = None  # IPv6 gateway
    ipv6_enabled: bool = False
    containers: List[str] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)


def check_docker_available() -> Tuple[bool, str]:
    """
    Check if Docker is available and running

    Returns:
        Tuple of (available: bool, message: str)
    """
    if not DOCKER_AVAILABLE:
        return False, "Docker SDK not installed. Install with: pip install docker"

    try:
        client = docker.from_env()
        client.ping()
        version = client.version()
        return True, f"Docker {version.get('Version', 'unknown')} available"
    except DockerException as e:
        return False, f"Docker not running or not accessible: {e}"
    except Exception as e:
        return False, f"Error checking Docker: {e}"


def get_docker_client():
    """
    Get Docker client instance

    Returns:
        Docker client

    Raises:
        DockerNotAvailableError: If Docker is not available
    """
    if not DOCKER_AVAILABLE:
        raise DockerNotAvailableError("Docker SDK not installed")

    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as e:
        raise DockerNotAvailableError(f"Cannot connect to Docker: {e}")


class DockerManager:
    """
    Docker operations manager for multi-agent orchestration
    """

    def __init__(self):
        """Initialize Docker manager"""
        self.logger = logging.getLogger("DockerManager")
        self._client = None
        self._available = None
        self._error_message = None

    @property
    def client(self):
        """Get Docker client (lazy initialization)"""
        if self._client is None:
            self._check_availability()
        return self._client

    @property
    def available(self) -> bool:
        """Check if Docker is available"""
        if self._available is None:
            self._check_availability()
        return self._available

    @property
    def error_message(self) -> Optional[str]:
        """Get error message if Docker is not available"""
        if self._available is None:
            self._check_availability()
        return self._error_message

    def _check_availability(self):
        """Check Docker availability and cache result"""
        available, message = check_docker_available()
        self._available = available
        if available:
            self._client = get_docker_client()
            self.logger.info(f"Docker available: {message}")
        else:
            self._error_message = message
            self.logger.warning(f"Docker not available: {message}")

    # Network Operations

    def create_network(
        self,
        name: str,
        subnet: Optional[str] = None,
        gateway: Optional[str] = None,
        subnet6: Optional[str] = None,
        gateway6: Optional[str] = None,
        enable_ipv6: bool = False,
        driver: str = "bridge",
        labels: Optional[Dict[str, str]] = None
    ) -> NetworkInfo:
        """
        Create a Docker network with optional dual-stack (IPv4 + IPv6) support

        3-Layer Network Architecture:
          Layer 1: Docker Network (this layer) - container connectivity
          Layer 2: ASI Overlay (IPv6 agent mesh) - auto-configured per agent
          Layer 3: Underlay (user-defined routing topology)

        Args:
            name: Network name
            subnet: IPv4 CIDR subnet (e.g., "172.20.0.0/16")
            gateway: IPv4 Gateway IP
            subnet6: IPv6 CIDR subnet (e.g., "fd00:d0c:1::/64")
            gateway6: IPv6 Gateway
            enable_ipv6: Enable IPv6 on the network (required for dual-stack)
            driver: Network driver (bridge, overlay, etc.)
            labels: Network labels

        Returns:
            NetworkInfo for created network
        """
        if not self.available:
            raise DockerNotAvailableError(self.error_message)

        # Check if network already exists
        try:
            existing = self.client.networks.get(name)
            self.logger.warning(f"Network {name} already exists, returning existing")
            return self._network_to_info(existing)
        except NotFound:
            pass

        # Build IPAM config with optional dual-stack
        ipam_pools = []

        # IPv4 pool
        if subnet:
            ipam_pools.append(docker.types.IPAMPool(
                subnet=subnet,
                gateway=gateway
            ))

        # IPv6 pool (for dual-stack)
        if subnet6 and enable_ipv6:
            ipam_pools.append(docker.types.IPAMPool(
                subnet=subnet6,
                gateway=gateway6
            ))
            self.logger.info(f"IPv6 enabled for network {name}: {subnet6}")

        ipam_config = None
        if ipam_pools:
            ipam_config = docker.types.IPAMConfig(pool_configs=ipam_pools)

        # Prepare network options for IPv6
        network_options = {}
        if enable_ipv6 and driver == "bridge":
            # Enable IPv6 routing in bridge network
            network_options["com.docker.network.bridge.enable_ip_masquerade"] = "true"

        # Create network with dual-stack support
        network = self.client.networks.create(
            name=name,
            driver=driver,
            ipam=ipam_config,
            enable_ipv6=enable_ipv6,
            options=network_options if network_options else None,
            labels=labels or {"asi.managed": "true"}
        )

        subnet_info = f"{subnet or 'auto'}"
        if subnet6 and enable_ipv6:
            subnet_info += f", {subnet6}"
        self.logger.info(f"Created Docker network: {name} ({subnet_info})")

        return self._network_to_info(network)

    def get_network(self, name: str) -> Optional[NetworkInfo]:
        """Get network info by name"""
        if not self.available:
            return None

        try:
            network = self.client.networks.get(name)
            return self._network_to_info(network)
        except NotFound:
            return None

    def delete_network(self, name: str, force: bool = False) -> bool:
        """
        Delete a Docker network

        Args:
            name: Network name
            force: Disconnect containers first

        Returns:
            True if deleted
        """
        if not self.available:
            return False

        try:
            network = self.client.networks.get(name)

            if force:
                # Disconnect all containers
                for container in network.containers:
                    try:
                        network.disconnect(container, force=True)
                    except Exception as e:
                        self.logger.warning(f"Error disconnecting container: {e}")

            network.remove()
            self.logger.info(f"Deleted Docker network: {name}")
            return True
        except NotFound:
            return False
        except APIError as e:
            self.logger.error(f"Error deleting network {name}: {e}")
            return False

    def list_networks(self, asi_only: bool = True) -> List[NetworkInfo]:
        """
        List Docker networks

        Args:
            asi_only: Only return ASI-managed networks

        Returns:
            List of NetworkInfo
        """
        if not self.available:
            return []

        filters = {}
        if asi_only:
            filters["label"] = "asi.managed=true"

        networks = self.client.networks.list(filters=filters)
        return [self._network_to_info(n) for n in networks]

    def _network_to_info(self, network) -> NetworkInfo:
        """Convert Docker network to NetworkInfo"""
        attrs = network.attrs
        ipam_configs = attrs.get("IPAM", {}).get("Config", [])

        # Parse IPv4 and IPv6 configurations
        subnet = None
        gateway = None
        subnet6 = None
        gateway6 = None

        for config in ipam_configs:
            config_subnet = config.get("Subnet", "")
            config_gateway = config.get("Gateway")

            # Check if IPv6 (contains ':')
            if ':' in config_subnet:
                subnet6 = config_subnet
                gateway6 = config_gateway
            else:
                subnet = config_subnet
                gateway = config_gateway

        containers = []
        for container_id in attrs.get("Containers", {}).keys():
            containers.append(container_id[:12])

        # Check if IPv6 is enabled
        ipv6_enabled = attrs.get("EnableIPv6", False)

        return NetworkInfo(
            id=network.id[:12],
            name=network.name,
            driver=attrs.get("Driver", "unknown"),
            subnet=subnet,
            gateway=gateway,
            subnet6=subnet6,
            gateway6=gateway6,
            ipv6_enabled=ipv6_enabled,
            containers=containers,
            labels=attrs.get("Labels", {})
        )

    # Container Operations

    def create_container(
        self,
        name: str,
        image: str,
        network: str,
        command: Optional[List[str]] = None,
        environment: Optional[Dict[str, str]] = None,
        ports: Optional[Dict[str, int]] = None,
        volumes: Optional[Dict[str, Dict]] = None,
        labels: Optional[Dict[str, str]] = None,
        privileged: bool = False,
        cap_add: Optional[List[str]] = None,
        ip_address: Optional[str] = None
    ) -> ContainerInfo:
        """
        Create and start a container

        Args:
            name: Container name
            image: Docker image
            network: Network to connect to
            command: Container command
            environment: Environment variables
            ports: Port mappings {container_port: host_port}
            volumes: Volume mounts
            labels: Container labels
            privileged: Run in privileged mode
            cap_add: Additional capabilities
            ip_address: Specific IP address to assign (requires network with subnet)

        Returns:
            ContainerInfo for created container
        """
        if not self.available:
            raise DockerNotAvailableError(self.error_message)

        # Check if container already exists
        try:
            existing = self.client.containers.get(name)
            if existing.status == "running":
                self.logger.warning(f"Container {name} already running")
                return self._container_to_info(existing)
            else:
                # Remove stopped container
                existing.remove()
        except NotFound:
            pass

        # Build port bindings
        port_bindings = None
        if ports:
            port_bindings = {f"{p}/tcp": hp for p, hp in ports.items()}

        # Default labels
        default_labels = {
            "asi.managed": "true",
            "asi.created": datetime.now().isoformat()
        }
        if labels:
            default_labels.update(labels)

        # Create container - always connect to the specified network
        # If we need a specific IP, we'll reconnect with that IP after creation
        container = self.client.containers.run(
            image=image,
            name=name,
            hostname=name,  # Set hostname to container name for identification
            command=command,
            environment=environment or {},
            ports=port_bindings,
            volumes=volumes,
            labels=default_labels,
            network=network,  # Always connect to the specified network
            privileged=privileged,
            cap_add=cap_add or [],
            detach=True,
            remove=False
        )

        # If we need a specific IP, disconnect and reconnect with that IP
        if ip_address:
            try:
                net = self.client.networks.get(network)
                # Disconnect from network (Docker assigned a random IP)
                net.disconnect(container)
                # Reconnect with the specific IP
                net.connect(container, ipv4_address=ip_address)
                self.logger.info(f"Assigned IP {ip_address} to container {name}")
            except Exception as e:
                self.logger.warning(f"Failed to assign specific IP {ip_address}: {e}")

        # Refresh container to get updated network info (IP address)
        container.reload()

        self.logger.info(f"Created container: {name} on network {network}")
        return self._container_to_info(container)

    def get_container(self, name: str) -> Optional[ContainerInfo]:
        """Get container info by name"""
        if not self.available:
            return None

        try:
            container = self.client.containers.get(name)
            return self._container_to_info(container)
        except NotFound:
            return None

    def stop_container(self, name: str, timeout: int = 10) -> bool:
        """
        Stop a container

        Args:
            name: Container name
            timeout: Stop timeout in seconds

        Returns:
            True if stopped
        """
        if not self.available:
            return False

        try:
            container = self.client.containers.get(name)
            container.stop(timeout=timeout)
            self.logger.info(f"Stopped container: {name}")
            return True
        except NotFound:
            return False
        except Exception as e:
            self.logger.error(f"Error stopping container {name}: {e}")
            return False

    def remove_container(self, name: str, force: bool = False) -> bool:
        """
        Remove a container

        Args:
            name: Container name
            force: Force removal (kill if running)

        Returns:
            True if removed
        """
        if not self.available:
            return False

        try:
            container = self.client.containers.get(name)
            container.remove(force=force)
            self.logger.info(f"Removed container: {name}")
            return True
        except NotFound:
            return False
        except Exception as e:
            self.logger.error(f"Error removing container {name}: {e}")
            return False

    def get_container_logs(self, name: str, tail: int = 100) -> Optional[str]:
        """
        Get container logs

        Args:
            name: Container name
            tail: Number of lines to return

        Returns:
            Log string or None
        """
        if not self.available:
            return None

        try:
            container = self.client.containers.get(name)
            logs = container.logs(tail=tail, timestamps=True)
            return logs.decode("utf-8") if isinstance(logs, bytes) else logs
        except NotFound:
            return None
        except Exception as e:
            self.logger.error(f"Error getting logs for {name}: {e}")
            return None

    def list_containers(self, asi_only: bool = True, all: bool = True) -> List[ContainerInfo]:
        """
        List containers

        Args:
            asi_only: Only return ASI-managed containers
            all: Include stopped containers

        Returns:
            List of ContainerInfo
        """
        if not self.available:
            return []

        filters = {}
        if asi_only:
            filters["label"] = "asi.managed=true"

        containers = self.client.containers.list(all=all, filters=filters)
        return [self._container_to_info(c) for c in containers]

    def _container_to_info(self, container) -> ContainerInfo:
        """Convert Docker container to ContainerInfo"""
        attrs = container.attrs
        network_settings = attrs.get("NetworkSettings", {})

        # Get network IP - prefer non-default networks over "bridge"
        networks = network_settings.get("Networks", {})
        network_name = None
        ip_address = None
        ip_address_v6 = None

        # First, try to find a non-bridge network (our custom networks)
        for name, config in networks.items():
            if name != "bridge":
                network_name = name
                ip_address = config.get("IPAddress")
                # Get IPv6 address if available (dual-stack)
                ipv6_addr = config.get("GlobalIPv6Address")
                if ipv6_addr:
                    ip_address_v6 = ipv6_addr
                break

        # Fall back to any network if no custom network found
        if not ip_address:
            for name, config in networks.items():
                network_name = name
                ip_address = config.get("IPAddress")
                ipv6_addr = config.get("GlobalIPv6Address")
                if ipv6_addr:
                    ip_address_v6 = ipv6_addr
                break

        # Get health status
        health = None
        if "Health" in attrs.get("State", {}):
            health = attrs["State"]["Health"].get("Status")

        return ContainerInfo(
            id=container.id[:12],
            name=container.name,
            status=container.status,
            image=attrs.get("Config", {}).get("Image", "unknown"),
            created=attrs.get("Created", ""),
            network=network_name,
            ip_address=ip_address,
            ip_address_v6=ip_address_v6,
            ports=network_settings.get("Ports", {}),
            labels=attrs.get("Config", {}).get("Labels", {}),
            health=health
        )

    # Image Operations

    def pull_image(self, image: str) -> bool:
        """
        Pull a Docker image

        Args:
            image: Image name and tag

        Returns:
            True if pulled successfully
        """
        if not self.available:
            return False

        try:
            self.logger.info(f"Pulling image: {image}")
            self.client.images.pull(image)
            return True
        except Exception as e:
            self.logger.error(f"Error pulling image {image}: {e}")
            return False

    def image_exists(self, image: str) -> bool:
        """Check if image exists locally"""
        if not self.available:
            return False

        try:
            self.client.images.get(image)
            return True
        except NotFound:
            return False

    def build_image(
        self,
        path: str,
        tag: str,
        dockerfile: str = "Dockerfile"
    ) -> bool:
        """
        Build a Docker image

        Args:
            path: Build context path
            tag: Image tag
            dockerfile: Dockerfile name

        Returns:
            True if built successfully
        """
        if not self.available:
            return False

        try:
            self.logger.info(f"Building image: {tag} from {path}")
            self.client.images.build(
                path=path,
                tag=tag,
                dockerfile=dockerfile,
                rm=True
            )
            return True
        except Exception as e:
            self.logger.error(f"Error building image {tag}: {e}")
            return False
