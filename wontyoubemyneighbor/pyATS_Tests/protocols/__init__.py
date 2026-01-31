"""
Protocol Tests - Protocol-specific validation tests

Provides test suites for:
- OSPF: Adjacency, LSA, route installation, DR/BDR
- BGP: Peer establishment, prefix advertisement, path selection
- IS-IS: Adjacency, LSP propagation, route calculation
- VXLAN/EVPN: VTEP reachability, VNI configuration, MAC/IP learning
- MPLS/LDP: Label distribution, LFIB, tunnel connectivity
- GRE: Tunnel state, endpoint reachability, MTU, key validation
- BFD: Session state, detection timers, protocol integration
"""

from . import ospf_tests
from . import bgp_tests
from . import isis_tests
from . import vxlan_tests
from . import mpls_tests
from . import gre_tests
from . import bfd_tests

__all__ = ['ospf_tests', 'bgp_tests', 'isis_tests', 'vxlan_tests', 'mpls_tests', 'gre_tests', 'bfd_tests']
