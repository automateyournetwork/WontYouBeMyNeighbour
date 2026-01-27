"""
Inventory Manager

Comprehensive device inventory tracking for network infrastructure.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Set
import uuid
import json


class DeviceType(Enum):
    """Device type classification."""
    ROUTER = "router"
    SWITCH = "switch"
    FIREWALL = "firewall"
    LOAD_BALANCER = "load_balancer"
    ACCESS_POINT = "access_point"
    SERVER = "server"
    STORAGE = "storage"
    VIRTUAL_MACHINE = "virtual_machine"
    CONTAINER = "container"
    APPLIANCE = "appliance"
    OTHER = "other"


class DeviceStatus(Enum):
    """Device operational status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    DECOMMISSIONED = "decommissioned"
    SPARE = "spare"
    FAILED = "failed"
    UNKNOWN = "unknown"


class LifecycleStage(Enum):
    """Device lifecycle stage."""
    PLANNING = "planning"
    PROCUREMENT = "procurement"
    DEPLOYMENT = "deployment"
    PRODUCTION = "production"
    END_OF_SALE = "end_of_sale"
    END_OF_SUPPORT = "end_of_support"
    END_OF_LIFE = "end_of_life"
    RETIRED = "retired"


@dataclass
class HardwareInfo:
    """Hardware information for a device."""
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    part_number: str = ""
    revision: str = ""
    cpu_model: str = ""
    cpu_cores: int = 0
    memory_gb: float = 0.0
    storage_gb: float = 0.0
    power_supplies: int = 0
    fans: int = 0
    ports: Dict[str, int] = field(default_factory=dict)
    form_factor: str = ""
    rack_units: int = 0
    weight_kg: float = 0.0
    power_watts: int = 0
    purchase_date: Optional[str] = None
    warranty_expiry: Optional[str] = None
    asset_tag: str = ""
    custom_fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "part_number": self.part_number,
            "revision": self.revision,
            "cpu_model": self.cpu_model,
            "cpu_cores": self.cpu_cores,
            "memory_gb": self.memory_gb,
            "storage_gb": self.storage_gb,
            "power_supplies": self.power_supplies,
            "fans": self.fans,
            "ports": self.ports,
            "form_factor": self.form_factor,
            "rack_units": self.rack_units,
            "weight_kg": self.weight_kg,
            "power_watts": self.power_watts,
            "purchase_date": self.purchase_date,
            "warranty_expiry": self.warranty_expiry,
            "asset_tag": self.asset_tag,
            "custom_fields": self.custom_fields
        }


@dataclass
class SoftwareInfo:
    """Software information for a device."""
    os_name: str = ""
    os_version: str = ""
    os_vendor: str = ""
    firmware_version: str = ""
    boot_image: str = ""
    config_register: str = ""
    uptime_seconds: int = 0
    last_boot: Optional[str] = None
    installed_packages: List[str] = field(default_factory=list)
    running_services: List[str] = field(default_factory=list)
    patch_level: str = ""
    vulnerabilities: List[str] = field(default_factory=list)
    custom_fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "os_name": self.os_name,
            "os_version": self.os_version,
            "os_vendor": self.os_vendor,
            "firmware_version": self.firmware_version,
            "boot_image": self.boot_image,
            "config_register": self.config_register,
            "uptime_seconds": self.uptime_seconds,
            "last_boot": self.last_boot,
            "installed_packages": self.installed_packages,
            "running_services": self.running_services,
            "patch_level": self.patch_level,
            "vulnerabilities": self.vulnerabilities,
            "custom_fields": self.custom_fields
        }


@dataclass
class LicenseInfo:
    """License information for software/features."""
    license_id: str = ""
    feature_name: str = ""
    license_type: str = ""  # perpetual, subscription, evaluation
    status: str = ""  # active, expired, grace_period
    start_date: Optional[str] = None
    expiry_date: Optional[str] = None
    quantity: int = 1
    used: int = 0
    vendor: str = ""
    support_level: str = ""
    entitlement_id: str = ""
    custom_fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "license_id": self.license_id,
            "feature_name": self.feature_name,
            "license_type": self.license_type,
            "status": self.status,
            "start_date": self.start_date,
            "expiry_date": self.expiry_date,
            "quantity": self.quantity,
            "used": self.used,
            "vendor": self.vendor,
            "support_level": self.support_level,
            "entitlement_id": self.entitlement_id,
            "custom_fields": self.custom_fields
        }


