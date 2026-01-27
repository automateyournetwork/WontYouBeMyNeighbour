"""
Multi-Vendor Network Simulation Module

Provides vendor-specific behaviors, CLI syntax, and operational characteristics
for simulating different network equipment manufacturers.
"""

from .vendor_manager import (
    VendorManager,
    Vendor,
    VendorProfile,
    VendorCapability,
    CLISyntax,
    get_vendor_manager,
    get_vendor,
    list_vendors,
    get_cli_syntax,
)

__all__ = [
    "VendorManager",
    "Vendor",
    "VendorProfile",
    "VendorCapability",
    "CLISyntax",
    "get_vendor_manager",
    "get_vendor",
    "list_vendors",
    "get_cli_syntax",
]
