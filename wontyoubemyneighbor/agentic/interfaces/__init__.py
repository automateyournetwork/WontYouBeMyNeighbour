"""
Interface Management Module

Provides:
- Subinterface (VLAN) management with 802.1Q tagging
- L3 routed subinterfaces for multiple IPs on routed ports
- IP address management (IPv4 and IPv6)
- Interface statistics
"""

from .subinterface import (
    SubinterfaceManager,
    Subinterface,
    PhysicalInterface,
    InterfaceState,
    InterfaceStatistics,
    EncapsulationType,
    InterfaceMode,
    get_subinterface_manager,
    start_subinterface_manager,
    stop_subinterface_manager,
    list_subinterfaces,
    get_subinterface_statistics
)

__all__ = [
    "SubinterfaceManager",
    "Subinterface",
    "PhysicalInterface",
    "InterfaceState",
    "InterfaceStatistics",
    "EncapsulationType",
    "InterfaceMode",
    "get_subinterface_manager",
    "start_subinterface_manager",
    "stop_subinterface_manager",
    "list_subinterfaces",
    "get_subinterface_statistics"
]