@dataclass
class DeviceLocation:
    """Physical location of a device."""
    site: str = ""
    building: str = ""
    floor: str = ""
    room: str = ""
    rack: str = ""
    rack_position: int = 0
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    postal_code: str = ""
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    custom_fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "site": self.site,
            "building": self.building,
            "floor": self.floor,
            "room": self.room,
            "rack": self.rack,
            "rack_position": self.rack_position,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "postal_code": self.postal_code,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "custom_fields": self.custom_fields
        }


@dataclass
class InventoryDevice:
    """Complete inventory record for a device."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    hostname: str = ""
    device_type: DeviceType = DeviceType.OTHER
    status: DeviceStatus = DeviceStatus.UNKNOWN
    lifecycle_stage: LifecycleStage = LifecycleStage.PRODUCTION

    # Network information
    management_ip: str = ""
    management_ipv6: str = ""
    loopback_ip: str = ""
    loopback_ipv6: str = ""
    interfaces: List[Dict] = field(default_factory=list)
    vlans: List[int] = field(default_factory=list)

    # Detailed info
    hardware: HardwareInfo = field(default_factory=HardwareInfo)
    software: SoftwareInfo = field(default_factory=SoftwareInfo)
    licenses: List[LicenseInfo] = field(default_factory=list)
    location: DeviceLocation = field(default_factory=DeviceLocation)

    # Organization
    owner: str = ""
    department: str = ""
    cost_center: str = ""
    project: str = ""
    environment: str = ""  # production, staging, development, lab

    # Tags and metadata
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    custom_fields: Dict[str, Any] = field(default_factory=dict)

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_seen: Optional[str] = None
    last_scanned: Optional[str] = None

    # Relationships
    parent_device_id: Optional[str] = None
    child_device_ids: List[str] = field(default_factory=list)
    connected_device_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "hostname": self.hostname,
            "device_type": self.device_type.value,
            "status": self.status.value,
            "lifecycle_stage": self.lifecycle_stage.value,
            "management_ip": self.management_ip,
            "management_ipv6": self.management_ipv6,
            "loopback_ip": self.loopback_ip,
            "loopback_ipv6": self.loopback_ipv6,
            "interfaces": self.interfaces,
            "vlans": self.vlans,
            "hardware": self.hardware.to_dict(),
            "software": self.software.to_dict(),
            "licenses": [lic.to_dict() for lic in self.licenses],
            "location": self.location.to_dict(),
            "owner": self.owner,
            "department": self.department,
            "cost_center": self.cost_center,
            "project": self.project,
            "environment": self.environment,
            "tags": self.tags,
            "notes": self.notes,
            "custom_fields": self.custom_fields,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_seen": self.last_seen,
            "last_scanned": self.last_scanned,
            "parent_device_id": self.parent_device_id,
            "child_device_ids": self.child_device_ids,
            "connected_device_ids": self.connected_device_ids
        }

    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow().isoformat()


@dataclass
class InventoryFilter:
    """Filter criteria for inventory queries."""
    device_types: List[DeviceType] = field(default_factory=list)
    statuses: List[DeviceStatus] = field(default_factory=list)
    lifecycle_stages: List[LifecycleStage] = field(default_factory=list)
    sites: List[str] = field(default_factory=list)
    vendors: List[str] = field(default_factory=list)
    os_names: List[str] = field(default_factory=list)
    environments: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    search_text: str = ""
    warranty_expiring_days: Optional[int] = None
    license_expiring_days: Optional[int] = None
    not_seen_days: Optional[int] = None

    def to_dict(self) -> Dict:
        return {
            "device_types": [dt.value for dt in self.device_types],
            "statuses": [s.value for s in self.statuses],
            "lifecycle_stages": [ls.value for ls in self.lifecycle_stages],
            "sites": self.sites,
            "vendors": self.vendors,
            "os_names": self.os_names,
            "environments": self.environments,
            "tags": self.tags,
            "search_text": self.search_text,
            "warranty_expiring_days": self.warranty_expiring_days,
            "license_expiring_days": self.license_expiring_days,
            "not_seen_days": self.not_seen_days
        }


class InventoryManager:
    """
    Comprehensive inventory management for network devices.

    Provides device tracking, asset management, lifecycle management,
    and reporting capabilities.
    """

    def __init__(self):
        self._devices: Dict[str, InventoryDevice] = {}
        self._devices_by_hostname: Dict[str, str] = {}
        self._devices_by_ip: Dict[str, str] = {}
        self._tags: Set[str] = set()
        self._sites: Set[str] = set()
        self._vendors: Set[str] = set()

    # ==================== Device CRUD ====================

    def add_device(self, device: InventoryDevice) -> InventoryDevice:
        """Add a device to inventory."""
        self._devices[device.id] = device

        # Index by hostname
        if device.hostname:
            self._devices_by_hostname[device.hostname.lower()] = device.id

        # Index by IPs
        if device.management_ip:
            self._devices_by_ip[device.management_ip] = device.id
        if device.loopback_ip:
            self._devices_by_ip[device.loopback_ip] = device.id

        # Track tags, sites, vendors
        for tag in device.tags:
            self._tags.add(tag)
        if device.location.site:
            self._sites.add(device.location.site)
        if device.hardware.manufacturer:
            self._vendors.add(device.hardware.manufacturer)

        return device

    def get_device(self, device_id: str) -> Optional[InventoryDevice]:
        """Get a device by ID."""
        return self._devices.get(device_id)

    def get_device_by_hostname(self, hostname: str) -> Optional[InventoryDevice]:
        """Get a device by hostname."""
        device_id = self._devices_by_hostname.get(hostname.lower())
        if device_id:
            return self._devices.get(device_id)
        return None

    def get_device_by_ip(self, ip: str) -> Optional[InventoryDevice]:
        """Get a device by IP address."""
        device_id = self._devices_by_ip.get(ip)
        if device_id:
            return self._devices.get(device_id)
        return None

    def update_device(self, device_id: str, updates: Dict) -> Optional[InventoryDevice]:
        """Update a device's fields."""
        device = self._devices.get(device_id)
        if not device:
            return None

        # Handle special fields
        if "hardware" in updates and isinstance(updates["hardware"], dict):
            for k, v in updates["hardware"].items():
                if hasattr(device.hardware, k):
                    setattr(device.hardware, k, v)
            del updates["hardware"]

        if "software" in updates and isinstance(updates["software"], dict):
            for k, v in updates["software"].items():
                if hasattr(device.software, k):
                    setattr(device.software, k, v)
            del updates["software"]

        if "location" in updates and isinstance(updates["location"], dict):
            for k, v in updates["location"].items():
                if hasattr(device.location, k):
                    setattr(device.location, k, v)
            del updates["location"]

        # Handle enum fields
        if "device_type" in updates:
            if isinstance(updates["device_type"], str):
                updates["device_type"] = DeviceType(updates["device_type"])
        if "status" in updates:
            if isinstance(updates["status"], str):
                updates["status"] = DeviceStatus(updates["status"])
        if "lifecycle_stage" in updates:
            if isinstance(updates["lifecycle_stage"], str):
                updates["lifecycle_stage"] = LifecycleStage(updates["lifecycle_stage"])

        # Apply updates
        for key, value in updates.items():
            if hasattr(device, key):
                setattr(device, key, value)

        device.update_timestamp()
        return device

    def delete_device(self, device_id: str) -> bool:
        """Delete a device from inventory."""
        device = self._devices.get(device_id)
        if not device:
            return False

        # Remove from indexes
        if device.hostname:
            self._devices_by_hostname.pop(device.hostname.lower(), None)
        if device.management_ip:
            self._devices_by_ip.pop(device.management_ip, None)
        if device.loopback_ip:
            self._devices_by_ip.pop(device.loopback_ip, None)

        # Remove from devices
        del self._devices[device_id]
        return True

    def list_devices(self, filter: Optional[InventoryFilter] = None) -> List[InventoryDevice]:
        """List devices with optional filtering."""
        devices = list(self._devices.values())

        if not filter:
            return devices

        # Apply filters
        if filter.device_types:
            devices = [d for d in devices if d.device_type in filter.device_types]

        if filter.statuses:
            devices = [d for d in devices if d.status in filter.statuses]

        if filter.lifecycle_stages:
            devices = [d for d in devices if d.lifecycle_stage in filter.lifecycle_stages]

        if filter.sites:
            devices = [d for d in devices if d.location.site in filter.sites]

        if filter.vendors:
            devices = [d for d in devices if d.hardware.manufacturer in filter.vendors]

        if filter.os_names:
            devices = [d for d in devices if d.software.os_name in filter.os_names]

        if filter.environments:
            devices = [d for d in devices if d.environment in filter.environments]

        if filter.tags:
            devices = [d for d in devices if any(t in d.tags for t in filter.tags)]

        if filter.search_text:
            search = filter.search_text.lower()
            devices = [d for d in devices if
                       search in d.name.lower() or
                       search in d.hostname.lower() or
                       search in d.management_ip.lower() or
                       search in d.hardware.serial_number.lower() or
                       search in d.notes.lower()]

        if filter.warranty_expiring_days is not None:
            now = datetime.utcnow()
            devices = [d for d in devices if
                       d.hardware.warranty_expiry and
                       self._days_until(d.hardware.warranty_expiry) <= filter.warranty_expiring_days]

        if filter.license_expiring_days is not None:
            devices = [d for d in devices if
                       any(lic.expiry_date and self._days_until(lic.expiry_date) <= filter.license_expiring_days
                           for lic in d.licenses)]

        if filter.not_seen_days is not None:
            now = datetime.utcnow()
            devices = [d for d in devices if
                       d.last_seen and
                       self._days_since(d.last_seen) >= filter.not_seen_days]

        return devices

    def _days_until(self, date_str: str) -> int:
        """Calculate days until a date."""
        try:
            target = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            now = datetime.utcnow()
            delta = target - now
            return delta.days
        except:
            return 999999

    def _days_since(self, date_str: str) -> int:
        """Calculate days since a date."""
        try:
            target = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            now = datetime.utcnow()
            delta = now - target
            return delta.days
        except:
            return 0

    # ==================== Bulk Operations ====================

    def import_devices(self, devices_data: List[Dict]) -> Dict[str, Any]:
        """Import multiple devices from data."""
        imported = 0
        updated = 0
        errors = []

        for data in devices_data:
            try:
                hostname = data.get("hostname", "")
                existing = self.get_device_by_hostname(hostname) if hostname else None

                if existing:
                    self.update_device(existing.id, data)
                    updated += 1
                else:
                    device = self._device_from_dict(data)
                    self.add_device(device)
                    imported += 1
            except Exception as e:
                errors.append({"data": data, "error": str(e)})

        return {
            "imported": imported,
            "updated": updated,
            "errors": len(errors),
            "error_details": errors
        }

    def export_devices(self, filter: Optional[InventoryFilter] = None) -> List[Dict]:
        """Export devices to data format."""
        devices = self.list_devices(filter)
        return [d.to_dict() for d in devices]

    def _device_from_dict(self, data: Dict) -> InventoryDevice:
        """Create a device from dictionary data."""
        device = InventoryDevice()

        # Basic fields
        for field in ["name", "hostname", "management_ip", "management_ipv6",
                      "loopback_ip", "loopback_ipv6", "owner", "department",
                      "cost_center", "project", "environment", "notes"]:
            if field in data:
                setattr(device, field, data[field])

        # Enum fields
        if "device_type" in data:
            device.device_type = DeviceType(data["device_type"])
        if "status" in data:
            device.status = DeviceStatus(data["status"])
        if "lifecycle_stage" in data:
            device.lifecycle_stage = LifecycleStage(data["lifecycle_stage"])

        # List fields
        if "tags" in data:
            device.tags = data["tags"]
        if "interfaces" in data:
            device.interfaces = data["interfaces"]
        if "vlans" in data:
            device.vlans = data["vlans"]

        # Hardware
        if "hardware" in data:
            hw = data["hardware"]
            for k, v in hw.items():
                if hasattr(device.hardware, k):
                    setattr(device.hardware, k, v)

        # Software
        if "software" in data:
            sw = data["software"]
            for k, v in sw.items():
                if hasattr(device.software, k):
                    setattr(device.software, k, v)

        # Location
        if "location" in data:
            loc = data["location"]
            for k, v in loc.items():
                if hasattr(device.location, k):
                    setattr(device.location, k, v)

        # Licenses
        if "licenses" in data:
            for lic_data in data["licenses"]:
                lic = LicenseInfo()
                for k, v in lic_data.items():
                    if hasattr(lic, k):
                        setattr(lic, k, v)
                device.licenses.append(lic)

        return device

    # ==================== Statistics & Reports ====================

    def get_statistics(self) -> Dict[str, Any]:
        """Get inventory statistics."""
        devices = list(self._devices.values())

        # Count by type
        by_type = {}
        for dt in DeviceType:
            count = len([d for d in devices if d.device_type == dt])
            if count > 0:
                by_type[dt.value] = count

        # Count by status
        by_status = {}
        for status in DeviceStatus:
            count = len([d for d in devices if d.status == status])
            if count > 0:
                by_status[status.value] = count

        # Count by lifecycle
        by_lifecycle = {}
        for stage in LifecycleStage:
            count = len([d for d in devices if d.lifecycle_stage == stage])
            if count > 0:
                by_lifecycle[stage.value] = count

        # Count by site
        by_site = {}
        for device in devices:
            site = device.location.site or "Unknown"
            by_site[site] = by_site.get(site, 0) + 1

        # Count by vendor
        by_vendor = {}
        for device in devices:
            vendor = device.hardware.manufacturer or "Unknown"
            by_vendor[vendor] = by_vendor.get(vendor, 0) + 1

        # Count by environment
        by_environment = {}
        for device in devices:
            env = device.environment or "Unknown"
            by_environment[env] = by_environment.get(env, 0) + 1

        # Warranty expiring soon (30 days)
        warranty_expiring = len([d for d in devices
                                 if d.hardware.warranty_expiry and
                                 0 <= self._days_until(d.hardware.warranty_expiry) <= 30])

        # Licenses expiring soon (30 days)
        license_expiring = len([d for d in devices
                                if any(lic.expiry_date and 0 <= self._days_until(lic.expiry_date) <= 30
                                       for lic in d.licenses)])

        # Not seen recently (7 days)
        not_seen_recently = len([d for d in devices
                                 if d.last_seen and self._days_since(d.last_seen) >= 7])

        return {
            "total_devices": len(devices),
            "by_type": by_type,
            "by_status": by_status,
            "by_lifecycle": by_lifecycle,
            "by_site": by_site,
            "by_vendor": by_vendor,
            "by_environment": by_environment,
            "warranty_expiring_30d": warranty_expiring,
            "license_expiring_30d": license_expiring,
            "not_seen_7d": not_seen_recently,
            "unique_tags": len(self._tags),
            "unique_sites": len(self._sites),
            "unique_vendors": len(self._vendors)
        }

    def get_alerts(self) -> List[Dict[str, Any]]:
        """Get inventory alerts for attention items."""
        alerts = []
        devices = list(self._devices.values())

        for device in devices:
            # Warranty expiring
            if device.hardware.warranty_expiry:
                days = self._days_until(device.hardware.warranty_expiry)
                if 0 <= days <= 30:
                    alerts.append({
                        "type": "warranty_expiring",
                        "severity": "warning" if days > 7 else "critical",
                        "device_id": device.id,
                        "device_name": device.name,
                        "message": f"Warranty expires in {days} days",
                        "expiry_date": device.hardware.warranty_expiry
                    })

            # License expiring
            for lic in device.licenses:
                if lic.expiry_date:
                    days = self._days_until(lic.expiry_date)
                    if 0 <= days <= 30:
                        alerts.append({
                            "type": "license_expiring",
                            "severity": "warning" if days > 7 else "critical",
                            "device_id": device.id,
                            "device_name": device.name,
                            "message": f"License '{lic.feature_name}' expires in {days} days",
                            "expiry_date": lic.expiry_date
                        })

            # End of support
            if device.lifecycle_stage == LifecycleStage.END_OF_SUPPORT:
                alerts.append({
                    "type": "end_of_support",
                    "severity": "warning",
                    "device_id": device.id,
                    "device_name": device.name,
                    "message": "Device is end of support"
                })

            # End of life
            if device.lifecycle_stage == LifecycleStage.END_OF_LIFE:
                alerts.append({
                    "type": "end_of_life",
                    "severity": "critical",
                    "device_id": device.id,
                    "device_name": device.name,
                    "message": "Device is end of life"
                })

            # Not seen recently
            if device.last_seen:
                days = self._days_since(device.last_seen)
                if device.status == DeviceStatus.ACTIVE and days >= 7:
                    alerts.append({
                        "type": "not_seen",
                        "severity": "warning",
                        "device_id": device.id,
                        "device_name": device.name,
                        "message": f"Device not seen for {days} days",
                        "last_seen": device.last_seen
                    })

            # Failed status
            if device.status == DeviceStatus.FAILED:
                alerts.append({
                    "type": "device_failed",
                    "severity": "critical",
                    "device_id": device.id,
                    "device_name": device.name,
                    "message": "Device is in failed state"
                })

        # Sort by severity
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda a: severity_order.get(a["severity"], 99))

        return alerts

    def get_tags(self) -> List[str]:
        """Get all unique tags."""
        return sorted(list(self._tags))

    def get_sites(self) -> List[str]:
        """Get all unique sites."""
        return sorted(list(self._sites))

    def get_vendors(self) -> List[str]:
        """Get all unique vendors."""
        return sorted(list(self._vendors))

    # ==================== Relationships ====================

    def add_connection(self, device_id1: str, device_id2: str) -> bool:
        """Add a connection between two devices."""
        device1 = self._devices.get(device_id1)
        device2 = self._devices.get(device_id2)

        if not device1 or not device2:
            return False

        if device_id2 not in device1.connected_device_ids:
            device1.connected_device_ids.append(device_id2)
        if device_id1 not in device2.connected_device_ids:
            device2.connected_device_ids.append(device_id1)

        return True

    def remove_connection(self, device_id1: str, device_id2: str) -> bool:
        """Remove a connection between two devices."""
        device1 = self._devices.get(device_id1)
        device2 = self._devices.get(device_id2)

        if not device1 or not device2:
            return False

        if device_id2 in device1.connected_device_ids:
            device1.connected_device_ids.remove(device_id2)
        if device_id1 in device2.connected_device_ids:
            device2.connected_device_ids.remove(device_id1)

        return True

    def get_connected_devices(self, device_id: str) -> List[InventoryDevice]:
        """Get all devices connected to a device."""
        device = self._devices.get(device_id)
        if not device:
            return []

        return [self._devices[did] for did in device.connected_device_ids
                if did in self._devices]

    def set_parent(self, child_id: str, parent_id: str) -> bool:
        """Set parent-child relationship."""
        child = self._devices.get(child_id)
        parent = self._devices.get(parent_id)

        if not child or not parent:
            return False

        # Remove from old parent
        if child.parent_device_id:
            old_parent = self._devices.get(child.parent_device_id)
            if old_parent and child_id in old_parent.child_device_ids:
                old_parent.child_device_ids.remove(child_id)

        # Set new parent
        child.parent_device_id = parent_id
        if child_id not in parent.child_device_ids:
            parent.child_device_ids.append(child_id)

        return True


# Singleton instance
_inventory_manager: Optional[InventoryManager] = None


def get_inventory_manager() -> InventoryManager:
    """Get the singleton inventory manager instance."""
    global _inventory_manager
    if _inventory_manager is None:
        _inventory_manager = InventoryManager()
    return _inventory_manager
