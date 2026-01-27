"""
Inventory Module

Provides:
- Device inventory tracking
- Asset management
- Hardware/software inventory
- License tracking
- Lifecycle management
"""

from .inventory_manager import (
    DeviceType,
    DeviceStatus,
    LifecycleStage,
    HardwareInfo,
    SoftwareInfo,
    LicenseInfo,
    DeviceLocation,
    InventoryDevice,
    InventoryFilter,
    InventoryManager,
    get_inventory_manager
)

__all__ = [
    "DeviceType",
    "DeviceStatus",
    "LifecycleStage",
    "HardwareInfo",
    "SoftwareInfo",
    "LicenseInfo",
    "DeviceLocation",
    "InventoryDevice",
    "InventoryFilter",
    "InventoryManager",
    "get_inventory_manager"
]
