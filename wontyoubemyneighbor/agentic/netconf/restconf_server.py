"""
RESTCONF Server Implementation for ASI Agents

Provides RESTCONF (RESTful NETCONF) server capabilities
as defined in RFC 8040. Allows external tools to configure
agents using a RESTful HTTP-based interface.

RFC Compliance:
- RFC 8040: RESTCONF Protocol
- RFC 7950: YANG 1.1 Data Modeling Language
- RFC 8341: Network Configuration Access Control Model
"""

import asyncio
import logging
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import copy

logger = logging.getLogger(__name__)

# RESTCONF media types
RESTCONF_JSON = "application/yang-data+json"
RESTCONF_XML = "application/yang-data+xml"


@dataclass
class RESTCONFConfig:
    """RESTCONF server configuration"""
    port: int = 8443
    host: str = "0.0.0.0"
    use_https: bool = True
    cert_file: Optional[str] = None
    key_file: Optional[str] = None
    max_connections: int = 100
    idle_timeout: int = 300
    default_username: str = "admin"
    default_password: str = "admin"
    api_root: str = "/restconf"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "port": self.port,
            "host": self.host,
            "use_https": self.use_https,
            "max_connections": self.max_connections,
            "idle_timeout": self.idle_timeout,
            "api_root": self.api_root
        }


@dataclass
class RESTCONFStatistics:
    """RESTCONF server statistics"""
    total_requests: int = 0
    get_requests: int = 0
    post_requests: int = 0
    put_requests: int = 0
    patch_requests: int = 0
    delete_requests: int = 0
    failed_requests: int = 0
    uptime_seconds: float = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "total_requests": self.total_requests,
            "get_requests": self.get_requests,
            "post_requests": self.post_requests,
            "put_requests": self.put_requests,
            "patch_requests": self.patch_requests,
            "delete_requests": self.delete_requests,
            "failed_requests": self.failed_requests,
            "uptime_seconds": self.uptime_seconds
        }


