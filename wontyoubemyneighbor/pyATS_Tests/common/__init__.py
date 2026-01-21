"""
Common Tests - Tests applicable to all network agents

These tests verify basic functionality that every agent should have:
- Connectivity: IP reachability, DNS resolution
- Interfaces: Status, configuration, counters
- Resources: CPU, memory, storage utilization
"""

from . import connectivity_tests
from . import interface_tests
from . import resource_tests

__all__ = ['connectivity_tests', 'interface_tests', 'resource_tests']
