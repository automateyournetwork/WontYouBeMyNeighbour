"""
VXLAN/EVPN Implementation

Virtual eXtensible Local Area Network (VXLAN) with
Ethernet VPN (EVPN) control plane for software-defined
overlay networking.

Based on:
- RFC 7348: VXLAN
- RFC 7432: BGP MPLS-Based EVPN
- RFC 8365: VXLAN-GPE
"""

from .vtep import VTEP, VXLANTunnel
from .evpn import EVPNInstance, MACIPRoute, InclusiveMulticastRoute
from .vni import VNI, VNIManager

__all__ = [
    'VTEP',
    'VXLANTunnel',
    'EVPNInstance',
    'MACIPRoute',
    'InclusiveMulticastRoute',
    'VNI',
    'VNIManager',
]
