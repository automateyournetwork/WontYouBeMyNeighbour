"""
NetBox MCP Client - DCIM/IPAM Integration

Provides integration with NetBox for:
- Device registration and inventory management
- IP address management (IPAM)
- Site and rack management
- Interface and cable documentation

This MCP allows agents to:
- Auto-register themselves as devices in NetBox
- Sync interface information
- Update IP address assignments
- Report device status
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import json

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger("NetBox_MCP")

# Singleton client instance
_netbox_client: Optional["NetBoxClient"] = None


class DeviceStatus(Enum):
    """NetBox device status choices"""
    ACTIVE = "active"
    PLANNED = "planned"
    STAGED = "staged"
    FAILED = "failed"
    INVENTORY = "inventory"
    DECOMMISSIONING = "decommissioning"
    OFFLINE = "offline"


@dataclass
class NetBoxConfig:
    """Configuration for NetBox connection"""
    url: str
    api_token: str
    # Auto-registration settings
    site_name: str = ""
    device_role: str = "router"
    device_type: str = "Virtual Router"
    manufacturer: str = "Virtual"
    platform: str = ""
    auto_register: bool = False
    # Optional settings
    verify_ssl: bool = True
    timeout: int = 30


@dataclass
class DeviceInfo:
    """Information about a device to register"""
    name: str
    site: str
    device_role: str
    device_type: str
    manufacturer: str
    platform: Optional[str] = None
    serial: Optional[str] = None
    status: DeviceStatus = DeviceStatus.ACTIVE
    primary_ip4: Optional[str] = None
    primary_ip6: Optional[str] = None
    comments: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    custom_fields: Dict[str, Any] = field(default_factory=dict)


class NetBoxClient:
    """
    NetBox API Client

    Handles communication with NetBox for device management and IPAM.
    """

    def __init__(self, config: NetBoxConfig):
        """
        Initialize NetBox client

        Args:
            config: NetBox configuration
        """
        self.config = config
        self.base_url = config.url.rstrip('/')
        self.headers = {
            "Authorization": f"Token {config.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self._http_client: Optional[httpx.AsyncClient] = None

        # Cache for resolved IDs
        self._site_cache: Dict[str, int] = {}
        self._role_cache: Dict[str, int] = {}
        self._type_cache: Dict[str, int] = {}
        self._manufacturer_cache: Dict[str, int] = {}
        self._platform_cache: Dict[str, int] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx is required for NetBox MCP. Install with: pip install httpx")

        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                verify=self.config.verify_ssl,
                timeout=self.config.timeout
            )
        return self._http_client

    async def close(self):
        """Close the HTTP client"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to NetBox

        Returns:
            Dict with connection status and NetBox version
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/status/")

            if response.status_code == 200:
                data = response.json()
                return {
                    "connected": True,
                    "netbox_version": data.get("netbox-version", "unknown"),
                    "python_version": data.get("python-version", "unknown"),
                    "plugins": data.get("plugins", {}),
                    "url": self.base_url
                }
            else:
                return {
                    "connected": False,
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "url": self.base_url
                }
        except Exception as e:
            logger.error(f"NetBox connection test failed: {e}")
            return {
                "connected": False,
                "error": str(e),
                "url": self.base_url
            }

    async def _get_or_create_site(self, name: str) -> int:
        """Get site ID by name, create if doesn't exist"""
        if name in self._site_cache:
            return self._site_cache[name]

        client = await self._get_client()

        # Search for existing site
        response = await client.get("/api/dcim/sites/", params={"name": name})
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                site_id = results[0]["id"]
                self._site_cache[name] = site_id
                return site_id

        # Create new site
        slug = name.lower().replace(" ", "-").replace("_", "-")
        response = await client.post("/api/dcim/sites/", json={
            "name": name,
            "slug": slug,
            "status": "active"
        })

        if response.status_code == 201:
            site_id = response.json()["id"]
            self._site_cache[name] = site_id
            logger.info(f"Created NetBox site: {name} (ID: {site_id})")
            return site_id
        else:
            raise Exception(f"Failed to create site '{name}': {response.text}")

    async def _get_or_create_manufacturer(self, name: str) -> int:
        """Get manufacturer ID by name, create if doesn't exist"""
        if name in self._manufacturer_cache:
            return self._manufacturer_cache[name]

        client = await self._get_client()

        # Search for existing manufacturer
        response = await client.get("/api/dcim/manufacturers/", params={"name": name})
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                mfr_id = results[0]["id"]
                self._manufacturer_cache[name] = mfr_id
                return mfr_id

        # Create new manufacturer
        slug = name.lower().replace(" ", "-").replace("_", "-")
        response = await client.post("/api/dcim/manufacturers/", json={
            "name": name,
            "slug": slug
        })

        if response.status_code == 201:
            mfr_id = response.json()["id"]
            self._manufacturer_cache[name] = mfr_id
            logger.info(f"Created NetBox manufacturer: {name} (ID: {mfr_id})")
            return mfr_id
        else:
            raise Exception(f"Failed to create manufacturer '{name}': {response.text}")

    async def _get_or_create_device_type(self, model: str, manufacturer_name: str) -> int:
        """Get device type ID by model, create if doesn't exist"""
        cache_key = f"{manufacturer_name}:{model}"
        if cache_key in self._type_cache:
            return self._type_cache[cache_key]

        client = await self._get_client()
        manufacturer_id = await self._get_or_create_manufacturer(manufacturer_name)

        # Search for existing device type
        response = await client.get("/api/dcim/device-types/", params={
            "model": model,
            "manufacturer_id": manufacturer_id
        })
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                type_id = results[0]["id"]
                self._type_cache[cache_key] = type_id
                return type_id

        # Create new device type
        slug = model.lower().replace(" ", "-").replace("_", "-")
        response = await client.post("/api/dcim/device-types/", json={
            "model": model,
            "slug": slug,
            "manufacturer": manufacturer_id,
            "u_height": 1
        })

        if response.status_code == 201:
            type_id = response.json()["id"]
            self._type_cache[cache_key] = type_id
            logger.info(f"Created NetBox device type: {model} (ID: {type_id})")
            return type_id
        else:
            raise Exception(f"Failed to create device type '{model}': {response.text}")

    async def _get_or_create_device_role(self, name: str) -> int:
        """Get device role ID by name, create if doesn't exist"""
        if name in self._role_cache:
            return self._role_cache[name]

        client = await self._get_client()

        # Search for existing role
        response = await client.get("/api/dcim/device-roles/", params={"name": name})
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                role_id = results[0]["id"]
                self._role_cache[name] = role_id
                return role_id

        # Create new role
        slug = name.lower().replace(" ", "-").replace("_", "-")
        response = await client.post("/api/dcim/device-roles/", json={
            "name": name,
            "slug": slug,
            "color": "4caf50"  # Green color
        })

        if response.status_code == 201:
            role_id = response.json()["id"]
            self._role_cache[name] = role_id
            logger.info(f"Created NetBox device role: {name} (ID: {role_id})")
            return role_id
        else:
            raise Exception(f"Failed to create device role '{name}': {response.text}")

    async def _get_or_create_platform(self, name: str) -> Optional[int]:
        """Get platform ID by name, create if doesn't exist"""
        if not name:
            return None

        if name in self._platform_cache:
            return self._platform_cache[name]

        client = await self._get_client()

        # Search for existing platform
        response = await client.get("/api/dcim/platforms/", params={"name": name})
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                platform_id = results[0]["id"]
                self._platform_cache[name] = platform_id
                return platform_id

        # Create new platform
        slug = name.lower().replace(" ", "-").replace("_", "-")
        response = await client.post("/api/dcim/platforms/", json={
            "name": name,
            "slug": slug
        })

        if response.status_code == 201:
            platform_id = response.json()["id"]
            self._platform_cache[name] = platform_id
            logger.info(f"Created NetBox platform: {name} (ID: {platform_id})")
            return platform_id
        else:
            logger.warning(f"Failed to create platform '{name}': {response.text}")
            return None

    async def get_device(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get device by name

        Args:
            name: Device name

        Returns:
            Device data or None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/dcim/devices/", params={"name": name})

            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    return results[0]
            return None
        except Exception as e:
            logger.error(f"Error getting device {name}: {e}")
            return None

    async def get_interfaces(self, device_id: int) -> List[Dict[str, Any]]:
        """
        Get all interfaces for a device.

        Args:
            device_id: NetBox device ID

        Returns:
            List of interface dictionaries
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/dcim/interfaces/", params={
                "device_id": device_id,
                "limit": 1000
            })

            if response.status_code == 200:
                return response.json().get("results", [])
            return []
        except Exception as e:
            logger.error(f"Error getting interfaces for device {device_id}: {e}")
            return []

    async def register_device(self, device: DeviceInfo) -> Dict[str, Any]:
        """
        Register a device in NetBox

        Creates the device if it doesn't exist, or updates if it does.
        Also creates any required related objects (site, manufacturer, etc.)

        Args:
            device: Device information

        Returns:
            Dict with registration result
        """
        try:
            client = await self._get_client()

            # Resolve IDs for related objects
            site_id = await self._get_or_create_site(device.site)
            device_type_id = await self._get_or_create_device_type(device.device_type, device.manufacturer)
            role_id = await self._get_or_create_device_role(device.device_role)
            platform_id = await self._get_or_create_platform(device.platform)

            # Check if device already exists
            existing = await self.get_device(device.name)

            # Build device payload
            payload = {
                "name": device.name,
                "site": site_id,
                "device_type": device_type_id,
                "role": role_id,
                "status": device.status.value
            }

            if platform_id:
                payload["platform"] = platform_id
            if device.serial:
                payload["serial"] = device.serial
            if device.comments:
                payload["comments"] = device.comments
            if device.custom_fields:
                payload["custom_fields"] = device.custom_fields

            if existing:
                # Update existing device
                device_id = existing["id"]
                response = await client.patch(f"/api/dcim/devices/{device_id}/", json=payload)
                action = "updated"
            else:
                # Create new device
                response = await client.post("/api/dcim/devices/", json=payload)
                action = "created"

            if response.status_code in (200, 201):
                result = response.json()
                logger.info(f"Device {action} in NetBox: {device.name} (ID: {result['id']})")
                return {
                    "success": True,
                    "action": action,
                    "device_id": result["id"],
                    "device_name": device.name,
                    "device_url": f"{self.base_url}/dcim/devices/{result['id']}/"
                }
            else:
                error_msg = response.text
                logger.error(f"Failed to register device: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "device_name": device.name
                }

        except Exception as e:
            logger.error(f"Error registering device {device.name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "device_name": device.name
            }

    async def register_interface(self, device_name: str, interface_name: str,
                                  interface_type: str = "virtual",
                                  mac_address: Optional[str] = None,
                                  enabled: bool = True,
                                  description: Optional[str] = None) -> Dict[str, Any]:
        """
        Register an interface on a device

        Args:
            device_name: Name of the device
            interface_name: Interface name (e.g., eth0, GigabitEthernet0/0)
            interface_type: Interface type (virtual, 1000base-t, etc.)
            mac_address: Optional MAC address
            enabled: Whether interface is enabled
            description: Optional description

        Returns:
            Dict with registration result
        """
        try:
            client = await self._get_client()

            # Get device
            device = await self.get_device(device_name)
            if not device:
                return {"success": False, "error": f"Device not found: {device_name}"}

            device_id = device["id"]

            # Check if interface exists
            response = await client.get("/api/dcim/interfaces/", params={
                "device_id": device_id,
                "name": interface_name
            })

            existing = None
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    existing = results[0]

            payload = {
                "device": device_id,
                "name": interface_name,
                "type": interface_type,
                "enabled": enabled
            }

            if mac_address:
                payload["mac_address"] = mac_address
            if description:
                payload["description"] = description

            if existing:
                response = await client.patch(f"/api/dcim/interfaces/{existing['id']}/", json=payload)
                action = "updated"
            else:
                response = await client.post("/api/dcim/interfaces/", json=payload)
                action = "created"

            if response.status_code in (200, 201):
                result = response.json()
                return {
                    "success": True,
                    "action": action,
                    "interface_id": result["id"],
                    "interface_name": interface_name
                }
            else:
                return {
                    "success": False,
                    "error": response.text,
                    "interface_name": interface_name
                }

        except Exception as e:
            logger.error(f"Error registering interface: {e}")
            return {"success": False, "error": str(e)}

    async def register_ip_address(self, address: str, interface_id: Optional[int] = None,
                                   status: str = "active",
                                   description: Optional[str] = None) -> Dict[str, Any]:
        """
        Register an IP address in NetBox IPAM

        Args:
            address: IP address with prefix (e.g., "192.168.1.1/24")
            interface_id: Optional interface ID to assign to
            status: Address status (active, reserved, deprecated)
            description: Optional description

        Returns:
            Dict with registration result
        """
        try:
            client = await self._get_client()

            # Check if IP exists
            response = await client.get("/api/ipam/ip-addresses/", params={"address": address})

            existing = None
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    existing = results[0]

            if existing:
                # Check current assignment status
                existing_obj_id = existing.get("assigned_object_id")
                existing_obj_type = existing.get("assigned_object_type")
                ip_id = existing["id"]

                logger.info(f"[NetBox] IP {address} exists (ID: {ip_id}), current assignment: {existing_obj_type}:{existing_obj_id}")

                # Case 1: IP already assigned to target interface - just update status
                if interface_id and existing_obj_id == interface_id and existing_obj_type == "dcim.interface":
                    payload = {"status": status}
                    if description:
                        payload["description"] = description

                    response = await client.patch(f"/api/ipam/ip-addresses/{ip_id}/", json=payload)
                    if response.status_code in (200, 201):
                        return {
                            "success": True,
                            "action": "unchanged",
                            "ip_id": ip_id,
                            "address": address
                        }

                # Case 2: IP is unassigned (from our cleanup phase) - just assign it
                if existing_obj_id is None:
                    logger.info(f"[NetBox] IP {address} is unassigned, assigning to interface {interface_id}")
                    payload = {
                        "status": status,
                        "assigned_object_type": "dcim.interface",
                        "assigned_object_id": interface_id
                    }
                    if description:
                        payload["description"] = description

                    response = await client.patch(f"/api/ipam/ip-addresses/{ip_id}/", json=payload)
                    if response.status_code in (200, 201):
                        return {
                            "success": True,
                            "action": "reassigned",
                            "ip_id": ip_id,
                            "address": address
                        }

                # Case 3: IP is assigned elsewhere - need to unassign first, then reassign
                logger.warning(f"[NetBox] IP {address} is assigned elsewhere, attempting unassign then reassign...")

                # First, clear any primary IP designation that might reference this IP
                # Try to unassign the IP
                for unassign_payload in [
                    {"assigned_object_id": None, "assigned_object_type": None},
                    {"assigned_object_id": None},
                ]:
                    unassign_response = await client.patch(f"/api/ipam/ip-addresses/{ip_id}/", json=unassign_payload)
                    if unassign_response.status_code in (200, 201):
                        logger.info(f"[NetBox] Successfully unassigned IP {address}")
                        break

                # Now try to assign to the new interface
                payload = {
                    "address": address,
                    "status": status,
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": interface_id
                }
                if description:
                    payload["description"] = description

                response = await client.patch(f"/api/ipam/ip-addresses/{ip_id}/", json=payload)
                action = "updated"

                # If still failing, delete and recreate
                if response.status_code not in (200, 201):
                    logger.warning(f"[NetBox] Reassign failed for {address}, trying delete and recreate...")
                    del_response = await client.delete(f"/api/ipam/ip-addresses/{ip_id}/")
                    if del_response.status_code in (200, 204):
                        # Create fresh
                        response = await client.post("/api/ipam/ip-addresses/", json=payload)
                        action = "recreated"
            else:
                # Create new IP
                payload = {
                    "address": address,
                    "status": status
                }
                if interface_id:
                    payload["assigned_object_type"] = "dcim.interface"
                    payload["assigned_object_id"] = interface_id
                if description:
                    payload["description"] = description

                response = await client.post("/api/ipam/ip-addresses/", json=payload)
                action = "created"

            if response.status_code in (200, 201):
                result = response.json()
                return {
                    "success": True,
                    "action": action if not existing else "updated",
                    "ip_id": result["id"],
                    "address": address
                }
            else:
                return {
                    "success": False,
                    "error": response.text,
                    "address": address
                }

        except Exception as e:
            logger.error(f"Error registering IP address: {e}")
            return {"success": False, "error": str(e)}

    async def register_service(self, device_name: str, name: str,
                                protocol: str, port: int,
                                description: Optional[str] = None) -> Dict[str, Any]:
        """
        Register a service on a device (for protocols like BGP, OSPF)

        Args:
            device_name: Name of the device
            name: Service name (e.g., "BGP", "OSPF")
            protocol: Protocol (tcp, udp)
            port: Port number (0 for L2/L3 protocols)
            description: Optional description

        Returns:
            Dict with registration result
        """
        try:
            client = await self._get_client()

            # Get device
            device = await self.get_device(device_name)
            if not device:
                return {"success": False, "error": f"Device not found: {device_name}"}

            device_id = device["id"]

            # Check if service exists
            response = await client.get("/api/ipam/services/", params={
                "device_id": device_id,
                "name": name
            })

            existing = None
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    existing = results[0]

            # Build ports list (NetBox expects array)
            ports = [port] if port > 0 else []

            # NetBox 3.5+ requires parent_object_type and parent_object_id
            # instead of just "device"
            payload = {
                "parent_object_type": "dcim.device",
                "parent_object_id": device_id,
                "name": name,
                "protocol": protocol,
                "ports": ports
            }

            if description:
                payload["description"] = description

            if existing:
                response = await client.patch(f"/api/ipam/services/{existing['id']}/", json=payload)
                action = "updated"
            else:
                response = await client.post("/api/ipam/services/", json=payload)
                action = "created"

            if response.status_code in (200, 201):
                result = response.json()
                return {
                    "success": True,
                    "action": action,
                    "service_id": result["id"],
                    "service_name": name
                }
            else:
                return {
                    "success": False,
                    "error": response.text,
                    "service_name": name
                }

        except Exception as e:
            logger.error(f"Error registering service: {e}")
            return {"success": False, "error": str(e)}

    async def get_interface_id(self, device_name: str, interface_name: str) -> Optional[int]:
        """
        Get the NetBox interface ID for a device's interface.

        Args:
            device_name: Name of the device
            interface_name: Name of the interface

        Returns:
            Interface ID or None if not found
        """
        try:
            client = await self._get_client()

            # Get device first
            device = await self.get_device(device_name)
            if not device:
                return None

            # Get interface
            response = await client.get("/api/dcim/interfaces/", params={
                "device_id": device["id"],
                "name": interface_name
            })

            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    return results[0]["id"]

            return None

        except Exception as e:
            logger.error(f"Error getting interface ID: {e}")
            return None

    async def register_cable(self, a_device: str, a_interface: str,
                             b_device: str, b_interface: str,
                             status: str = "connected",
                             cable_type: str = "",
                             label: str = "") -> Dict[str, Any]:
        """
        Register a cable connection between two device interfaces in NetBox.

        Args:
            a_device: Name of first device
            a_interface: Name of interface on first device
            b_device: Name of second device
            b_interface: Name of interface on second device
            status: Cable status (connected, planned, decommissioning)
            cable_type: Optional cable type (cat6, fiber, etc.)
            label: Optional cable label

        Returns:
            Dict with registration result including cable_id
        """
        try:
            client = await self._get_client()

            # Get interface IDs for both ends
            a_iface_id = await self.get_interface_id(a_device, a_interface)
            b_iface_id = await self.get_interface_id(b_device, b_interface)

            if not a_iface_id:
                return {
                    "success": False,
                    "error": f"Interface not found: {a_device}:{a_interface}"
                }
            if not b_iface_id:
                return {
                    "success": False,
                    "error": f"Interface not found: {b_device}:{b_interface}"
                }

            # Check if cable already exists between these interfaces
            response = await client.get("/api/dcim/cables/", params={"limit": 1000})
            if response.status_code == 200:
                cables = response.json().get("results", [])
                for cable in cables:
                    a_terms = cable.get("a_terminations", [])
                    b_terms = cable.get("b_terminations", [])

                    # Check if this cable connects our interfaces
                    a_ids = [t.get("object_id") for t in a_terms if t.get("object_type") == "dcim.interface"]
                    b_ids = [t.get("object_id") for t in b_terms if t.get("object_type") == "dcim.interface"]

                    if (a_iface_id in a_ids and b_iface_id in b_ids) or \
                       (a_iface_id in b_ids and b_iface_id in a_ids):
                        # Cable already exists - build URL to NetBox cable
                        cable_url = f"{self.config.url.rstrip('/')}/dcim/cables/{cable['id']}/"
                        return {
                            "success": True,
                            "action": "exists",
                            "cable_id": cable["id"],
                            "url": cable_url,
                            "a_device": a_device,
                            "a_interface": a_interface,
                            "b_device": b_device,
                            "b_interface": b_interface,
                            "message": f"Cable already exists between {a_device}:{a_interface} and {b_device}:{b_interface}"
                        }

            # Create cable payload
            # NetBox 3.x+ uses terminations format
            payload = {
                "a_terminations": [
                    {
                        "object_type": "dcim.interface",
                        "object_id": a_iface_id
                    }
                ],
                "b_terminations": [
                    {
                        "object_type": "dcim.interface",
                        "object_id": b_iface_id
                    }
                ],
                "status": status
            }

            if cable_type:
                payload["type"] = cable_type
            if label:
                payload["label"] = label

            # Create the cable
            response = await client.post("/api/dcim/cables/", json=payload)

            if response.status_code in (200, 201):
                result = response.json()
                cable_url = f"{self.config.url.rstrip('/')}/dcim/cables/{result['id']}/"
                logger.info(f"Created cable {result['id']}: {a_device}:{a_interface} <-> {b_device}:{b_interface}")
                return {
                    "success": True,
                    "action": "created",
                    "cable_id": result["id"],
                    "url": cable_url,
                    "a_device": a_device,
                    "a_interface": a_interface,
                    "b_device": b_device,
                    "b_interface": b_interface
                }
            else:
                error_msg = response.text
                # Check for interface already connected errors
                if "already connected" in error_msg.lower() or "termination" in error_msg.lower():
                    logger.warning(f"Interface already connected, attempting to clear old cables...")
                    # Try to clear conflicting cables and retry
                    await self._delete_interface_cables(a_iface_id)
                    await self._delete_interface_cables(b_iface_id)

                    # Retry cable creation
                    retry_response = await client.post("/api/dcim/cables/", json=payload)
                    if retry_response.status_code in (200, 201):
                        result = retry_response.json()
                        cable_url = f"{self.config.url.rstrip('/')}/dcim/cables/{result['id']}/"
                        logger.info(f"Created cable after clearing conflicts: {result['id']}")
                        return {
                            "success": True,
                            "action": "created_after_cleanup",
                            "cable_id": result["id"],
                            "url": cable_url,
                            "a_device": a_device,
                            "a_interface": a_interface,
                            "b_device": b_device,
                            "b_interface": b_interface
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"Failed to create cable after cleanup: {retry_response.text}"
                        }

                return {
                    "success": False,
                    "error": f"Failed to create cable: {error_msg}"
                }

        except Exception as e:
            logger.error(f"Error registering cable: {e}")
            return {"success": False, "error": str(e)}

    async def register_topology_cables(self, links: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Register multiple cables from a topology links array.

        Args:
            links: List of link dicts with keys:
                   - agent1_id or source_device: First device name
                   - interface1 or source_interface: First interface name
                   - agent2_id or target_device: Second device name
                   - interface2 or target_interface: Second interface name

        Returns:
            Summary of cable registration results
        """
        results = {
            "total": len(links),
            "created": 0,
            "existing": 0,
            "failed": 0,
            "cables": [],
            "errors": []
        }

        for link in links:
            # Support both wizard format and topology format
            a_device = link.get("source_device") or link.get("agent1_id") or link.get("a_device")
            a_interface = link.get("source_interface") or link.get("interface1") or link.get("a_interface")
            b_device = link.get("target_device") or link.get("agent2_id") or link.get("b_device")
            b_interface = link.get("target_interface") or link.get("interface2") or link.get("b_interface")

            if not all([a_device, a_interface, b_device, b_interface]):
                results["failed"] += 1
                results["errors"].append(f"Invalid link data: {link}")
                continue

            # Strip netbox- prefix from agent IDs if present (wizard adds this)
            if a_device.startswith("netbox-"):
                a_device = a_device.replace("netbox-", "").replace("-", " ").title()
            if b_device.startswith("netbox-"):
                b_device = b_device.replace("netbox-", "").replace("-", " ").title()

            cable_result = await self.register_cable(
                a_device=a_device,
                a_interface=a_interface,
                b_device=b_device,
                b_interface=b_interface,
                status=link.get("status", "connected"),
                label=link.get("label", "")
            )

            if cable_result.get("success"):
                if cable_result.get("action") == "exists":
                    results["existing"] += 1
                else:
                    results["created"] += 1
                results["cables"].append(cable_result)
            else:
                results["failed"] += 1
                results["errors"].append(f"{a_device}:{a_interface} <-> {b_device}:{b_interface}: {cable_result.get('error')}")

        return results

    async def _set_primary_ip(self, device_name: str, ip_id: int) -> bool:
        """
        Set the primary IPv4 address on a device

        Args:
            device_name: Device name
            ip_id: IP address ID to set as primary

        Returns:
            True if successful
        """
        try:
            client = await self._get_client()

            device = await self.get_device(device_name)
            if not device:
                return False

            device_id = device["id"]

            response = await client.patch(f"/api/dcim/devices/{device_id}/", json={
                "primary_ip4": ip_id
            })

            return response.status_code == 200

        except Exception as e:
            logger.error(f"Error setting primary IP: {e}")
            return False

    async def _clear_primary_ip(self, device_id: int) -> bool:
        """
        Clear all primary IP addresses from a device to allow IP reassignment.

        Args:
            device_id: Device ID

        Returns:
            True if successful
        """
        try:
            client = await self._get_client()
            # Clear both primary_ip4 and primary_ip6 in one request
            response = await client.patch(f"/api/dcim/devices/{device_id}/", json={
                "primary_ip4": None,
                "primary_ip6": None
            })
            if response.status_code == 200:
                logger.info(f"Cleared primary_ip4 and primary_ip6 from device {device_id}")
                return True
            else:
                logger.warning(f"Failed to clear primary IPs: {response.text}")
                # Try clearing them individually
                await client.patch(f"/api/dcim/devices/{device_id}/", json={"primary_ip4": None})
                await client.patch(f"/api/dcim/devices/{device_id}/", json={"primary_ip6": None})
                return True
        except Exception as e:
            logger.error(f"Error clearing primary IP: {e}")
            return False

    async def _delete_device_ips(self, device_id: int, keep_addresses: List[str] = None) -> int:
        """
        Delete IP addresses assigned to a device, optionally keeping specified ones.

        This method uses multiple approaches to ensure IPs are removed:
        1. First unassign from interface
        2. Then delete
        3. If delete fails, mark as deprecated

        Args:
            device_id: Device ID
            keep_addresses: List of IP addresses (with CIDR) to keep

        Returns:
            Number of IPs deleted/handled
        """
        keep_addresses = keep_addresses or []
        # Normalize keep addresses (strip whitespace, ensure format)
        keep_set = set()
        for addr in keep_addresses:
            if addr:
                # Normalize to just the base address for comparison
                base = addr.split('/')[0].strip()
                keep_set.add(base)

        deleted = 0
        try:
            client = await self._get_client()
            response = await client.get("/api/ipam/ip-addresses/", params={
                "device_id": device_id,
                "limit": 1000
            })

            if response.status_code == 200:
                ips = response.json().get("results", [])
                logger.info(f"[NetBox] Found {len(ips)} IPs to process for device {device_id}")

                for ip in ips:
                    ip_addr = ip.get("address", "")
                    ip_id = ip.get("id")
                    base_addr = ip_addr.split('/')[0].strip()

                    # Skip if this IP should be kept
                    if base_addr in keep_set:
                        logger.debug(f"Keeping IP {ip_addr}")
                        continue

                    logger.info(f"[NetBox] Processing IP {ip_addr} (ID: {ip_id}) for removal...")

                    # Step 1: Unassign the IP from its interface first
                    # Try multiple approaches
                    unassign_success = False
                    for attempt, payload in enumerate([
                        {"assigned_object_id": None, "assigned_object_type": None},
                        {"assigned_object_id": None},
                        {"assigned_object_type": None, "assigned_object_id": None, "status": "deprecated"},
                    ]):
                        try:
                            unassign_response = await client.patch(
                                f"/api/ipam/ip-addresses/{ip_id}/",
                                json=payload
                            )
                            if unassign_response.status_code in (200, 201):
                                logger.info(f"[NetBox] Unassigned IP {ip_addr} (attempt {attempt+1})")
                                unassign_success = True
                                break
                            else:
                                logger.debug(f"[NetBox] Unassign attempt {attempt+1} failed: {unassign_response.text}")
                        except Exception as e:
                            logger.debug(f"[NetBox] Unassign attempt {attempt+1} error: {e}")

                    # Step 2: Now delete the IP
                    del_response = await client.delete(f"/api/ipam/ip-addresses/{ip_id}/")
                    if del_response.status_code in (204, 200):
                        logger.info(f"[NetBox] Deleted IP: {ip_addr}")
                        deleted += 1
                    else:
                        logger.warning(f"[NetBox] Failed to delete IP {ip_addr}: {del_response.text}")

                        # Step 3: If delete fails but unassign succeeded, change description to mark for cleanup
                        if unassign_success:
                            await client.patch(
                                f"/api/ipam/ip-addresses/{ip_id}/",
                                json={"description": "[AUTO-CLEANUP] Unassigned by ASI update", "status": "deprecated"}
                            )
                            logger.info(f"[NetBox] Marked IP {ip_addr} as deprecated (will be recreated)")
                            deleted += 1  # Count as handled since it's unassigned

            return deleted
        except Exception as e:
            logger.error(f"Error deleting device IPs: {e}")
            import traceback
            traceback.print_exc()
            return deleted

    async def _delete_interface_cables(self, interface_id: int) -> int:
        """
        Delete all cables connected to an interface.

        Args:
            interface_id: Interface ID

        Returns:
            Number of cables deleted
        """
        deleted = 0
        try:
            client = await self._get_client()

            # Find cables connected to this interface
            response = await client.get("/api/dcim/cables/", params={"limit": 1000})
            if response.status_code == 200:
                cables = response.json().get("results", [])
                for cable in cables:
                    a_terms = cable.get("a_terminations", [])
                    b_terms = cable.get("b_terminations", [])

                    # Check if this interface is connected
                    connected = False
                    for term in a_terms + b_terms:
                        if term.get("object_type") == "dcim.interface" and term.get("object_id") == interface_id:
                            connected = True
                            break

                    if connected:
                        del_response = await client.delete(f"/api/dcim/cables/{cable['id']}/")
                        if del_response.status_code in (204, 200):
                            logger.info(f"Deleted cable {cable['id']} from interface {interface_id}")
                            deleted += 1
                        else:
                            logger.warning(f"Failed to delete cable {cable['id']}: {del_response.text}")

            return deleted
        except Exception as e:
            logger.error(f"Error deleting interface cables: {e}")
            return deleted

    async def _delete_device_interfaces(self, device_id: int, keep_names: List[str] = None) -> int:
        """
        Delete interfaces from a device, optionally keeping specified ones.

        Args:
            device_id: Device ID
            keep_names: List of interface names to keep

        Returns:
            Number of interfaces deleted
        """
        keep_names = keep_names or []
        keep_set = set(n.lower() for n in keep_names)
        deleted = 0

        try:
            client = await self._get_client()
            response = await client.get("/api/dcim/interfaces/", params={
                "device_id": device_id,
                "limit": 1000
            })

            if response.status_code == 200:
                interfaces = response.json().get("results", [])
                for iface in interfaces:
                    iface_name = iface.get("name", "")
                    if iface_name.lower() in keep_set:
                        logger.debug(f"Keeping interface {iface_name}")
                        continue

                    # First delete any cables attached to this interface
                    await self._delete_interface_cables(iface["id"])

                    # Then delete the interface
                    del_response = await client.delete(f"/api/dcim/interfaces/{iface['id']}/")
                    if del_response.status_code in (204, 200):
                        logger.info(f"Deleted stale interface: {iface_name}")
                        deleted += 1
                    else:
                        logger.warning(f"Failed to delete interface {iface_name}: {del_response.text}")

            return deleted
        except Exception as e:
            logger.error(f"Error deleting device interfaces: {e}")
            return deleted

    async def _delete_device_services(self, device_id: int, keep_names: List[str] = None) -> int:
        """
        Delete services from a device, optionally keeping specified ones.

        Args:
            device_id: Device ID
            keep_names: List of service names to keep

        Returns:
            Number of services deleted
        """
        keep_names = keep_names or []
        keep_set = set(n.lower() for n in keep_names)
        deleted = 0

        try:
            client = await self._get_client()
            response = await client.get("/api/ipam/services/", params={
                "device_id": device_id,
                "limit": 1000
            })

            if response.status_code == 200:
                services = response.json().get("results", [])
                for svc in services:
                    svc_name = svc.get("name", "")
                    if svc_name.lower() in keep_set:
                        logger.debug(f"Keeping service {svc_name}")
                        continue

                    del_response = await client.delete(f"/api/ipam/services/{svc['id']}/")
                    if del_response.status_code in (204, 200):
                        logger.info(f"Deleted stale service: {svc_name}")
                        deleted += 1
                    else:
                        logger.warning(f"Failed to delete service {svc_name}: {del_response.text}")

            return deleted
        except Exception as e:
            logger.error(f"Error deleting device services: {e}")
            return deleted

    async def prepare_device_for_update(self, device_name: str,
                                         new_interfaces: List[str] = None,
                                         new_ips: List[str] = None,
                                         new_services: List[str] = None) -> Dict[str, Any]:
        """
        Prepare an existing device for update by clearing conflicts.

        This method:
        1. Clears primary_ip4 to allow IP reassignment
        2. Deletes stale IPs not in the new config
        3. Deletes stale interfaces not in the new config
        4. Deletes stale services not in the new config
        5. Deletes cables on interfaces that will be modified

        Args:
            device_name: Device name
            new_interfaces: List of interface names that will exist after update
            new_ips: List of IP addresses (with CIDR) that will exist after update
            new_services: List of service names that will exist after update

        Returns:
            Summary of cleanup operations
        """
        result = {
            "success": True,
            "device_name": device_name,
            "primary_ip_cleared": False,
            "ips_deleted": 0,
            "interfaces_deleted": 0,
            "services_deleted": 0,
            "cables_deleted": 0,
            "errors": []
        }

        try:
            device = await self.get_device(device_name)
            if not device:
                return {"success": True, "device_name": device_name, "message": "Device does not exist, no cleanup needed"}

            device_id = device["id"]
            logger.info(f"[NetBox] Preparing device '{device_name}' (ID: {device_id}) for update")

            # 1. Clear primary IP first (this is critical!)
            if device.get("primary_ip4"):
                if await self._clear_primary_ip(device_id):
                    result["primary_ip_cleared"] = True
                    logger.info(f"[NetBox] Cleared primary_ip4 from {device_name}")

            # 2. Delete cables on interfaces that will be updated
            # (We need to clear cables before we can properly update interfaces)
            interfaces = await self.get_interfaces(device_id)
            for iface in interfaces:
                iface_id = iface.get("id")
                if iface.get("cable"):
                    cables_deleted = await self._delete_interface_cables(iface_id)
                    result["cables_deleted"] += cables_deleted

            # 3. Delete ALL IPs (not just stale ones) - they will be recreated fresh
            # This avoids "Cannot reassign IP while designated as primary" errors
            result["ips_deleted"] = await self._delete_device_ips(device_id, keep_addresses=[])

            # 4. Delete stale interfaces
            result["interfaces_deleted"] = await self._delete_device_interfaces(device_id, new_interfaces)

            # 5. Delete stale services
            result["services_deleted"] = await self._delete_device_services(device_id, new_services)

            logger.info(f"[NetBox] Device cleanup complete: {result}")
            return result

        except Exception as e:
            logger.error(f"Error preparing device for update: {e}")
            result["success"] = False
            result["errors"].append(str(e))
            return result

    async def list_sites(self) -> List[Dict[str, Any]]:
        """Get list of all sites"""
        try:
            client = await self._get_client()
            response = await client.get("/api/dcim/sites/", params={"limit": 1000})
            if response.status_code == 200:
                return response.json().get("results", [])
            return []
        except Exception as e:
            logger.error(f"Error listing sites: {e}")
            return []

    async def list_device_roles(self) -> List[Dict[str, Any]]:
        """Get list of all device roles"""
        try:
            client = await self._get_client()
            response = await client.get("/api/dcim/device-roles/", params={"limit": 1000})
            if response.status_code == 200:
                return response.json().get("results", [])
            return []
        except Exception as e:
            logger.error(f"Error listing device roles: {e}")
            return []

    async def list_manufacturers(self) -> List[Dict[str, Any]]:
        """Get list of all manufacturers"""
        try:
            client = await self._get_client()
            response = await client.get("/api/dcim/manufacturers/", params={"limit": 1000})
            if response.status_code == 200:
                return response.json().get("results", [])
            return []
        except Exception as e:
            logger.error(f"Error listing manufacturers: {e}")
            return []

    async def list_devices(self, site: Optional[str] = None,
                           role: Optional[str] = None,
                           status: str = "active") -> List[Dict[str, Any]]:
        """
        Get list of devices from NetBox

        Args:
            site: Optional site name/slug filter
            role: Optional role name/slug filter
            status: Device status filter (default: active)

        Returns:
            List of device dictionaries
        """
        try:
            client = await self._get_client()
            params = {"limit": 1000, "status": status}
            if site:
                params["site"] = site
            if role:
                params["role"] = role

            response = await client.get("/api/dcim/devices/", params=params)
            if response.status_code == 200:
                return response.json().get("results", [])
            return []
        except Exception as e:
            logger.error(f"Error listing devices: {e}")
            return []

    async def get_device_full(self, device_id: int) -> Optional[Dict[str, Any]]:
        """
        Get full device details including interfaces and IPs

        Args:
            device_id: NetBox device ID

        Returns:
            Device dictionary with interfaces and IPs
        """
        try:
            client = await self._get_client()

            # Get device
            response = await client.get(f"/api/dcim/devices/{device_id}/")
            if response.status_code != 200:
                return None
            device = response.json()

            # Get interfaces
            response = await client.get("/api/dcim/interfaces/",
                                        params={"device_id": device_id, "limit": 100})
            interfaces = []
            if response.status_code == 200:
                interfaces = response.json().get("results", [])

            # Get IP addresses for each interface
            for iface in interfaces:
                response = await client.get("/api/ipam/ip-addresses/",
                                           params={"interface_id": iface["id"]})
                if response.status_code == 200:
                    iface["ip_addresses"] = response.json().get("results", [])
                else:
                    iface["ip_addresses"] = []

            device["interfaces"] = interfaces

            # Get primary IPs
            if device.get("primary_ip4"):
                device["primary_ipv4"] = device["primary_ip4"].get("address", "").split("/")[0]
            if device.get("primary_ip6"):
                device["primary_ipv6"] = device["primary_ip6"].get("address", "").split("/")[0]

            return device

        except Exception as e:
            logger.error(f"Error getting device {device_id}: {e}")
            return None

    async def import_device_as_agent_config(self, device_id: int) -> Dict[str, Any]:
        """
        Import a NetBox device and convert to agent configuration

        Args:
            device_id: NetBox device ID

        Returns:
            Agent configuration dictionary ready for the wizard
        """
        device = await self.get_device_full(device_id)
        if not device:
            return {"error": f"Device {device_id} not found"}

        # Map NetBox device to agent config
        # Use (x or {}) pattern because device.get("key", {}) returns None if key exists with None value
        agent_config = {
            "name": device.get("name", ""),
            "router_id": device.get("primary_ipv4") or self._extract_loopback_ip(device),
            "site": (device.get("site") or {}).get("name", ""),
            "role": (device.get("role") or {}).get("name", "Router"),
            "manufacturer": ((device.get("device_type") or {}).get("manufacturer") or {}).get("name", ""),
            "device_type": (device.get("device_type") or {}).get("model", ""),
            "platform": (device.get("platform") or {}).get("name", ""),
            "serial": device.get("serial", ""),
            "status": (device.get("status") or {}).get("value", "active"),
            "netbox_id": device.get("id"),
            "netbox_url": f"{self.base_url}/dcim/devices/{device.get('id')}/",

            # Interfaces
            "interfaces": [],

            # Custom fields from NetBox
            "custom_fields": device.get("custom_fields", {}),

            # Comments/description
            "description": device.get("comments", ""),
        }

        # Process interfaces
        for iface in device.get("interfaces", []):
            iface_config = {
                "name": iface.get("name", ""),
                "type": self._map_interface_type((iface.get("type") or {}).get("value", "")),
                "enabled": iface.get("enabled", True),
                "mac_address": iface.get("mac_address") or "",
                "mtu": iface.get("mtu"),
                "description": iface.get("description") or "",
                "ip_addresses": []
            }

            # Add IP addresses
            for ip in iface.get("ip_addresses", []):
                iface_config["ip_addresses"].append({
                    "address": ip.get("address", ""),
                    "status": (ip.get("status") or {}).get("value", "active"),
                    "primary": ip.get("id") == (device.get("primary_ip4") or {}).get("id") or
                              ip.get("id") == (device.get("primary_ip6") or {}).get("id")
                })

            agent_config["interfaces"].append(iface_config)

        # Try to determine protocols from device role/tags
        agent_config["protocols"] = self._suggest_protocols(device)

        return agent_config

    def _extract_loopback_ip(self, device: Dict) -> str:
        """Extract loopback IP from device interfaces"""
        for iface in device.get("interfaces", []):
            name = iface.get("name", "").lower()
            if "loopback" in name or name.startswith("lo"):
                for ip in iface.get("ip_addresses", []):
                    addr = ip.get("address", "").split("/")[0]
                    if addr and ":" not in addr:  # Prefer IPv4
                        return addr
        return ""

    def _map_interface_type(self, netbox_type: str) -> str:
        """Map NetBox interface type to agent interface type"""
        type_map = {
            "virtual": "virtual",
            "bridge": "bridge",
            "lag": "bond",
            "100base-tx": "ethernet",
            "1000base-t": "ethernet",
            "10gbase-t": "ethernet",
            "25gbase-x-sfp28": "ethernet",
            "40gbase-x-qsfpp": "ethernet",
            "100gbase-x-qsfp28": "ethernet",
        }
        return type_map.get(netbox_type, "ethernet")

    def _suggest_protocols(self, device: Dict) -> List[Dict[str, Any]]:
        """Suggest protocols based on device role and tags"""
        protocols = []
        role = (device.get("role") or {}).get("name", "").lower()
        tags = [(t.get("name") or "").lower() for t in (device.get("tags") or [])]

        # OSPF for most routers
        if "router" in role or "ospf" in tags:
            protocols.append({
                "type": "ospf",
                "area": "0.0.0.0",
                "enabled": True
            })

        # BGP for core/edge routers
        if "core" in role or "edge" in role or "bgp" in tags:
            protocols.append({
                "type": "bgp",
                "enabled": True
            })

        # IS-IS if tagged
        if "isis" in tags:
            protocols.append({
                "type": "isis",
                "enabled": True
            })

        return protocols

    async def get_site_devices(self, site_name: str) -> List[Dict[str, Any]]:
        """
        Get all devices in a site.

        Args:
            site_name: Name of the site

        Returns:
            List of device dictionaries with full details
        """
        try:
            client = await self._get_client()

            # First, get the site ID by name (NetBox API requires site_id or slug, not name)
            site_response = await client.get(
                "/api/dcim/sites/",
                params={"name": site_name}
            )
            if site_response.status_code != 200:
                logger.error(f"Failed to look up site {site_name}: {site_response.status_code}")
                return []

            sites = site_response.json().get("results", [])
            if not sites:
                logger.error(f"Site '{site_name}' not found in NetBox")
                return []

            site_id = sites[0]["id"]
            logger.info(f"Found site '{site_name}' with ID {site_id}")

            # Now get devices using site_id
            response = await client.get(
                "/api/dcim/devices/",
                params={"site_id": site_id, "limit": 500}
            )

            if response.status_code != 200:
                logger.error(f"Failed to get devices for site {site_name}: {response.status_code}")
                return []

            devices = response.json().get("results", [])
            logger.info(f"Found {len(devices)} devices in site {site_name}")
            return devices

        except Exception as e:
            logger.error(f"Error getting site devices: {e}")
            return []

    async def get_site_cables(self, site_name: str) -> List[Dict[str, Any]]:
        """
        Get all cables connecting devices in a site.

        Args:
            site_name: Name of the site

        Returns:
            List of cable connections with endpoint details
        """
        try:
            client = await self._get_client()

            # First, get the site ID by name
            site_response = await client.get(
                "/api/dcim/sites/",
                params={"name": site_name}
            )
            if site_response.status_code != 200:
                logger.error(f"Failed to look up site {site_name}: {site_response.status_code}")
                return []

            sites = site_response.json().get("results", [])
            if not sites:
                logger.error(f"Site '{site_name}' not found in NetBox")
                return []

            site_id = sites[0]["id"]

            # Get all devices in the site
            devices_response = await client.get(
                "/api/dcim/devices/",
                params={"site_id": site_id, "limit": 500}
            )
            if devices_response.status_code != 200:
                return []

            devices = devices_response.json().get("results", [])
            device_ids = {d["id"] for d in devices}
            device_names = {d["id"]: d["name"] for d in devices}

            # Get all cables
            cables_response = await client.get(
                "/api/dcim/cables/",
                params={"limit": 1000}
            )
            if cables_response.status_code != 200:
                return []

            all_cables = cables_response.json().get("results", [])

            # Filter cables to those connecting devices in our site
            site_cables = []
            for cable in all_cables:
                a_terms = cable.get("a_terminations", [])
                b_terms = cable.get("b_terminations", [])

                # Extract device IDs from terminations
                a_device_id = None
                b_device_id = None
                a_interface = None
                b_interface = None

                for term in a_terms:
                    if term.get("object_type") == "dcim.interface":
                        obj = term.get("object", {})
                        a_device_id = obj.get("device", {}).get("id")
                        a_interface = obj.get("name")

                for term in b_terms:
                    if term.get("object_type") == "dcim.interface":
                        obj = term.get("object", {})
                        b_device_id = obj.get("device", {}).get("id")
                        b_interface = obj.get("name")

                # Include if at least one end is in our site
                if a_device_id in device_ids or b_device_id in device_ids:
                    site_cables.append({
                        "cable_id": cable.get("id"),
                        "status": cable.get("status", {}).get("value", "connected"),
                        "type": cable.get("type", ""),
                        "a_device_id": a_device_id,
                        "a_device_name": device_names.get(a_device_id, "external"),
                        "a_interface": a_interface,
                        "b_device_id": b_device_id,
                        "b_device_name": device_names.get(b_device_id, "external"),
                        "b_interface": b_interface,
                        "label": cable.get("label", ""),
                        "description": cable.get("description", "")
                    })

            return site_cables

        except Exception as e:
            logger.error(f"Error getting site cables: {e}")
            return []

    async def get_site_topology(self, site_name: str) -> Dict[str, Any]:
        """
        Get complete site topology including devices and their interconnections.

        This provides everything needed to reconstruct the network in the wizard:
        - All devices with full config
        - All cables/links between devices
        - Interface-to-interface mappings

        Args:
            site_name: Name of the site

        Returns:
            Complete topology data structure
        """
        try:
            # 1. Get all devices in the site with full details
            devices = await self.get_site_devices(site_name)

            # 2. Get all cables connecting devices
            cables = await self.get_site_cables(site_name)

            # 3. Build device configs
            device_configs = []
            for device in devices:
                config = await self.import_device_as_agent_config(device["id"])
                if not config.get("error"):
                    device_configs.append(config)

            # 4. Build links/connections list for topology
            links = []
            for cable in cables:
                if cable["a_device_name"] and cable["b_device_name"]:
                    links.append({
                        "source_device": cable["a_device_name"],
                        "source_interface": cable["a_interface"],
                        "target_device": cable["b_device_name"],
                        "target_interface": cable["b_interface"],
                        "cable_id": cable["cable_id"],
                        "status": cable["status"],
                        "label": cable["label"]
                    })

            # 5. Build neighbor map (which device connects to which)
            neighbors = {}
            for link in links:
                src = link["source_device"]
                tgt = link["target_device"]

                if src not in neighbors:
                    neighbors[src] = []
                if tgt not in neighbors:
                    neighbors[tgt] = []

                neighbors[src].append({
                    "neighbor": tgt,
                    "local_interface": link["source_interface"],
                    "remote_interface": link["target_interface"]
                })
                neighbors[tgt].append({
                    "neighbor": src,
                    "local_interface": link["target_interface"],
                    "remote_interface": link["source_interface"]
                })

            return {
                "site_name": site_name,
                "device_count": len(device_configs),
                "link_count": len(links),
                "devices": device_configs,
                "links": links,
                "neighbors": neighbors,
                "cables_raw": cables  # Raw cable data for debugging
            }

        except Exception as e:
            logger.error(f"Error getting site topology: {e}")
            return {
                "error": str(e),
                "site_name": site_name,
                "devices": [],
                "links": [],
                "neighbors": {}
            }

    async def get_interface_connections(self, device_id: int) -> List[Dict[str, Any]]:
        """
        Get all connections for a specific device's interfaces using cable traces.

        Args:
            device_id: NetBox device ID

        Returns:
            List of connections with local and remote endpoint details
        """
        connections = []
        try:
            client = await self._get_client()

            # Get device interfaces
            response = await client.get(
                "/api/dcim/interfaces/",
                params={"device_id": device_id, "limit": 100}
            )
            if response.status_code != 200:
                logger.warning(f"Failed to get interfaces for device {device_id}: {response.status_code}")
                return connections

            interfaces = response.json().get("results", [])
            logger.info(f"[NetBox] Found {len(interfaces)} interfaces for device {device_id}")

            # Count interfaces with cables
            interfaces_with_cables = [i for i in interfaces if i.get("cable")]
            logger.info(f"[NetBox] {len(interfaces_with_cables)} interfaces have cables attached")

            for iface in interfaces:
                # Check if interface has a cable
                cable_info = iface.get("cable")
                if cable_info:
                    logger.debug(f"[NetBox] Interface {iface.get('name')} has cable: {cable_info}")
                    # Get cable trace to find far end
                    trace_response = await client.get(
                        f"/api/dcim/interfaces/{iface['id']}/trace/"
                    )
                    if trace_response.status_code == 200:
                        trace = trace_response.json()
                        logger.debug(f"[NetBox] Trace for {iface.get('name')}: {trace}")
                        # Trace returns path segments, last segment has far end
                        if trace and len(trace) > 0:
                            # Each trace segment has near_end and far_end
                            for segment in trace:
                                far_end = segment.get("far_end")
                                if far_end and far_end.get("device"):
                                    conn = {
                                        "local_interface": iface.get("name"),
                                        "local_interface_id": iface.get("id"),
                                        "remote_device": far_end.get("device", {}).get("name"),
                                        "remote_device_id": far_end.get("device", {}).get("id"),
                                        "remote_interface": far_end.get("name"),
                                        "remote_interface_id": far_end.get("id"),
                                        "cable_id": cable_info.get("id") if isinstance(cable_info, dict) else cable_info
                                    }
                                    connections.append(conn)
                                    logger.info(f"[NetBox] Connection: {conn['local_interface']} -> {conn['remote_device']}:{conn['remote_interface']}")
                    else:
                        logger.warning(f"[NetBox] Trace failed for interface {iface.get('name')}: {trace_response.status_code}")

            logger.info(f"[NetBox] Total connections found: {len(connections)}")

        except Exception as e:
            logger.error(f"Error getting interface connections for device {device_id}: {e}")
            import traceback
            traceback.print_exc()

        return connections


def get_netbox_client() -> Optional[NetBoxClient]:
    """Get singleton NetBox client instance"""
    global _netbox_client
    return _netbox_client


def configure_netbox(config: NetBoxConfig) -> NetBoxClient:
    """
    Configure and return NetBox client

    Args:
        config: NetBox configuration

    Returns:
        Configured NetBox client
    """
    global _netbox_client
    _netbox_client = NetBoxClient(config)
    logger.info(f"NetBox client configured for {config.url}")
    return _netbox_client


async def auto_register_agent(agent_name: str, agent_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Auto-register an agent as a device in NetBox with full configuration.

    Creates:
    1. Device (with minimal required fields)
    2. All interfaces from agent config
    3. IP addresses assigned to interfaces
    4. Services for protocols (BGP, OSPF, etc.)
    5. Sets primary IP on device

    Args:
        agent_name: Name of the agent/device
        agent_config: Agent configuration dictionary

    Returns:
        Registration result with details
    """
    client = get_netbox_client()
    if not client:
        return {"success": False, "error": "NetBox client not configured"}

    if not client.config.auto_register:
        return {"success": False, "error": "Auto-registration is disabled"}

    if not client.config.site_name:
        return {"success": False, "error": "Site name is required for registration"}

    results = {
        "device": None,
        "interfaces": [],
        "ip_addresses": [],
        "services": [],
        "errors": []
    }

    # Determine device role from agent protocols
    protocols = agent_config.get("protocols", [])
    device_role = "Router"  # Default
    for proto in protocols:
        proto_type = proto.get("type", proto.get("t", "")).lower()
        if proto_type in ["bgp", "ospf", "ospfv3", "isis"]:
            device_role = "Router"
            break
        elif proto_type == "mpls":
            device_role = "Router"

    # Build device info - using Agentic as manufacturer
    device = DeviceInfo(
        name=agent_name,
        site=client.config.site_name,
        device_role=device_role,
        device_type="ASI Agent",
        manufacturer="Agentic",
        platform="ASI",
        status=DeviceStatus.ACTIVE,
        comments=f"ASI Network Agent\nRouter ID: {agent_config.get('router_id', 'N/A')}\nAuto-registered by NetBox MCP"
    )

    # Check if device already exists - if so, prepare for update by cleaning conflicts
    existing_device = await client.get_device(agent_name)
    if existing_device:
        logger.info(f"[NetBox] Device '{agent_name}' already exists (ID: {existing_device['id']}), preparing for update...")

        # Extract new interface names from config
        interfaces = agent_config.get("interfaces", [])
        new_interface_names = []
        new_ip_addresses = []
        for iface in interfaces:
            iface_name = iface.get("name", iface.get("n", ""))
            if iface_name:
                new_interface_names.append(iface_name)
            ip_addr = iface.get("ip", iface.get("ip_address", ""))
            if ip_addr:
                # Ensure CIDR format for comparison
                if "/" not in ip_addr:
                    ip_addr = f"{ip_addr}/24"
                new_ip_addresses.append(ip_addr)

        # Extract new service names from protocols
        new_service_names = []
        for proto in protocols:
            proto_type = proto.get("type", proto.get("t", "")).lower()
            if proto_type == "bgp":
                new_service_names.append("BGP")
            elif proto_type in ["ospf", "ospfv2"]:
                new_service_names.append("OSPF")
            elif proto_type == "ospfv3":
                new_service_names.append("OSPFv3")
            elif proto_type == "isis":
                new_service_names.append("IS-IS")
            elif proto_type == "ldp":
                new_service_names.append("LDP")
            elif proto_type == "mpls":
                new_service_names.append("MPLS")

        # Prepare device for update - this clears primary IP, deletes stale objects
        cleanup_result = await client.prepare_device_for_update(
            device_name=agent_name,
            new_interfaces=new_interface_names,
            new_ips=new_ip_addresses,
            new_services=new_service_names
        )
        logger.info(f"[NetBox] Device cleanup result: {cleanup_result}")

        if not cleanup_result.get("success"):
            results["errors"].append(f"Failed to prepare device for update: {cleanup_result.get('errors', [])}")

    # 1. Register the device (will update if exists)
    device_result = await client.register_device(device)
    results["device"] = device_result

    if not device_result.get("success"):
        results["errors"].append(f"Device creation failed: {device_result.get('error')}")
        return {"success": False, **results}

    # 2. Register all interfaces
    interfaces = agent_config.get("interfaces", [])
    logger.info(f"[NetBox] Registering {len(interfaces)} interfaces for {agent_name}")
    primary_ip_id = None
    primary_interface_id = None

    for iface in interfaces:
        iface_name = iface.get("name", iface.get("n", ""))
        iface_ip = iface.get("ip", iface.get("ip_address", ""))
        logger.info(f"[NetBox] Processing interface: name={iface_name}, ip={iface_ip}")
        if not iface_name:
            logger.warning(f"[NetBox] Skipping interface with no name: {iface}")
            continue

        # Map interface type
        iface_type = iface.get("type", iface.get("t", "ethernet"))
        netbox_type = _map_agent_interface_type(iface_type)

        iface_result = await client.register_interface(
            device_name=agent_name,
            interface_name=iface_name,
            interface_type=netbox_type,
            mac_address=iface.get("mac", iface.get("mac_address")),
            enabled=iface.get("enabled", iface.get("e", True)),
            description=iface.get("description", "")
        )
        results["interfaces"].append(iface_result)

        if not iface_result.get("success"):
            results["errors"].append(f"Interface {iface_name}: {iface_result.get('error')}")
            continue

        # 3. Register IP addresses for this interface
        ip_addr = iface.get("ip", iface.get("ip_address", ""))
        if ip_addr:
            # Ensure CIDR format
            if "/" not in ip_addr:
                ip_addr = f"{ip_addr}/24"  # Default to /24 if no prefix

            # Check if this is a loopback interface
            is_loopback = "lo" in iface_name.lower() or "loopback" in iface_name.lower()

            # Build rich self-description for loopback (agent identity)
            if is_loopback:
                # Build protocol summary
                proto_names = []
                for p in protocols:
                    ptype = p.get("type", p.get("t", "")).upper()
                    if ptype:
                        # Add details for key protocols
                        if "bgp" in ptype.lower():
                            asn = p.get("local_as", p.get("asn", ""))
                            proto_names.append(f"BGP AS{asn}" if asn else "BGP")
                        elif "ospf" in ptype.lower():
                            area = p.get("area", "0")
                            proto_names.append(f"OSPF Area {area}")
                        else:
                            proto_names.append(ptype)

                proto_str = ", ".join(proto_names) if proto_names else "No protocols"
                router_id = agent_config.get("router_id", "N/A")

                ip_description = f"ASI Agent: {agent_name} | RID: {router_id} | Protocols: {proto_str} | Site: {client.config.site_name}"
            else:
                ip_description = f"{agent_name} - {iface_name}"

            ip_result = await client.register_ip_address(
                address=ip_addr,
                interface_id=iface_result.get("interface_id"),
                status="active",
                description=ip_description
            )
            results["ip_addresses"].append(ip_result)

            # Track first IP for primary (prefer loopback)
            if ip_result.get("success"):
                if is_loopback or primary_ip_id is None:
                    primary_ip_id = ip_result.get("ip_id")

            if not ip_result.get("success"):
                results["errors"].append(f"IP {ip_addr}: {ip_result.get('error')}")

    # 4. Set primary IP on device
    if primary_ip_id:
        try:
            await client._set_primary_ip(agent_name, primary_ip_id)
        except Exception as e:
            results["errors"].append(f"Setting primary IP: {e}")

    # 5. Register services for protocols
    for proto in protocols:
        proto_type = proto.get("type", proto.get("t", "")).lower()
        service_result = await _register_protocol_service(client, agent_name, proto_type, proto)
        if service_result:
            results["services"].append(service_result)
            if not service_result.get("success"):
                results["errors"].append(f"Service {proto_type}: {service_result.get('error')}")

    return {
        "success": len(results["errors"]) == 0,
        "device_name": agent_name,
        "device_url": device_result.get("device_url"),
        **results
    }


def _map_agent_interface_type(agent_type: str) -> str:
    """Map agent interface type to NetBox interface type"""
    type_map = {
        "ethernet": "1000base-t",
        "eth": "1000base-t",
        "loopback": "virtual",
        "lo": "virtual",
        "virtual": "virtual",
        "vlan": "virtual",
        "bridge": "bridge",
        "bond": "lag",
        "tunnel": "virtual",
        "gre": "virtual",
        "vxlan": "virtual",
    }
    return type_map.get(agent_type.lower(), "other")


async def _register_protocol_service(client: NetBoxClient, device_name: str,
                                      proto_type: str, proto_config: Dict) -> Optional[Dict]:
    """Register a protocol as a NetBox service"""
    # Protocol to service mapping
    service_map = {
        "bgp": {"name": "BGP", "protocol": "tcp", "port": 179},
        "ospf": {"name": "OSPF", "protocol": "tcp", "port": 89},  # OSPF uses IP protocol 89
        "ospfv3": {"name": "OSPFv3", "protocol": "tcp", "port": 89},
        "isis": {"name": "IS-IS", "protocol": "tcp", "port": 0},  # IS-IS is L2
        "ldp": {"name": "LDP", "protocol": "tcp", "port": 646},
        "rsvp": {"name": "RSVP", "protocol": "tcp", "port": 0},
    }

    if proto_type not in service_map:
        return None

    service_info = service_map[proto_type]

    # Build description with protocol details
    description_parts = []
    if proto_type == "bgp":
        asn = proto_config.get("local_as", proto_config.get("asn", ""))
        if asn:
            description_parts.append(f"AS {asn}")
        peers = proto_config.get("peers", [])
        if peers:
            description_parts.append(f"{len(peers)} peer(s)")
    elif proto_type in ["ospf", "ospfv3"]:
        area = proto_config.get("area", proto_config.get("area_id", "0.0.0.0"))
        description_parts.append(f"Area {area}")
        router_id = proto_config.get("router_id", "")
        if router_id:
            description_parts.append(f"RID {router_id}")

    description = " | ".join(description_parts) if description_parts else f"ASI Agent {proto_type.upper()}"

    return await client.register_service(
        device_name=device_name,
        name=service_info["name"],
        protocol=service_info["protocol"],
        port=service_info["port"],
        description=description
    )
