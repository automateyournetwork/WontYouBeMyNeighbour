"""
Service Tests - Network service validation

Provides test suites for:
- DHCP: Pool configuration, lease assignment, relay
- DNS: Zone loading, query resolution
"""

from . import dhcp_tests
from . import dns_tests

__all__ = ['dhcp_tests', 'dns_tests']
