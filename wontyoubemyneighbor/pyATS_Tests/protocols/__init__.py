"""
Protocol Tests - Protocol-specific validation tests

Provides test suites for:
- OSPF: Adjacency, LSA, route installation, DR/BDR
- BGP: Peer establishment, prefix advertisement, path selection
- IS-IS: Adjacency, LSP propagation, route calculation
- VXLAN/EVPN: VTEP reachability, VNI configuration, MAC/IP learning
- MPLS/LDP: Label distribution, LFIB, tunnel connectivity
"""

from . import ospf_tests
from . import bgp_tests
from . import isis_tests
from . import vxlan_tests
from . import mpls_tests

__all__ = ['ospf_tests', 'bgp_tests', 'isis_tests', 'vxlan_tests', 'mpls_tests']