class RESTCONFDatastore:
    """
    RESTCONF datastore with YANG-like path support.

    Provides hierarchical configuration storage accessible via RESTful paths.
    """

    def __init__(self):
        self._data = self._default_data()

    def _default_data(self) -> Dict[str, Any]:
        """Return default data structure following YANG modules"""
        return {
            "ietf-system:system": {
                "hostname": "agent",
                "contact": "",
                "location": "",
                "clock": {
                    "timezone-name": "UTC"
                },
                "ntp": {
                    "enabled": False,
                    "server": []
                },
                "dns-resolver": {
                    "search": [],
                    "server": []
                }
            },
            "ietf-interfaces:interfaces": {
                "interface": []
            },
            "ietf-routing:routing": {
                "control-plane-protocols": {
                    "control-plane-protocol": []
                },
                "ribs": {
                    "rib": [
                        {
                            "name": "ipv4-main",
                            "address-family": "ipv4"
                        },
                        {
                            "name": "ipv6-main",
                            "address-family": "ipv6"
                        }
                    ]
                }
            },
            "ietf-access-control:nacm": {
                "enable-nacm": True,
                "groups": {
                    "group": []
                },
                "rule-list": []
            }
        }

    def get(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Get data at path.

        Args:
            path: RESTCONF path (e.g., /data/ietf-interfaces:interfaces)

        Returns:
            Data at path or None if not found
        """
        # Remove /data prefix if present
        if path.startswith("/data"):
            path = path[5:]

        if not path or path == "/":
            return copy.deepcopy(self._data)

        # Parse path segments
        segments = [s for s in path.strip("/").split("/") if s]

        current = self._data
        for segment in segments:
            # Handle list key predicates like interface[name='eth0']
            if "[" in segment:
                name = segment.split("[")[0]
                predicate = segment.split("[")[1].rstrip("]")
                key, value = predicate.split("=")
                value = value.strip("'\"")

                if name in current and isinstance(current[name], list):
                    found = None
                    for item in current[name]:
                        if isinstance(item, dict) and item.get(key) == value:
                            found = item
                            break
                    if found:
                        current = found
                    else:
                        return None
                else:
                    return None
            elif isinstance(current, dict) and segment in current:
                current = current[segment]
            else:
                return None

        return copy.deepcopy(current) if isinstance(current, (dict, list)) else {"value": current}

    def put(self, path: str, data: Dict[str, Any]) -> bool:
        """
        Replace data at path (PUT).

        Args:
            path: RESTCONF path
            data: Data to set

        Returns:
            True if successful
        """
        if path.startswith("/data"):
            path = path[5:]

        if not path or path == "/":
            self._data = copy.deepcopy(data)
            return True

        segments = [s for s in path.strip("/").split("/") if s]

        # Navigate to parent
        current = self._data
        for segment in segments[:-1]:
            if "[" in segment:
                name = segment.split("[")[0]
                predicate = segment.split("[")[1].rstrip("]")
                key, value = predicate.split("=")
                value = value.strip("'\"")

                if name not in current:
                    current[name] = []
                if isinstance(current[name], list):
                    found = None
                    for item in current[name]:
                        if isinstance(item, dict) and item.get(key) == value:
                            found = item
                            break
                    if not found:
                        found = {key: value}
                        current[name].append(found)
                    current = found
            else:
                if segment not in current:
                    current[segment] = {}
                current = current[segment]

        # Set the final segment
        final = segments[-1] if segments else None
        if final:
            if "[" in final:
                name = final.split("[")[0]
                # Replace in list
                if name not in current:
                    current[name] = []
                # For simplicity, append/replace
                current[name] = [data] if not isinstance(data, list) else data
            else:
                current[final] = copy.deepcopy(data)

        return True

    def post(self, path: str, data: Dict[str, Any]) -> bool:
        """
        Create data at path (POST).

        Args:
            path: RESTCONF path
            data: Data to create

        Returns:
            True if successful
        """
        if path.startswith("/data"):
            path = path[5:]

        parent = self.get(path)
        if parent is None:
            # Create path
            return self.put(path, data)

        # If parent is a list, append
        if isinstance(parent, list):
            segments = [s for s in path.strip("/").split("/") if s]
            current = self._data
            for segment in segments:
                if isinstance(current, dict) and segment in current:
                    current = current[segment]

            if isinstance(current, list):
                current.append(copy.deepcopy(data))
                return True

        # Otherwise merge
        return self.patch(path, data)

    def patch(self, path: str, data: Dict[str, Any]) -> bool:
        """
        Merge data at path (PATCH).

        Args:
            path: RESTCONF path
            data: Data to merge

        Returns:
            True if successful
        """
        if path.startswith("/data"):
            path = path[5:]

        existing = self.get(path)
        if existing is None:
            return self.put(path, data)

        if isinstance(existing, dict) and isinstance(data, dict):
            self._deep_merge(existing, data)
            return self.put(path, existing)

        return self.put(path, data)

    def delete(self, path: str) -> bool:
        """
        Delete data at path (DELETE).

        Args:
            path: RESTCONF path

        Returns:
            True if successful
        """
        if path.startswith("/data"):
            path = path[5:]

        if not path or path == "/":
            self._data = self._default_data()
            return True

        segments = [s for s in path.strip("/").split("/") if s]

        # Navigate to parent
        current = self._data
        for segment in segments[:-1]:
            if "[" in segment:
                name = segment.split("[")[0]
                predicate = segment.split("[")[1].rstrip("]")
                key, value = predicate.split("=")
                value = value.strip("'\"")

                if isinstance(current.get(name), list):
                    found = None
                    for item in current[name]:
                        if isinstance(item, dict) and item.get(key) == value:
                            found = item
                            break
                    if found:
                        current = found
                    else:
                        return False
            elif isinstance(current, dict) and segment in current:
                current = current[segment]
            else:
                return False

        # Delete final segment
        final = segments[-1]
        if "[" in final:
            name = final.split("[")[0]
            predicate = final.split("[")[1].rstrip("]")
            key, value = predicate.split("=")
            value = value.strip("'\"")

            if isinstance(current.get(name), list):
                current[name] = [
                    item for item in current[name]
                    if not (isinstance(item, dict) and item.get(key) == value)
                ]
                return True
        elif isinstance(current, dict) and final in current:
            del current[final]
            return True

        return False

    def _deep_merge(self, base: Dict, overlay: Dict):
        """Deep merge overlay into base"""
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = copy.deepcopy(value)


class RESTCONFServer:
    """
    RESTCONF Server for ASI agents.

    Provides RFC 8040 compliant RESTCONF server functionality.
    This implementation provides the API handlers that can be
    integrated with FastAPI or another web framework.
    """

    def __init__(
        self,
        agent_name: str,
        config: Optional[RESTCONFConfig] = None,
        apply_handler: Optional[Callable[[Dict], asyncio.Future]] = None
    ):
        """
        Initialize RESTCONF server.

        Args:
            agent_name: Name of the agent
            config: Server configuration
            apply_handler: Async function to apply configuration changes
        """
        self.agent_name = agent_name
        self.config = config or RESTCONFConfig()
        self.apply_handler = apply_handler

        self._datastore = RESTCONFDatastore()
        self._running = False
        self._started_at: Optional[datetime] = None
        self._statistics = RESTCONFStatistics()

    async def start(self) -> bool:
        """Start the RESTCONF server"""
        if self._running:
            logger.warning(f"RESTCONF server for {self.agent_name} already running")
            return False

        self._running = True
        self._started_at = datetime.now()
        logger.info(
            f"RESTCONF server for {self.agent_name} started on port {self.config.port}"
        )
        return True

    async def stop(self):
        """Stop the RESTCONF server"""
        if not self._running:
            return

        self._running = False
        logger.info(f"RESTCONF server for {self.agent_name} stopped")

    @property
    def running(self) -> bool:
        """Check if server is running"""
        return self._running

    async def handle_get(self, path: str) -> Dict[str, Any]:
        """
        Handle GET request.

        Args:
            path: RESTCONF path

        Returns:
            Response data
        """
        self._statistics.total_requests += 1
        self._statistics.get_requests += 1

        # Handle well-known entry points
        if path == "/.well-known/host-meta":
            return {
                "link": {
                    "rel": "restconf",
                    "href": self.config.api_root
                }
            }

        if path == f"{self.config.api_root}" or path == f"{self.config.api_root}/":
            return self._get_root_resource()

        if path.startswith(f"{self.config.api_root}/data"):
            data_path = path[len(f"{self.config.api_root}/data"):]
            data = self._datastore.get(data_path or "/")
            if data is not None:
                return {"data": data}
            else:
                self._statistics.failed_requests += 1
                return {"error": "data-missing", "message": "Requested data not found"}

        if path.startswith(f"{self.config.api_root}/operations"):
            return {"operations": self._get_operations()}

        if path.startswith(f"{self.config.api_root}/yang-library-version"):
            return {"yang-library-version": "2019-01-04"}

        self._statistics.failed_requests += 1
        return {"error": "invalid-path", "message": f"Invalid path: {path}"}

    async def handle_post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle POST request (create).

        Args:
            path: RESTCONF path
            data: Data to create

        Returns:
            Response data
        """
        self._statistics.total_requests += 1
        self._statistics.post_requests += 1

        if path.startswith(f"{self.config.api_root}/data"):
            data_path = path[len(f"{self.config.api_root}/data"):]
            if self._datastore.post(data_path or "/", data):
                if self.apply_handler:
                    await self.apply_handler(self._datastore.get("/"))
                return {"success": True, "message": "Created"}
            else:
                self._statistics.failed_requests += 1
                return {"error": "operation-failed", "message": "Failed to create"}

        if path.startswith(f"{self.config.api_root}/operations"):
            return await self._handle_operation(path, data)

        self._statistics.failed_requests += 1
        return {"error": "invalid-path", "message": f"Invalid path: {path}"}

    async def handle_put(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle PUT request (replace).

        Args:
            path: RESTCONF path
            data: Data to set

        Returns:
            Response data
        """
        self._statistics.total_requests += 1
        self._statistics.put_requests += 1

        if path.startswith(f"{self.config.api_root}/data"):
            data_path = path[len(f"{self.config.api_root}/data"):]
            if self._datastore.put(data_path or "/", data):
                if self.apply_handler:
                    await self.apply_handler(self._datastore.get("/"))
                return {"success": True, "message": "Updated"}
            else:
                self._statistics.failed_requests += 1
                return {"error": "operation-failed", "message": "Failed to update"}

        self._statistics.failed_requests += 1
        return {"error": "invalid-path", "message": f"Invalid path: {path}"}

    async def handle_patch(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle PATCH request (merge).

        Args:
            path: RESTCONF path
            data: Data to merge

        Returns:
            Response data
        """
        self._statistics.total_requests += 1
        self._statistics.patch_requests += 1

        if path.startswith(f"{self.config.api_root}/data"):
            data_path = path[len(f"{self.config.api_root}/data"):]
            if self._datastore.patch(data_path or "/", data):
                if self.apply_handler:
                    await self.apply_handler(self._datastore.get("/"))
                return {"success": True, "message": "Patched"}
            else:
                self._statistics.failed_requests += 1
                return {"error": "operation-failed", "message": "Failed to patch"}

        self._statistics.failed_requests += 1
        return {"error": "invalid-path", "message": f"Invalid path: {path}"}

    async def handle_delete(self, path: str) -> Dict[str, Any]:
        """
        Handle DELETE request.

        Args:
            path: RESTCONF path

        Returns:
            Response data
        """
        self._statistics.total_requests += 1
        self._statistics.delete_requests += 1

        if path.startswith(f"{self.config.api_root}/data"):
            data_path = path[len(f"{self.config.api_root}/data"):]
            if self._datastore.delete(data_path or "/"):
                if self.apply_handler:
                    await self.apply_handler(self._datastore.get("/"))
                return {"success": True, "message": "Deleted"}
            else:
                self._statistics.failed_requests += 1
                return {"error": "data-missing", "message": "Data not found"}

        self._statistics.failed_requests += 1
        return {"error": "invalid-path", "message": f"Invalid path: {path}"}

    def _get_root_resource(self) -> Dict[str, Any]:
        """Get RESTCONF root resource"""
        return {
            "ietf-restconf:restconf": {
                "data": {},
                "operations": {},
                "yang-library-version": "2019-01-04"
            }
        }

    def _get_operations(self) -> List[str]:
        """Get available YANG operations"""
        return [
            "ietf-system:system-restart",
            "ietf-system:system-shutdown",
            "ietf-interfaces:clear-interface-statistics"
        ]

    async def _handle_operation(
        self,
        path: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle RPC operation"""
        op_path = path[len(f"{self.config.api_root}/operations"):]
        op_name = op_path.strip("/")

        if op_name == "ietf-system:system-restart":
            return {"output": {"status": "restart-scheduled"}}
        elif op_name == "ietf-system:system-shutdown":
            return {"output": {"status": "shutdown-scheduled"}}
        elif op_name == "ietf-interfaces:clear-interface-statistics":
            interface = data.get("input", {}).get("interface", "all")
            return {"output": {"status": "ok", "interface": interface}}

        self._statistics.failed_requests += 1
        return {"error": "unknown-operation", "message": f"Operation not found: {op_name}"}

    def get_statistics(self) -> RESTCONFStatistics:
        """Get server statistics"""
        if self._started_at:
            self._statistics.uptime_seconds = (
                datetime.now() - self._started_at
            ).total_seconds()
        return self._statistics

    def get_config(self) -> Dict[str, Any]:
        """Get server configuration"""
        return self.config.to_dict()

    def get_data(self, path: str = "/") -> Dict[str, Any]:
        """Get datastore data"""
        return self._datastore.get(path) or {}


# Global RESTCONF server instances
_restconf_servers: Dict[str, RESTCONFServer] = {}


def get_restconf_server(agent_name: str) -> Optional[RESTCONFServer]:
    """Get RESTCONF server for an agent"""
    return _restconf_servers.get(agent_name)


async def start_restconf_server(
    agent_name: str,
    port: int = 8443,
    apply_handler: Optional[Callable[[Dict], asyncio.Future]] = None,
    **config_kwargs
) -> RESTCONFServer:
    """
    Start RESTCONF server for an agent.

    Args:
        agent_name: Name of the agent
        port: RESTCONF port
        apply_handler: Async function to apply configuration
        **config_kwargs: Additional RESTCONFConfig parameters

    Returns:
        RESTCONFServer instance
    """
    if agent_name in _restconf_servers:
        return _restconf_servers[agent_name]

    config = RESTCONFConfig(port=port, **config_kwargs)
    server = RESTCONFServer(agent_name, config, apply_handler)

    if await server.start():
        _restconf_servers[agent_name] = server
        logger.info(f"RESTCONF server started for {agent_name} on port {port}")
    else:
        raise RuntimeError(f"Failed to start RESTCONF server for {agent_name}")

    return server


async def stop_restconf_server(agent_name: str):
    """Stop RESTCONF server for an agent"""
    if agent_name in _restconf_servers:
        server = _restconf_servers.pop(agent_name)
        await server.stop()
        logger.info(f"RESTCONF server stopped for {agent_name}")


def get_restconf_statistics(agent_name: Optional[str] = None) -> Dict[str, Any]:
    """Get RESTCONF statistics"""
    if agent_name:
        server = _restconf_servers.get(agent_name)
        if server:
            return server.get_statistics().to_dict()
        return {}

    return {
        name: server.get_statistics().to_dict()
        for name, server in _restconf_servers.items()
    }
