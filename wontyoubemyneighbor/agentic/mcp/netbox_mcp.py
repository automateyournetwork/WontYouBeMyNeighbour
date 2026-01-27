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

            payload = {
                "address": address,
                "status": status
            }

            if interface_id:
                payload["assigned_object_type"] = "dcim.interface"
                payload["assigned_object_id"] = interface_id
            if description:
                payload["description"] = description

            if existing:
                response = await client.patch(f"/api/ipam/ip-addresses/{existing['id']}/", json=payload)
                action = "updated"
            else:
                response = await client.post("/api/ipam/ip-addresses/", json=payload)
                action = "created"

            if response.status_code in (200, 201):
                result = response.json()
                return {
                    "success": True,
                    "action": action,
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

            payload = {
                "device": device_id,
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
        agent_config = {
            "name": device.get("name", ""),
            "router_id": device.get("primary_ipv4") or self._extract_loopback_ip(device),
            "site": device.get("site", {}).get("name", ""),
            "role": device.get("role", {}).get("name", "Router"),
            "manufacturer": device.get("device_type", {}).get("manufacturer", {}).get("name", ""),
            "device_type": device.get("device_type", {}).get("model", ""),
            "platform": device.get("platform", {}).get("name", "") if device.get("platform") else "",
            "serial": device.get("serial", ""),
            "status": device.get("status", {}).get("value", "active"),
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
                "type": self._map_interface_type(iface.get("type", {}).get("value", "")),
                "enabled": iface.get("enabled", True),
                "mac_address": iface.get("mac_address", ""),
                "mtu": iface.get("mtu"),
                "description": iface.get("description", ""),
                "ip_addresses": []
            }

            # Add IP addresses
            for ip in iface.get("ip_addresses", []):
                iface_config["ip_addresses"].append({
                    "address": ip.get("address", ""),
                    "status": ip.get("status", {}).get("value", "active"),
                    "primary": ip.get("id") == device.get("primary_ip4", {}).get("id") or
                              ip.get("id") == device.get("primary_ip6", {}).get("id")
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
        role = device.get("role", {}).get("name", "").lower()
        tags = [t.get("name", "").lower() for t in device.get("tags", [])]

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

    # 1. Register the device
    device_result = await client.register_device(device)
    results["device"] = device_result

    if not device_result.get("success"):
        results["errors"].append(f"Device creation failed: {device_result.get('error')}")
        return {"success": False, **results}

    # 2. Register all interfaces
    interfaces = agent_config.get("interfaces", [])
    primary_ip_id = None
    primary_interface_id = None

    for iface in interfaces:
        iface_name = iface.get("name", iface.get("n", ""))
        if not iface_name:
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

            ip_result = await client.register_ip_address(
                address=ip_addr,
                interface_id=iface_result.get("interface_id"),
                status="active",
                description=f"Agent interface {iface_name}"
            )
            results["ip_addresses"].append(ip_result)

            # Track first IP for primary (prefer loopback)
            if ip_result.get("success"):
                is_loopback = "lo" in iface_name.lower() or "loopback" in iface_name.lower()
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
