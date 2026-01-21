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
        driver: str = "bridge",
        labels: Optional[Dict[str, str]] = None
    ) -> NetworkInfo:
        """
        Create a Docker network

        Args:
            name: Network name
            subnet: CIDR subnet (e.g., "172.20.0.0/16")
            gateway: Gateway IP
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

        # Build IPAM config if subnet specified
        ipam_config = None
        if subnet:
            ipam_pool = docker.types.IPAMPool(
                subnet=subnet,
                gateway=gateway
            )
            ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool])

        # Create network
        network = self.client.networks.create(
            name=name,
            driver=driver,
            ipam=ipam_config,
            labels=labels or {"rubberband.managed": "true"}
        )

        self.logger.info(f"Created Docker network: {name} ({subnet or 'auto'})")
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

    def list_networks(self, rubberband_only: bool = True) -> List[NetworkInfo]:
        """
        List Docker networks

        Args:
            rubberband_only: Only return RubberBand-managed networks

        Returns:
            List of NetworkInfo
        """
        if not self.available:
            return []

        filters = {}
        if rubberband_only:
            filters["label"] = "rubberband.managed=true"

        networks = self.client.networks.list(filters=filters)
        return [self._network_to_info(n) for n in networks]

    def _network_to_info(self, network) -> NetworkInfo:
        """Convert Docker network to NetworkInfo"""
        attrs = network.attrs
        ipam = attrs.get("IPAM", {}).get("Config", [{}])[0]

        containers = []
        for container_id in attrs.get("Containers", {}).keys():
            containers.append(container_id[:12])

        return NetworkInfo(
            id=network.id[:12],
            name=network.name,
            driver=attrs.get("Driver", "unknown"),
            subnet=ipam.get("Subnet"),
            gateway=ipam.get("Gateway"),
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
            "rubberband.managed": "true",
            "rubberband.created": datetime.now().isoformat()
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

    def list_containers(self, rubberband_only: bool = True, all: bool = True) -> List[ContainerInfo]:
        """
        List containers

        Args:
            rubberband_only: Only return RubberBand-managed containers
            all: Include stopped containers

        Returns:
            List of ContainerInfo
        """
        if not self.available:
            return []

        filters = {}
        if rubberband_only:
            filters["label"] = "rubberband.managed=true"

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

        # First, try to find a non-bridge network (our custom networks)
        for name, config in networks.items():
            if name != "bridge":
                network_name = name
                ip_address = config.get("IPAddress")
                break

        # Fall back to any network if no custom network found
        if not ip_address:
            for name, config in networks.items():
                network_name = name
                ip_address = config.get("IPAddress")
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
